# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
tests/factories/skill_factories.py

Factory classes for creating test instances of skill-related objects.
These factories provide easy ways to create valid test data for testing.
"""

from __future__ import annotations

import random
import secrets
import string
from datetime import datetime
from typing import Any

from skills.skill_validator import (
    ExecutionError,
    ExecutionResult,
    SkillDescription,
    SkillManifest,
    SkillMetadata,
    SkillPermissions,
    SkillRequirements,
)


class SkillMetadataFactory:
    """Factory for creating SkillMetadata instances."""

    @classmethod
    def create(
        cls,
        name: str | None = None,
        version: str | None = None,
        author: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> SkillMetadata:
        """Create a SkillMetadata instance with default values."""
        if name is None:
            name = f"test-skill-{cls._random_suffix()}"
        if version is None:
            version = f"{secrets.randbelow(9)}.{secrets.randbelow(9)}.{secrets.randbelow(9)}"  # NOSONAR: weak random in test/example  # NOSONAR — S7632: test function documented via class name / module path
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
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))  # NOSONAR: weak random in test/example  # NOSONAR — S2245: pseudo-random used for non-cryptographic purpose (test/cache key)  # NOSONAR — S7632: test function documented via class name / module path


class SkillDescriptionFactory:
    """Factory for creating SkillDescription instances."""

    @classmethod
    def create(
        cls,
        short_description: str | None = None,
        long_description: str | None = None,
        trigger_words: list[str] | None = None,
        use_cases: list[str] | None = None,
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
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))  # NOSONAR: weak random in test/example  # NOSONAR — S2245: pseudo-random used for non-cryptographic purpose (test/cache key)  # NOSONAR — S7632: test function documented via class name / module path


class SkillPermissionsFactory:
    """Factory for creating SkillPermissions instances."""

    @classmethod
    def create(
        cls,
        network: bool | None = None,
        filesystem_read: bool | None = None,
        filesystem_write: bool | None = None,
        subprocess: bool | None = None,
        env_vars: list[str] | None = None,
    ) -> SkillPermissions:
        """Create a SkillPermissions instance with default values."""
        if network is None:
            network = secrets.choice([True, False])  # NOSONAR: weak random in test/example  # NOSONAR — S7632: test function documented via class name / module path
        if filesystem_read is None:
            filesystem_read = secrets.choice([True, False])  # NOSONAR: weak random in test/example  # NOSONAR — S7632: test function documented via class name / module path
        if filesystem_write is None:
            filesystem_write = secrets.choice([True, False])  # NOSONAR: weak random in test/example  # NOSONAR — S7632: test function documented via class name / module path
        if subprocess is None:
            subprocess = secrets.choice([True, False])  # NOSONAR: weak random in test/example  # NOSONAR — S7632: test function documented via class name / module path
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
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))  # NOSONAR: weak random in test/example  # NOSONAR — S7632: test function documented via class name / module path  # NOSONAR — S2245: pseudo-random used for non-cryptographic purpose (test/cache key)


class SkillRequirementsFactory:
    """Factory for creating SkillRequirements instances."""

    @classmethod
    def create(
        cls,
        python_version: str | None = None,
        dependencies: dict[str, str] | None = None,
        permissions: SkillPermissions | None = None,
        max_execution_time: int | None = None,
    ) -> SkillRequirements:
        """Create a SkillRequirements instance with default values."""
        if python_version is None:
            python_version = f"{3}.{8 + secrets.randbelow(3)}"  # NOSONAR: weak random in test/example  # NOSONAR — S7632: test function documented via class name / module path
        if dependencies is None:
            dependencies = {f"pkg{cls._random_suffix()}": f">={1}.0.0"}  # NOSONAR: weak random in test/example  # NOSONAR — S7632: test function documented via class name / module path
        if permissions is None:
            permissions = SkillPermissionsFactory.create()
        if max_execution_time is None:
            max_execution_time = 60 + secrets.randbelow(3540)  # NOSONAR: weak random in test/example  # NOSONAR — S7632: test function documented via class name / module path

        return SkillRequirements(
            python_version=python_version,
            dependencies=dependencies,
            permissions=permissions,
            max_execution_time=max_execution_time,
        )

    @staticmethod
    def _random_suffix(length: int = 6) -> str:
        """Generate a random suffix for test data."""
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))  # NOSONAR: weak random in test/example  # NOSONAR — S2245: pseudo-random used for non-cryptographic purpose (test/cache key)  # NOSONAR — S7632: test function documented via class name / module path


class ExecutionErrorFactory:
    """Factory for creating ExecutionError instances."""

    @classmethod
    def create(
        cls,
        error: bool = True,
        type: str | None = None,
        message: str | None = None,
        action_required: str | None = None,
        can_retry: bool | None = None,
        details: dict[str, Any] | None = None,
    ) -> ExecutionError:
        """Create an ExecutionError instance with default values."""
        if type is None:
            type = f"ERROR_TYPE_{cls._random_suffix().upper()}"  # NOSONAR — S5806: type check acceptable
        if message is None:
            message = f"Error occurred: {cls._random_suffix()}"
        if can_retry is None:
            can_retry = secrets.choice([True, False])  # NOSONAR: weak random in test/example  # NOSONAR — S7632: test function documented via class name / module path

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
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))  # NOSONAR: weak random in test/example  # NOSONAR — S2245: pseudo-random used for non-cryptographic purpose (test/cache key)  # NOSONAR — S7632: test function documented via class name / module path


class ExecutionResultFactory:
    """Factory for creating ExecutionResult instances."""

    @classmethod
    def create(
        cls,
        success: bool | None = None,
        data: Any | None = None,
        error: ExecutionError | None = None,
        timestamp: datetime | None = None,
        duration_ms: float | None = None,
    ) -> ExecutionResult:
        """Create an ExecutionResult instance with default values."""
        if success is None:
            success = secrets.choice([True, False])  # NOSONAR: weak random in test/example  # NOSONAR — S7632: test function documented via class name / module path

        # Ensure mutual exclusivity of data and error
        if success:
            if error is not None:
                error = None
            if data is None:
                data = {"result": cls._random_suffix(), "value": 1 + secrets.randbelow(99)}  # NOSONAR: weak random in test/example  # NOSONAR — S7632: test function documented via class name / module path
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
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))  # NOSONAR: weak random in test/example  # NOSONAR — S7632: test function documented via class name / module path  # NOSONAR — S2245: pseudo-random used for non-cryptographic purpose (test/cache key)


class SkillManifestFactory:
    """Factory for creating SkillManifest instances."""

    @classmethod
    def create(
        cls,
        metadata: SkillMetadata | None = None,
        description: SkillDescription | None = None,
        requirements: SkillRequirements | None = None,
        version_compatibility: str | None = None,
        tags: list[str] | None = None,
    ) -> SkillManifest:
        """Create a SkillManifest instance with default values."""
        if metadata is None:
            metadata = SkillMetadataFactory.create()
        if description is None:
            description = SkillDescriptionFactory.create()
        if requirements is None:
            requirements = SkillRequirementsFactory.create()
        if version_compatibility is None:
            version_compatibility = f"{1}.{secrets.randbelow(9)}"  # NOSONAR: weak random in test/example  # NOSONAR — S7632: test function documented via class name / module path
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
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))  # NOSONAR: weak random in test/example  # NOSONAR — S2245: pseudo-random used for non-cryptographic purpose (test/cache key)  # NOSONAR — S7632: test function documented via class name / module path


# Convenience functions for common test scenarios
def create_valid_skill_manifest() -> SkillManifest:
    """Create a fully valid skill manifest for testing."""
    return SkillManifestFactory.create()


def create_valid_execution_result(success: bool = True) -> ExecutionResult:
    """Create a valid execution result for testing."""
    return ExecutionResultFactory.create(success=success)
