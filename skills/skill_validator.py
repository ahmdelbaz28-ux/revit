"""
skills/skill_validator.py - AI Agent Skill Validation System

This module provides comprehensive validation for AI Agent Skills
using Pydantic models with strict type checking and validation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

T = TypeVar("T")


# ═══════════════════════════════════════════════════════════════════════════
# SKILL METADATA
# ═══════════════════════════════════════════════════════════════════════════


class SkillMetadata(BaseModel):
    """Validated skill metadata with strict constraints."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    name: str = Field(
        min_length=1,
        max_length=100,
        description="Skill name - unique identifier",
    )
    version: str = Field(
        pattern=r"^\d+\.\d+\.\d+$",
        description="Semantic version (X.Y.Z)",
    )
    author: str = Field(
        min_length=1,
        max_length=100,
        description="Author name or organization",
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Creation timestamp",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="Last update timestamp",
    )

    @field_validator("version")
    @classmethod
    def validate_version_format(cls, v: str) -> str:
        """Ensure version follows semantic versioning."""
        parts = v.split(".")
        if len(parts) != 3:
            raise ValueError("Version must be X.Y.Z format")
        if not all(p.isdigit() for p in parts):
            raise ValueError("All version parts must be numeric")
        return v

    @field_validator("name")
    @classmethod
    def validate_name_chars(cls, v: str) -> str:
        """Ensure name contains only allowed characters."""
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_")
        if not all(c.lower() in allowed for c in v):
            raise ValueError(
                "Name must contain only lowercase letters, numbers, hyphens, underscores"
            )
        return v.lower()


# ═══════════════════════════════════════════════════════════════════════════
# SKILL DESCRIPTION
# ═══════════════════════════════════════════════════════════════════════════


class SkillDescription(BaseModel):
    """Skill description with trigger word extraction."""

    model_config = ConfigDict(extra="forbid")

    short_description: str = Field(
        min_length=10,
        max_length=200,
        description="Brief description for listings",
    )
    long_description: str | None = Field(
        default=None,
        max_length=5000,
        description="Detailed description",
    )
    trigger_words: list[str] = Field(
        min_length=1,
        max_length=50,
        description="Keywords that activate this skill",
    )
    use_cases: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Common use case descriptions",
    )

    @field_validator("trigger_words")
    @classmethod
    def validate_triggers(cls, v: list[str]) -> list[str]:
        """Ensure trigger words are meaningful."""
        if not v:
            raise ValueError("At least one trigger word is required")
        cleaned = [t.strip().lower() for t in v if t.strip()]
        if len(cleaned) < len(v):
            raise ValueError("Trigger words cannot be empty or whitespace only")
        return list(set(cleaned))  # Deduplicate


# ═══════════════════════════════════════════════════════════════════════════
# SKILL CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════


class SkillPermissions(BaseModel):
    """Permissions required by a skill."""

    model_config = ConfigDict(extra="forbid")

    network: bool = Field(default=False, description="Requires network access")
    filesystem_read: bool = Field(default=False, description="Requires read access")
    filesystem_write: bool = Field(default=False, description="Requires write access")
    subprocess: bool = Field(default=False, description="Can spawn subprocesses")
    env_vars: list[str] = Field(default_factory=list, description="Required env vars")

    @field_validator("env_vars", mode="before")
    @classmethod
    def validate_env_vars(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v if isinstance(v, list) else []


class SkillRequirements(BaseModel):
    """Runtime requirements for a skill."""

    model_config = ConfigDict(extra="forbid")

    python_version: str = Field(
        pattern=r"^\d+\.\d+$",
        default="3.10",
        description="Minimum Python version",
    )
    dependencies: dict[str, str] = Field(
        default_factory=dict,
        description="Package name to version spec",
    )
    permissions: SkillPermissions = Field(
        default_factory=SkillPermissions,
        description="Permission requirements",
    )
    max_execution_time: int = Field(
        default=300,
        ge=1,
        le=3600,
        description="Max execution time in seconds",
    )


# ═══════════════════════════════════════════════════════════════════════════
# EXECUTION RESULT
# ═══════════════════════════════════════════════════════════════════════════


class ExecutionError(BaseModel):
    """Standardized error response."""

    model_config = ConfigDict(extra="forbid")

    error: bool = True
    type: str = Field(description="Error classification")
    message: str = Field(description="Human-readable message")
    action_required: str | None = Field(
        default=None,
        description="How to resolve",
    )
    can_retry: bool = Field(default=False, description="Whether retry is safe")
    details: dict[str, Any] | None = Field(
        default=None,
        description="Additional context",
    )


class ExecutionResult(BaseModel, Generic[T]):
    """Generic execution result with type safety."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(description="Whether execution succeeded")
    data: T | None = Field(default=None, description="Result data")
    error: ExecutionError | None = Field(default=None, description="Error if failed")
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Execution timestamp",
    )
    duration_ms: float | None = Field(
        default=None,
        ge=0,
        description="Execution duration in milliseconds",
    )

    @model_validator(mode="after")
    def validate_mutual_exclusivity(self) -> ExecutionResult:
        """Ensure error and data are mutually exclusive."""
        if self.success and self.error is not None:
            raise ValueError("Cannot have error on successful execution")
        if not self.success and self.data is not None:
            raise ValueError("Cannot have data on failed execution")
        return self

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON export."""
        return self.model_dump(mode="json")


# ═══════════════════════════════════════════════════════════════════════════
# SKILL VALIDATOR
# ═══════════════════════════════════════════════════════════════════════════


class SkillManifest(BaseModel):
    """Complete skill manifest with all validation."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    metadata: SkillMetadata
    description: SkillDescription
    requirements: SkillRequirements = Field(default_factory=SkillRequirements)
    version_compatibility: str = Field(
        default="1.0",
        pattern=r"^\d+\.\d+$",
    )
    tags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [x.strip().lower() for x in v.split(",") if x.strip()]
        return v if isinstance(v, list) else []

    @field_validator("tags")
    @classmethod
    def validate_tags_content(cls, v: list[str]) -> list[str]:
        """Ensure tags are meaningful."""
        return [t for t in v if len(t) >= 2]

    def get_trigger_pattern(self) -> str:
        """Generate regex pattern from trigger words."""
        import re
        escaped = [re.escape(t) for t in self.description.trigger_words]
        return "|".join(escaped)


# ═══════════════════════════════════════════════════════════════════════════
# VALIDATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════


def validate_skill_manifest(data: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Validate skill manifest data.

    Returns:
        (is_valid, error_message)

    """
    try:
        SkillManifest(**data)
        return True, None
    except Exception as e:
        return False, str(e)


def validate_version_compatibility(
    skill_version: str,
    system_version: str,
) -> bool:
    """
    Check if skill version is compatible with system.

    Args:
        skill_version: Version claimed by skill (X.Y)
        system_version: Current system version (X.Y)

    Returns:
        True if compatible

    """
    skill_parts = skill_version.split(".")
    system_parts = system_version.split(".")

    # Major version must match
    if skill_parts[0] != system_parts[0]:
        return False

    # Minor version must be <= system
    return int(skill_parts[1]) <= int(system_parts[1])
