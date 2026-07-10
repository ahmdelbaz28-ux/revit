"""
backend/routers/llm.py — AI Copilot Router (Zenmux LLM integration).

ENDPOINTS
---------
* ``POST /api/v1/llm/chat``          — Chat completion (engineering assistant)
* ``POST /api/v1/llm/explain``       — Explain an NFPA 72 calculation result
* ``POST /api/v1/llm/compliance-narrative`` — Draft a compliance narrative
* ``GET  /api/v1/llm/health``        — Service status
* ``GET  /api/v1/llm/models``        — List available models (passthrough)

All endpoints require ``CALCULATION_EXECUTE`` (chat/explain/narrative) or
``HEALTH_READ`` (health/models) permission. Rate-limited to 30/min for write
endpoints and 60/min for read endpoints.

SAFETY
------
The LLM is **advisory only**. It never overrides deterministic NFPA 72
calculations. All responses include a ``source`` field and a ``disclaimer``
reminding the engineer that AI output must be verified against the published code.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.auth import require_permission
from backend.limiter import limiter
from backend.rbac import Permission
from backend.services.llm_service import LLMResponse, get_llm_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm", tags=["llm"])

# Standard disclaimer appended to all AI-generated narratives.
# This protects the engineer and the AHJ (Authority Having Jurisdiction) by
# making it explicit that AI output is advisory and must be verified.
_AI_DISCLAIMER = (
	"⚠️ AI-GENERATED CONTENT — Advisory only. This output was produced by an "
	"LLM and must be verified against the published NFPA 72 / NEC code by a "
	"licensed fire-protection engineer before use in a submittal."
)

# Standard error messages — defined once to avoid duplication (SonarCloud S1192).
_ERR_NOT_CONFIGURED = "LLM service not configured"
_ERR_REQUEST_FAILED = "LLM request failed"

# Standard OpenAPI response specs for documented HTTP errors (SonarCloud S8415).
_RES_502 = {
	502: {
		"description": "LLM provider returned an error",
		"content": {
			"application/json": {
				"example": {"detail": {"error": "LLM_REQUEST_FAILED"}},
			}
		},
	},
}
_RES_503 = {
	503: {
		"description": "LLM service is not configured (ZENMUX_API_KEY missing)",
		"content": {
			"application/json": {
				"example": {"detail": {"error": "LLM_SERVICE_UNAVAILABLE"}},
			}
		},
	},
}


# ── Request / Response models ────────────────────────────────────────────────


class ChatRequest(BaseModel):
	"""Request body for POST /llm/chat."""

	prompt: str = Field(
		...,
		min_length=1,
		max_length=8000,
		description="The user's question or instruction to the LLM.",
	)
	system: str | None = Field(
		None,
		max_length=2000,
		description="Optional system message to set the assistant's persona.",
	)
	model: str | None = Field(
		None,
		description="Override the default model (e.g. 'z-ai/glm-4.7-flash-free').",
	)
	temperature: float = Field(
		0.1,
		ge=0.0,
		le=2.0,
		description="Sampling temperature. Low values = more deterministic.",
	)
	max_tokens: int | None = Field(
		None,
		ge=1,
		le=8000,
		description="Max tokens to generate. Defaults to ZENMUX_MAX_TOKENS.",
	)


class ExplainRequest(BaseModel):
	"""Request body for POST /llm/explain — explain a calculation result."""

	calculation_type: str = Field(
		...,
		max_length=100,
		description="e.g. 'smoke_spacing', 'voltage_drop', 'battery_sizing'",
	)
	calculation_result: Dict[str, Any] = Field(
		...,
		description="The JSON result returned by the qomn/analyze endpoint.",
	)
	question: str = Field(
		"Explain this result and its NFPA 72 / NEC basis.",
		max_length=2000,
		description="What to ask the LLM about the result.",
	)


class ComplianceNarrativeRequest(BaseModel):
	"""Request body for POST /llm/compliance-narrative."""

	project_name: str = Field(..., max_length=200)
	building_description: str = Field(..., max_length=2000)
	calculations_summary: Dict[str, Any] = Field(
		...,
		description="Summary of key calculations (spacing, voltage, battery, FACP).",
	)
	audience: str = Field(
		"AHJ",
		max_length=50,
		description="Target audience: 'AHJ', 'client', 'internal'.",
	)


class LLMResponseModel(BaseModel):
	"""Standard response wrapper for LLM endpoints."""

	content: str
	model: str
	source: str = "zenmux"
	finish_reason: str = "stop"
	prompt_tokens: int = 0
	completion_tokens: int = 0
	total_tokens: int = 0
	disclaimer: str = _AI_DISCLAIMER


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post(
	"/chat",
	dependencies=[Depends(require_permission(Permission.CALCULATION_EXECUTE))],
	responses={**_RES_502, **_RES_503},
)
@limiter.limit("30/minute")
async def llm_chat(request: Request, req: ChatRequest) -> Dict[str, Any]:
	"""Send a chat completion request to the LLM.

	The LLM acts as an engineering assistant. It can answer NFPA 72 / NEC
	code questions, explain calculation results, and draft compliance text.

	**Advisory only** — all output must be verified by a licensed engineer.
	"""
	svc = get_llm_service()
	if not svc.available:
		raise HTTPException(
			status_code=503,
			detail={
				"error": "LLM_SERVICE_UNAVAILABLE",
				"message": _ERR_NOT_CONFIGURED,
			},
		)
	try:
		result: LLMResponse = await svc.chat(
			req.prompt,
			system=req.system,
			model=req.model,
			temperature=req.temperature,
			max_tokens=req.max_tokens,
		)
	except Exception:
		logger.exception("LLM chat failed")
		raise HTTPException(
			status_code=502,
			detail={
				"error": "LLM_REQUEST_FAILED",
				"message": _ERR_REQUEST_FAILED,
			},
		) from None

	return {
		"success": True,
		"data": _build_response_data(result),
	}


@router.post(
	"/explain",
	dependencies=[Depends(require_permission(Permission.CALCULATION_EXECUTE))],
	responses={**_RES_502, **_RES_503},
)
@limiter.limit("30/minute")
async def llm_explain(request: Request, req: ExplainRequest) -> Dict[str, Any]:
	"""Explain a calculation result in plain language.

	Takes a calculation result (e.g. from ``/api/v1/qomn/smoke-spacing``) and
	asks the LLM to explain its meaning and the NFPA 72 / NEC basis.
	"""
	svc = get_llm_service()
	if not svc.available:
		raise HTTPException(503, detail=_ERR_NOT_CONFIGURED)

	import json

	system_msg = (
		"You are a licensed fire-protection engineer explaining NFPA 72 and NEC "
		"calculation results to a colleague. Be precise, cite the relevant code "
		"section, and flag any non-compliance. Do NOT invent code sections."
	)
	prompt = (
		f"Calculation type: {req.calculation_type}\n\n"
		f"Result JSON:\n{json.dumps(req.calculation_result, indent=2)}\n\n"
		f"Question: {req.question}"
	)
	try:
		result = await svc.chat(prompt, system=system_msg, temperature=0.1)
	except Exception:
		logger.exception("LLM explain failed")
		raise HTTPException(502, detail=_ERR_REQUEST_FAILED) from None

	return {"success": True, "data": _build_response_data(result)}


@router.post(
	"/compliance-narrative",
	dependencies=[Depends(require_permission(Permission.CALCULATION_EXECUTE))],
	responses={**_RES_502, **_RES_503},
)
@limiter.limit("20/minute")
async def llm_compliance_narrative(
	request: Request, req: ComplianceNarrativeRequest
) -> Dict[str, Any]:
	"""Draft a compliance narrative for a submittal package.

	Generates a narrative paragraph summarizing the fire-alarm design's
	compliance with NFPA 72, suitable for inclusion in an AHJ submittal.
	"""
	svc = get_llm_service()
	if not svc.available:
		raise HTTPException(503, detail=_ERR_NOT_CONFIGURED)

	import json

	system_msg = (
		"You are a fire-protection engineer drafting a compliance narrative for "
		f"a submittal to the {req.audience}. Use formal technical language, cite "
		"NFPA 72-2022 sections precisely, and do NOT invent requirements. If a "
		"calculation result is missing, note it as 'to be verified'."
	)
	prompt = (
		f"Project: {req.project_name}\n\n"
		f"Building: {req.building_description}\n\n"
		f"Calculations summary:\n{json.dumps(req.calculations_summary, indent=2)}\n\n"
		f"Draft a compliance narrative (2-3 paragraphs) for the {req.audience}."
	)
	try:
		result = await svc.chat(
			prompt, system=system_msg, temperature=0.2, max_tokens=1500
		)
	except Exception:
		logger.exception("LLM compliance narrative failed")
		raise HTTPException(502, detail=_ERR_REQUEST_FAILED) from None

	return {"success": True, "data": _build_response_data(result)}


@router.get(
	"/health",
	dependencies=[Depends(require_permission(Permission.HEALTH_READ))],
)
@limiter.limit("60/minute")
async def llm_health(request: Request) -> Dict[str, Any]:
	"""Return the LLM service configuration status (never raises)."""
	svc = get_llm_service()
	status = await svc.health()
	return {"success": True, "data": status}


@router.get(
	"/models",
	dependencies=[Depends(require_permission(Permission.CALCULATION_READ))],
	responses={**_RES_502, **_RES_503},
)
@limiter.limit("60/minute")
async def llm_models(request: Request) -> Dict[str, Any]:
	"""List models available on the configured LLM provider (passthrough)."""
	svc = get_llm_service()
	if not svc.available:
		raise HTTPException(503, detail=_ERR_NOT_CONFIGURED)
	try:
		client = svc._get_client()  # noqa: SLF001 — internal access acceptable in router
		models_page = await client.models.list()
		models = []
		for m in models_page.data:
			models.append({"id": m.id, "owned_by": getattr(m, "owned_by", "")})
		return {"success": True, "data": {"models": models, "count": len(models)}}
	except Exception:
		logger.exception("LLM models list failed")
		raise HTTPException(502, detail=_ERR_REQUEST_FAILED) from None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_response_data(result: LLMResponse) -> Dict[str, Any]:
	"""Build the standard response data dict from an LLMResponse."""
	return LLMResponseModel(
		content=result.content,
		model=result.model,
		source=result.source,
		finish_reason=result.finish_reason,
		prompt_tokens=result.prompt_tokens,
		completion_tokens=result.completion_tokens,
		total_tokens=result.total_tokens,
	).model_dump()
