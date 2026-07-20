"""
backend/services/uptime_service.py — UptimeRobot Keep-Awake and Monitoring Integration.
========================================================================================

Handles:
1. Periodic heartbeat pings to UptimeRobot push/heartbeat monitor.
2. Querying UptimeRobot API to fetch real-time monitor status and statistics.
3. Keep-awake behavior to prevent Hugging Face Spaces / server sleep.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# ── Keys and Configuration ───────────────────────────────────────────────────
# SECURITY: Keys MUST be set via environment variables. Never hardcode them.
# Set UPTIMEROBOT_USER_KEY (read-only key recommended) and
# UPTIMEROBOT_MONITOR_KEY (heartbeat monitor key) in your environment.
# Get keys from: https://dashboard.uptimerobot.com/integrations

USER_KEY = os.getenv("UPTIMEROBOT_USER_KEY", "")
MONITOR_KEY = os.getenv("UPTIMEROBOT_MONITOR_KEY", "")
HEARTBEAT_INTERVAL = int(os.getenv("UPTIMEROBOT_HEARTBEAT_INTERVAL", "300"))  # 5 minutes

if not USER_KEY:
    logger.warning(
        "UPTIMEROBOT_USER_KEY is not set. Monitor status API will be disabled. "
        "Set it in your environment to enable UptimeRobot monitoring."
    )
if not MONITOR_KEY:
    logger.warning(
        "UPTIMEROBOT_MONITOR_KEY is not set. Heartbeat pings will be disabled. "
        "Set it in your environment to enable keep-awake heartbeats."
    )

# ── Singleton Pattern ──────────────────────────────────────────────────────────

_instance: Optional[UptimeService] = None
_lock = threading.Lock()


def get_uptime_service() -> UptimeService:
    """Get the UptimeService singleton instance."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = UptimeService()
    return _instance


class UptimeService:
    """Service to handle keep-awake push heartbeats and fetch UptimeRobot stats."""

    def __init__(self) -> None:
        self._loop_running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._last_ping_status = "never"
        self._last_ping_time: float = 0.0

    async def start_heartbeat_loop(self) -> None:
        """Start the periodic heartbeat ping background task."""
        if self._loop_running:
            return

        self._loop_running = True
        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.info("UptimeRobot Heartbeat background task started.")

    async def stop_heartbeat_loop(self) -> None:
        """Stop the background heartbeat task."""
        self._loop_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                # S7497: Re-raise CancelledError after cleanup per asyncio guidelines
                raise
            self._task = None
        logger.info("UptimeRobot Heartbeat background task stopped.")

    async def _heartbeat_loop(self) -> None:
        """Background loop executing the ping requests."""
        # Warmup delay to let the app initialize fully
        await asyncio.sleep(5)

        async with httpx.AsyncClient(timeout=10.0) as client:
            while self._loop_running:
                try:
                    await self._ping_heartbeat(client)
                except Exception as e:
                    logger.warning("UptimeRobot heartbeat loop error: %s", e)

                await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def _ping_heartbeat(self, client: httpx.AsyncClient) -> bool:
        """Send a single heartbeat ping to UptimeRobot."""
        if not MONITOR_KEY:
            logger.warning("UptimeRobot Monitor Key is not set. Skipping heartbeat ping.")
            self._last_ping_status = "disabled"
            return False

        # Heartbeat endpoint format: https://heartbeat.uptimerobot.com/MONITOR_KEY
        url = f"https://heartbeat.uptimerobot.com/{MONITOR_KEY}"
        try:
            res = await client.get(url)
            if res.status_code == 200:
                self._last_ping_status = "success"
                self._last_ping_time = time.time()
                logger.debug("Successfully sent UptimeRobot heartbeat ping.")
                return True
            else:
                self._last_ping_status = f"failed (HTTP {res.status_code})"
                logger.warning("UptimeRobot heartbeat returned HTTP %s", res.status_code)
                return False
        except httpx.HTTPError as e:
            self._last_ping_status = f"failed ({type(e).__name__})"
            logger.warning("UptimeRobot heartbeat network failure: %s", e)
            return False

    async def fetch_monitor_status(self) -> Dict[str, Any]:
        """
        Query the UptimeRobot API using the user key to get monitor statuses.
        """
        if not USER_KEY:
            return {"success": False, "error": "User API Key is not configured."}

        url = "https://api.uptimerobot.com/v2/getMonitors"
        payload = {
            "api_key": USER_KEY,
            "format": "json",
            "logs": 1
        }
        headers = {
            "content-type": "application/x-www-form-urlencoded"
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, data=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    if data.get("stat") == "ok":
                        return {"success": True, "monitors": data.get("monitors", [])}
                    return {"success": False, "error": data.get("error", {}).get("message", "API Error")}
                return {"success": False, "error": f"HTTP {res.status_code}"}
        except Exception as e:
            logger.exception("Failed to query UptimeRobot API: %s", e)
            return {"success": False, "error": str(e)}

    def get_local_status(self) -> Dict[str, Any]:
        """Return the status of the local keep-awake loop."""
        return {
            "loop_running": self._loop_running,
            "last_ping_status": self._last_ping_status,
            "last_ping_time": self._last_ping_time,
            "interval_seconds": HEARTBEAT_INTERVAL,
        }
