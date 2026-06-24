"""FireAI Type-Safe API Contract System
======================================

Inspired by tRPC's end-to-end type safety, this module provides:
1. Structured API contract definitions with Pydantic validation
2. Auto-generated OpenAPI spec from contracts
3. Runtime response validation against contracts
4. Frontend type generation support (openapi-typescript compatible)
5. Contract versioning and backward compatibility checks

Unlike tRPC (TypeScript-only), this works with our Python FastAPI
backend and generates TypeScript types for the frontend automatically.

SAFETY: In a life-critical system, the API contract MUST be enforced.
Malformed responses could cause the frontend to display incorrect
coverage data, leading to false confidence in detector placement.

Architecture:
    FastAPI Route → ContractValidator → Pydantic Validation → Response
                                       ↓
                              OpenAPI Spec → TypeScript Types
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRACT DEFINITION
# ═══════════════════════════════════════════════════════════════════════════════


class ContractSeverity(str, Enum):
    """How strictly to enforce the contract."""

    STRICT = "strict"  # Raise exception on violation
    LOG = "log"  # Log violation but return response
    DISABLED = "disabled"  # No validation (development only)


class APIContract(BaseModel, Generic[T]):
    """Defines a typed API contract for an endpoint.

    Each contract specifies:
    - The endpoint path and method
    - Request and response schemas (Pydantic models)
    - NFPA/safety references
    - Version for compatibility tracking

    This replaces the manual contract.py validation with
    automatic, type-safe validation.
    """

    endpoint: str
    method: str = "GET"
    request_schema: Optional[str] = None  # Pydantic model class name
    response_schema: Optional[str] = None  # Pydantic model class name
    nfpa_reference: Optional[str] = None
    safety_critical: bool = False
    version: str = "1.0.0"
    description: str = ""


class ContractViolationDetail(BaseModel):
    """Detailed information about a contract violation."""

    endpoint: str
    method: str
    violation_type: str  # "response_schema", "request_schema", "missing_field"
    field_path: str = ""
    expected_type: str = ""
    actual_value: Any = None
    severity: ContractSeverity = ContractSeverity.STRICT
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRACT VALIDATOR
# ═══════════════════════════════════════════════════════════════════════════════


class ContractValidator:
    """Validates API responses against their declared contracts.

    This replaces the manual validation in backend/contract.py with
    automatic Pydantic-based validation that generates TypeScript types
    for the frontend.

    SAFETY: In a life-critical system, EVERY response MUST be validated.
    An unvalidated response could contain:
    - Missing fields → frontend shows empty data
    - Wrong types → frontend crashes silently
    - Stale data → engineer makes decisions on outdated information

    Usage:
        validator = ContractValidator()
        validator.register("/api/projects", "GET", ProjectResponse)
        result = validator.validate_response("/api/projects", "GET", data)
    """

    def __init__(
        self,
        severity: ContractSeverity = ContractSeverity.STRICT,
    ) -> None:
        self.severity = severity
        self._contracts: Dict[str, Dict[str, Type[BaseModel]]] = {}
        self._violation_log: List[ContractViolationDetail] = []

    def register(
        self,
        endpoint: str,
        method: str,
        response_model: Type[BaseModel],
        nfpa_reference: Optional[str] = None,
        safety_critical: bool = False,
    ) -> None:
        """Register a response contract for an endpoint."""
        key = f"{method}:{endpoint}"
        self._contracts[key] = {
            "response_model": response_model,
            "nfpa_reference": nfpa_reference,  # type: ignore[dict-item]
            "safety_critical": safety_critical,  # type: ignore[dict-item]
        }
        logger.debug("Contract registered: %s", key)

    def validate_response(
        self,
        endpoint: str,
        method: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validate a response against its contract.

        Returns the validated data. Raises on STRICT violations.
        Logs on LOG violations. Skips on DISABLED — EXCEPT for
        safety-critical contracts which are ALWAYS enforced.

        V93 FIX (V67-5): Safety-critical contracts bypass severity mode.
        In a life-critical fire alarm system, a DISABLED or LOG mode
        should NOT allow malformed safety data through. If a contract
        is marked safety_critical=True, violations ALWAYS raise, even
        in LOG or DISABLED mode. Non-critical contracts respect the
        configured severity. This follows agent.md Priority 1 (Safety)
        and Rule 12 (safety-first thinking).
        """
        key = f"{method}:{endpoint}"
        contract = self._contracts.get(key)

        # V93 FIX (V67-5): DISABLED mode short-circuits ONLY for
        # non-registered, non-critical endpoints. If the contract
        # exists and is safety_critical, we MUST validate regardless.
        if self.severity == ContractSeverity.DISABLED:
            if contract is None:
                # No contract registered, DISABLED mode → skip entirely
                return data
            # Contract exists — check if safety-critical before skipping
            if not contract.get("safety_critical", False):
                # Non-critical contract, DISABLED mode → skip validation
                logger.debug("Contract validation DISABLED for %s", key)
                return data
            # Safety-critical contract — FALL THROUGH to validation
            # even in DISABLED mode. Log a warning that we're overriding.
            logger.warning(
                f"V93: Severity is DISABLED but contract for {key} is "
                f"safety_critical=True — OVERRIDING to enforce validation. "
                f"Safety-critical data must NEVER pass unvalidated."
            )

        if contract is None:
            # SAFETY FIX (MEDIUM-19): In STRICT mode, unregistered contracts
            # MUST fail validation, not silently pass. In a safety-critical
            # system, unregistered endpoints bypass contract validation until
            # explicitly registered — this is a security gap. Only LOG and
            # DISABLED modes allow unregistered endpoints through.
            if self.severity == ContractSeverity.STRICT:
                raise ValidationError.from_exception_data(  # type: ignore[call-arg]
                    title=f"No contract registered for {method}:{endpoint}",
                    input_data=data,
                )
            logger.warning(
                f"No contract registered for {key}. "
                f"Response validation SKIPPED. Register a contract "
                f"to ensure type safety."
            )
            return data

        response_model: Type[BaseModel] = contract["response_model"]
        safety_critical: bool = contract.get("safety_critical", False)  # type: ignore[assignment]

        try:
            # Validate using Pydantic model
            validated = response_model.model_validate(data)
            return validated.model_dump()

        except ValidationError as e:
            violation = ContractViolationDetail(
                endpoint=endpoint,
                method=method,
                violation_type="response_schema",
                field_path=str(e.errors()),
                expected_type=response_model.__name__,
                actual_value=data,
                severity=self.severity,
            )
            self._violation_log.append(violation)

            if safety_critical:
                logger.critical(
                    f"SAFETY-CRITICAL contract violation on {key}: {e.errors()}. "
                    f"In a fire alarm system, malformed data could cause "
                    f"incorrect engineering decisions."
                )
                # V93 FIX (V67-5): Safety-critical violations ALWAYS raise,
                # regardless of severity mode. In a life-safety system,
                # returning unvalidated safety data is worse than failing.
                raise

            if self.severity == ContractSeverity.STRICT:
                raise

            logger.error("Contract violation on %s: %s. Returning unvalidated response (severity=LOG).", key, e.errors())
            return data

    def validate_request(
        self,
        endpoint: str,
        method: str,
        data: Dict[str, Any],
        request_model: Type[BaseModel],
    ) -> Dict[str, Any]:
        """Validate a request body against its contract.

        For mutating endpoints (POST, PUT, PATCH, DELETE), request
        validation is mandatory in a safety-critical system to prevent
        unauthorized or malformed modifications.
        """
        try:
            validated = request_model.model_validate(data)
            return validated.model_dump()
        except ValidationError as e:
            violation = ContractViolationDetail(
                endpoint=endpoint,
                method=method,
                violation_type="request_schema",
                field_path=str(e.errors()),
                expected_type=request_model.__name__,
                actual_value=data,
            )
            self._violation_log.append(violation)
            logger.error("Request validation failed on %s:%s: %s", method, endpoint, e.errors())
            raise

    def get_violations(self) -> List[ContractViolationDetail]:
        """Get all recorded contract violations for audit."""
        return list(self._violation_log)

    def get_openapi_components(self) -> Dict[str, Any]:
        """Generate OpenAPI schema components from registered contracts.

        This replaces manual schema definition and enables automatic
        TypeScript type generation for the frontend using:
          npx openapi-typescript openapi.json -o src/types/api.d.ts

        This gives us tRPC-like type safety without requiring TypeScript
        on the backend.
        """
        schemas: Dict[str, Any] = {}

        for _key, contract in self._contracts.items():
            response_model: Type[BaseModel] = contract["response_model"]
            schema = response_model.model_json_schema()
            model_name = response_model.__name__
            schemas[model_name] = schema

        return {"schemas": schemas}

    def get_contract_summary(self) -> List[Dict[str, Any]]:
        """Get a summary of all registered contracts."""
        summary = []
        for key, contract in self._contracts.items():
            method, endpoint = key.split(":", 1)
            response_model: Type[BaseModel] = contract["response_model"]
            summary.append(
                {
                    "method": method,
                    "endpoint": endpoint,
                    "response_type": response_model.__name__,
                    "nfpa_reference": contract.get("nfpa_reference"),
                    "safety_critical": contract.get("safety_critical", False),
                }
            )
        return summary


# ═══════════════════════════════════════════════════════════════════════════════
# FASTAPI INTEGRATION HELPER
# ═══════════════════════════════════════════════════════════════════════════════


def create_contract_aware_router(
    validator: ContractValidator,
) -> Dict[str, Any]:
    """Create router configuration that enforces contracts.

    This replaces the manual contract.py approach with automatic
    validation using FastAPI's response_model parameter.

    Usage in FastAPI:
        @app.get("/api/projects",
                 response_model=ProjectListResponse)
        async def list_projects():
            ...

    FastAPI already validates responses when response_model is set.
    This helper adds:
    - Contract registration for audit
    - NFPA reference tracking
    - Safety-critical endpoint marking
    """
    return {
        "validator": validator,
        "auto_validate": True,
        "log_violations": True,
        "strict_mode": True,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TYPE GENERATION HELPER
# ═══════════════════════════════════════════════════════════════════════════════


def generate_typescript_config(
    openapi_url: str = "http://localhost:8000/openapi.json",
    output_path: str = "src/types/api.d.ts",
) -> str:
    """Generate a configuration for openapi-typescript.

    This enables automatic TypeScript type generation from the
    FastAPI OpenAPI spec, giving us tRPC-like type safety
    on the frontend without requiring TypeScript on the backend.

    Run in the frontend directory:
        npx openapi-typescript {openapi_url} -o {output_path}

    Then in the frontend code:
        import type { paths } from './types/api';
        type ProjectResponse = paths['/api/projects']['get']['responses']['200']['content']['application/json'];
    """
    return f"""
// FireAI Type Generation Configuration
// ======================================
//
// Run this command to generate TypeScript types from the API:
//   npx openapi-typescript {openapi_url} -o {output_path}
//
// This gives you tRPC-like type safety on the frontend:
//   import type {{ paths }} from './types/api';
//   type ProjectResponse = paths['/api/projects']['get']['responses']['200']['content']['application/json'];
//
// CRITICAL: Re-run this command whenever the API changes.
// The TypeScript compiler will catch any breaking changes.

export const API_CONFIG = {{
  openapiUrl: "{openapi_url}",
  outputPath: "{output_path}",
}};
"""
