from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent-ws"])

# Active connections from agents
# Map from agent_type -> list of WebSocket
active_agents: Dict[str, list[WebSocket]] = {}
agent_response_futures: Dict[str, asyncio.Future[Any]] = {}

# A lock per connection to serialize command dispatches
agent_locks: Dict[str, asyncio.Lock] = {}


def get_agent_lock(websocket: WebSocket) -> asyncio.Lock:
    ws_id = str(id(websocket))
    if ws_id not in agent_locks:
        agent_locks[ws_id] = asyncio.Lock()
    return agent_locks[ws_id]


# S-06 FIX (Engineering Review): the previous signature used
#   api_key: str = Query(..., alias="api_key")
# which placed the API key in the URL query string. Query strings are logged
# by every proxy (nginx, Cloudflare, Akamai, Vercel), captured in browser
# history, and may leak via Referer headers. The key is now extracted from the
# `X-API-Key` request header BEFORE the WebSocket handshake is accepted.
#
# Backward compatibility: if the header is missing, we fall back to checking
# the Sec-WebSocket-Protocol subprotocol (clients can send the key as the
# first subprotocol). The query-string path is no longer supported.


def _extract_api_key_from_handshake(websocket: WebSocket) -> str:
    """Pull the API key from headers or subprotocol — never from the query string."""
    # 1. Header-based (preferred)
    headers = websocket.headers
    for name in ("x-api-key", "X-API-Key", "authorization"):
        val = headers.get(name)
        if val:
            if name.lower() == "authorization" and val.lower().startswith("bearer "):
                return val[7:].strip()
            return val.strip()
    # 2. Subprotocol-based (for browsers that cannot set custom headers on WS)
    protocols = websocket.headers.get("sec-websocket-protocol", "")
    if protocols:
        # The first token is the API key (client must send it as the subprotocol)
        return protocols.split(",")[0].strip()
    return ""


@router.websocket("/ws")
async def agent_websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for the local agent to connect.

    S-06 FIX: the API key MUST be supplied via the `X-API-Key` request header
    (or as the Sec-WebSocket-Protocol subprotocol for browser clients). It is
    no longer accepted as a query-string parameter — query strings are logged
    by every reverse proxy and would leak the key.
    """
    from backend.api_keys import validate_api_key

    api_key = _extract_api_key_from_handshake(websocket)
    if not api_key:
        logger.warning("Rejected agent connection: no API key in headers/subprotocol")
        await websocket.close(code=4003)
        return

    try:
        is_valid = validate_api_key(api_key) is not None
        if not is_valid:
            logger.warning("Rejected agent connection: invalid API Key")
            await websocket.close(code=4003)
            return
    except Exception as e:
        logger.error("Error validating agent API Key: %s", e)
        await websocket.close(code=4003)
        return

    await websocket.accept()
    logger.info("Local Agent connected to WebSocket successfully")

    agent_type = "autocad_revit"
    if agent_type not in active_agents:
        active_agents[agent_type] = []
    active_agents[agent_type].append(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get("type")
                if msg_type == "response":
                    cmd_id = msg.get("id")
                    payload = msg.get("payload")
                    if cmd_id in agent_response_futures:
                        agent_response_futures[cmd_id].set_result(payload)
                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
            except Exception as e:
                logger.warning("Error handling agent message: %s", e)
    except WebSocketDisconnect:
        logger.info("Local Agent disconnected from WebSocket")
    finally:
        if agent_type in active_agents and websocket in active_agents[agent_type]:
            active_agents[agent_type].remove(websocket)
        agent_locks.pop(str(id(websocket)), None)


def has_active_agent(agent_type: str = "autocad_revit") -> bool:
    """Check if there is at least one active agent connected."""
    return len(active_agents.get(agent_type, [])) > 0


async def send_agent_command(agent_type: str, action: str, args: Dict[str, Any], timeout: float = 30.0) -> Any:
    """
    Send a command to the active agent and await the response.
    """
    agents = active_agents.get("autocad_revit", [])
    if not agents:
        raise HTTPException(status_code=503, detail="No active local agent connected.")

    websocket = agents[0]
    cmd_id = str(uuid.uuid4())
    future = asyncio.get_running_loop().create_future()
    agent_response_futures[cmd_id] = future

    lock = get_agent_lock(websocket)
    async with lock:
        try:
            await websocket.send_json({
                "type": "command",
                "id": cmd_id,
                "action": f"{agent_type}/{action}",
                "args": args
            })
            response = await asyncio.wait_for(future, timeout=timeout)
            if isinstance(response, dict) and "error" in response:
                raise HTTPException(status_code=400, detail=response["error"])
            return response
        except asyncio.TimeoutError as exc:
            logger.error("Agent command %s timed out after %s seconds", action, timeout)
            raise HTTPException(status_code=504, detail="Local Agent command execution timed out.") from exc
        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            logger.exception("Error executing agent command %s: %s", action, e)
            raise HTTPException(status_code=502, detail=f"Failed to execute local agent command: {e}")
        finally:
            agent_response_futures.pop(cmd_id, None)
