"""
skills/skill_validator.py — AI Agent Skill Validation System
============================================================

Production-ready skill validation using Pydantic patterns.
Implements robust data validation for AI agent skills with comprehensive error handling.

ARCHITECTURE:
- Pydantic BaseModel for skill data structures
- Custom field validators for business logic
- Serialization/deserialization patterns
- Comprehensive error handling

USAGE:
    from skills.skill_validator import SkillDescription, ExecutionResult
    skill = SkillDescription(name="test", description="test desc", trigger_words=["test"])
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Union, Dict, Any, List
import re


class SkillMetadata(BaseModel):
    """
    Metadata for AI agent skills.
    
    Contains authorship, versioning, and dependency information.
    """
    author: str = Field(
        ..., 
        description="Author of the skill", 
        min_length=1,
        max_length=100
    )
    version: str = Field(
        ..., 
        description="Semantic version of the skill",
        pattern=r"^\d+\.\d+\.\d+$"
    )
    requires: Dict[str, str] = Field(
        default_factory=dict,
        description="Dependency requirements for the skill"
    )
    license: Optional[str] = Field(
        default=None,
        description="License information for the skill"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Tags for categorizing the skill"
    )

    @field_validator('author')
    @classmethod
    def validate_author(cls, v: str) -> str:
        """Validate author field."""
        if not v.strip():
            raise ValueError("Author cannot be empty or whitespace")
        return v.strip()


class SkillDescription(BaseModel):
    """
    Description and configuration for an AI agent skill.
    
    Defines the skill's purpose, triggers, and execution parameters.
    """
    name: str = Field(
        ...,
        description="Unique name of the skill",
        min_length=1,
        max_length=100,
        pattern=r'^[a-zA-Z][a-zA-Z0-9_-]*$'
    )
    description: str = Field(
        ...,
        description="Detailed description of what the skill does",
        min_length=10,
        max_length=1000
    )
    trigger_words: List[str] = Field(
        ...,
        description="Words that trigger this skill",
        min_length=1
    )
    category: str = Field(
        default="general",
        description="Category for organizing skills",
        min_length=1,
        max_length=50
    )
    enabled: bool = Field(
        default=True,
        description="Whether the skill is enabled"
    )
    timeout: int = Field(
        default=30,
        description="Timeout in seconds for skill execution",
        ge=1,
        le=300
    )
    priority: int = Field(
        default=0,
        description="Execution priority (lower runs first)",
        ge=-10,
        le=10
    )

    @field_validator('trigger_words')
    @classmethod
    def validate_trigger_words(cls, v: List[str]) -> List[str]:
        """Validate trigger words."""
        if not v:
            raise ValueError("Must have at least one trigger word")
        cleaned = []
        for word in v:
            cleaned_word = word.strip().lower()
            if not cleaned_word:
                raise ValueError(f"Trigger word cannot be empty: '{word}'")
            cleaned.append(cleaned_word)
        return list(set(cleaned))  # Remove duplicates

    @field_validator('description')
    @classmethod
    def validate_description(cls, v: str) -> str:
        """Validate description field."""
        if len(v.strip()) < 10:
            raise ValueError("Description must be at least 10 characters")
        return v.strip()

    @model_validator(mode='after')
    def validate_triggers_coverage(self) -> 'SkillDescription':
        """Validate that trigger words provide adequate coverage for the skill."""
        if self.trigger_words and self.description:
            # Ensure trigger words are reasonable for the description
            desc_lower = self.description.lower()
            for trigger in self.trigger_words:
                if len(trigger) < 2:
                    raise ValueError(f"Trigger word '{trigger}' is too short (minimum 2 characters)")
        return self


class ExecutionResult(BaseModel):
    """
    Result of executing an AI agent skill.
    
    Contains success status, data, and error information.
    """
    success: bool = Field(..., description="Whether the skill execution succeeded")
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Result data from successful execution"
    )
    error: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Error information from failed execution"
    )
    execution_time: Optional[float] = Field(
        default=None,
        description="Time taken to execute the skill in seconds"
    )
    timestamp: Optional[str] = Field(
        default=None,
        description="Timestamp of execution"
    )

    @model_validator(mode='after')
    def validate_result_consistency(self) -> 'ExecutionResult':
        """Ensure result consistency."""
        if self.success and self.error:
            raise ValueError("Success cannot be True when error is present")
        if not self.success and not self.error:
            raise ValueError("Error must be present when success is False")
        if self.success and self.data is None:
            raise ValueError("Data must be present when success is True")
        return self


class SkillConfig(BaseModel):
    """
    Configuration for skill execution environment.
    """
    max_concurrent: int = Field(
        default=5,
        description="Maximum number of concurrent executions",
        ge=1,
        le=100
    )
    cache_enabled: bool = Field(
        default=True,
        description="Whether caching is enabled for this skill"
    )
    cache_ttl: int = Field(
        default=3600,
        description="Cache time-to-live in seconds",
        ge=60,
        le=86400
    )
    rate_limit: Optional[Dict[str, int]] = Field(
        default=None,
        description="Rate limiting configuration"
    )
    allowed_hosts: List[str] = Field(
        default_factory=list,
        description="List of allowed hosts for external requests"
    )


class SkillManifest(BaseModel):
    """
    Complete manifest describing a skill and its configuration.
    """
    metadata: SkillMetadata
    description: SkillDescription
    config: SkillConfig = Field(default_factory=SkillConfig)
    dependencies: List[str] = Field(
        default_factory=list,
        description="List of skill dependencies"
    )

    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this manifest."""
        return self.model_json_schema()