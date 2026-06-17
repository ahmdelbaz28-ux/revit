"""
tests/factories/skill_factories.py

Factory classes for creating test instances of skill-related objects.
These factories provide easy ways to create valid test data for testing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import random
import string

from skills.skill_validator import (
    SkillMetadata,
    SkillDescription,
    SkillPermissions,
    SkillRequirements,
    SkillManifest,
    ExecutionResult,
    ExecutionError,
)


class SkillMetadataFactory:
    """Factory for creating SkillMetadata instances."""
    
    @classmethod
    def create(
        cls,
        name: Optional[str] = None,
        version: Optional[str] = None,
        author: Optional[str] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ) -> SkillMetadata:
        """Create a SkillMetadata instance with default values."""
        if name is None:
            name = f"test-skill-{cls._random_suffix()}"
        if version is None:
            version = f"{random.randint(0, 9)}.{random.randint(0, 9)}.{random.randint(0, 9)}"
        if author is None:
            author = f"test-author-{cls._random_suffix()}"
        
        return SkillMetadata(
            name=name,
            version=version,
            author=author,
            created_at=created_at or datetime.now(),
            updated_at=updated_at,
        )
    
    @staticmethod
    def _random_suffix(length: int = 6) -> str:
        """Generate a random suffix for test data."""
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


class SkillDescriptionFactory:
    """Factory for creating SkillDescription instances."""
    
    @classmethod
    def create(
        cls,
        short_description: Optional[str] = None,
        long_description: Optional[str] = None,
        trigger_words: Optional[list[str]] = None,
        use_cases: Optional[list[str]] = None,
    ) -> SkillDescription:
        """Create a SkillDescription instance with default values."""
        if short_description is None:
            short_description = f"Test skill for {cls._random_suffix()}"
        if trigger_words is None:
            trigger_words = [f"test{cls._random_suffix()[:3]}", f"skill{cls._random_suffix()[:3]}"]
        if use_cases is None:
            use_cases = [f"Use case for {cls._random_suffix()}"]
        
        return SkillDescription(
            short_description=short_description,
            long_description=long_description,
            trigger_words=trigger_words,
            use_cases=use_cases,
        )
    
    @staticmethod
    def _random_suffix(length: int = 6) -> str:
        """Generate a random suffix for test data."""
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


class SkillPermissionsFactory:
    """Factory for creating SkillPermissions instances."""
    
    @classmethod
    def create(
        cls,
        network: Optional[bool] = None,
        filesystem_read: Optional[bool] = None,
        filesystem_write: Optional[bool] = None,
        subprocess: Optional[bool] = None,
        env_vars: Optional[list[str]] = None,
    ) -> SkillPermissions:
        """Create a SkillPermissions instance with default values."""
        if network is None:
            network = random.choice([True, False])
        if filesystem_read is None:
            filesystem_read = random.choice([True, False])
        if filesystem_write is None:
            filesystem_write = random.choice([True, False])
        if subprocess is None:
            subprocess = random.choice([True, False])
        if env_vars is None:
            env_vars = [f"ENV_VAR_{cls._random_suffix().upper()}"]
        
        return SkillPermissions(
            network=network,
            filesystem_read=filesystem_read,
            filesystem_write=filesystem_write,
            subprocess=subprocess,
            env_vars=env_vars,
        )
    
    @staticmethod
    def _random_suffix(length: int = 6) -> str:
        """Generate a random suffix for test data."""
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


class SkillRequirementsFactory:
    """Factory for creating SkillRequirements instances."""
    
    @classmethod
    def create(
        cls,
        python_version: Optional[str] = None,
        dependencies: Optional[dict[str, str]] = None,
        permissions: Optional[SkillPermissions] = None,
        max_execution_time: Optional[int] = None,
    ) -> SkillRequirements:
        """Create a SkillRequirements instance with default values."""
        if python_version is None:
            python_version = f"{random.randint(3, 3)}.{random.randint(8, 11)}"
        if dependencies is None:
            dependencies = {f"pkg{cls._random_suffix()}": f">={random.randint(1, 2)}.0.0"}
        if permissions is None:
            permissions = SkillPermissionsFactory.create()
        if max_execution_time is None:
            max_execution_time = random.randint(60, 3600)
        
        return SkillRequirements(
            python_version=python_version,
            dependencies=dependencies,
            permissions=permissions,
            max_execution_time=max_execution_time,
        )
    
    @staticmethod
    def _random_suffix(length: int = 6) -> str:
        """Generate a random suffix for test data."""
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


class ExecutionErrorFactory:
    """Factory for creating ExecutionError instances."""
    
    @classmethod
    def create(
        cls,
        error: bool = True,
        type: Optional[str] = None,
        message: Optional[str] = None,
        action_required: Optional[str] = None,
        can_retry: Optional[bool] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> ExecutionError:
        """Create an ExecutionError instance with default values."""
        if type is None:
            type = f"ERROR_TYPE_{cls._random_suffix().upper()}"
        if message is None:
            message = f"Error occurred: {cls._random_suffix()}"
        if can_retry is None:
            can_retry = random.choice([True, False])
        
        return ExecutionError(
            error=error,
            type=type,
            message=message,
            action_required=action_required,
            can_retry=can_retry,
            details=details,
        )
    
    @staticmethod
    def _random_suffix(length: int = 6) -> str:
        """Generate a random suffix for test data."""
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


class ExecutionResultFactory:
    """Factory for creating ExecutionResult instances."""
    
    @classmethod
    def create(
        cls,
        success: Optional[bool] = None,
        data: Optional[Any] = None,
        error: Optional[ExecutionError] = None,
        timestamp: Optional[datetime] = None,
        duration_ms: Optional[float] = None,
    ) -> ExecutionResult:
        """Create an ExecutionResult instance with default values."""
        if success is None:
            success = random.choice([True, False])
        
        # Ensure mutual exclusivity of data and error
        if success:
            if error is not None:
                error = None
            if data is None:
                data = {"result": cls._random_suffix(), "value": random.randint(1, 100)}
        else:
            if data is not None:
                data = None
            if error is None:
                error = ExecutionErrorFactory.create()
        
        return ExecutionResult(
            success=success,
            data=data,
            error=error,
            timestamp=timestamp or datetime.now(),
            duration_ms=duration_ms,
        )
    
    @staticmethod
    def _random_suffix(length: int = 6) -> str:
        """Generate a random suffix for test data."""
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


class SkillManifestFactory:
    """Factory for creating SkillManifest instances."""
    
    @classmethod
    def create(
        cls,
        metadata: Optional[SkillMetadata] = None,
        description: Optional[SkillDescription] = None,
        requirements: Optional[SkillRequirements] = None,
        version_compatibility: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> SkillManifest:
        """Create a SkillManifest instance with default values."""
        if metadata is None:
            metadata = SkillMetadataFactory.create()
        if description is None:
            description = SkillDescriptionFactory.create()
        if requirements is None:
            requirements = SkillRequirementsFactory.create()
        if version_compatibility is None:
            version_compatibility = f"{random.randint(1, 2)}.{random.randint(0, 9)}"
        if tags is None:
            tags = [f"tag{cls._random_suffix()[:5]}", f"type{cls._random_suffix()[:5]}"]
        
        return SkillManifest(
            metadata=metadata,
            description=description,
            requirements=requirements,
            version_compatibility=version_compatibility,
            tags=tags,
        )
    
    @staticmethod
    def _random_suffix(length: int = 6) -> str:
        """Generate a random suffix for test data."""
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


# Convenience functions for common test scenarios
def create_valid_skill_manifest() -> SkillManifest:
    """Create a fully valid skill manifest for testing."""
    return SkillManifestFactory.create()


def create_valid_execution_result(success: bool = True) -> ExecutionResult:
    """Create a valid execution result for testing."""
    return ExecutionResultFactory.create(success=success)