"""Integration tests for the AI agent skill validator and retry system."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest
from hypothesis import Phase, given, settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule
from pydantic import ValidationError

from core.retry import (
    async_network_retry,
    conditional_retry,
    network_retry,
    skill_retry,
)
from skills.skill_validator import (
    ExecutionError,
    ExecutionResult,
    SkillDescription,
    SkillManifest,
    SkillMetadata,
    SkillRequirements,
    validate_skill_manifest,
    validate_version_compatibility,
)


class RetryTestError(ImportError):
    pass


valid_name_strategy = st.text(
    min_size=1,
    max_size=30,
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_",
).filter(lambda value: value[0].isalpha())


valid_version_strategy = st.builds(
    lambda major, minor, patch: f"{major}.{minor}.{patch}",
    st.integers(min_value=0, max_value=99),
    st.integers(min_value=0, max_value=99),
    st.integers(min_value=0, max_value=999),
)


valid_author_strategy = st.text(
    min_size=1,
    max_size=30,
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_",
)


short_description_strategy = st.text(
    min_size=10,
    max_size=200,
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-.:,",
)


trigger_word_strategy = st.text(
    min_size=2,
    max_size=30,
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
).map(str.lower)


trigger_words_strategy = st.lists(
    trigger_word_strategy,
    min_size=1,
    max_size=10,
    unique=True,
)


dependencies_strategy = st.dictionaries(
    st.text(
        min_size=1,
        max_size=30,
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
    ).map(str.lower),
    st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_.>=<"),
    min_size=1,
    max_size=5,
)


requirements_strategy = st.builds(
    lambda dependencies, max_execution_time: SkillRequirements(
        python_version="3.10",
        dependencies=dependencies,
        max_execution_time=max_execution_time,
    ),
    dependencies_strategy,
    st.integers(min_value=1, max_value=3600),
)


tags_strategy = st.lists(
    st.text(
        min_size=2,
        max_size=20,
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
    ),
    min_size=0,
    max_size=10,
    unique=True,
)


def test_pydantic_validation_integration():
    created_at = datetime(2024, 1, 1, 12, 0, 0)
    updated_at = datetime(2024, 1, 2, 12, 0, 0)

    metadata = SkillMetadata(
        name="test_skill",
        version="1.0.0",
        author="test_author",
        created_at=created_at,
        updated_at=updated_at,
    )
    description = SkillDescription(
        short_description="Short description for integration testing",
        long_description="Long description used by the integration test.",
        trigger_words=["test", "integration", "skill"],
        use_cases=["Validate skill manifests"],
    )
    requirements = SkillRequirements(
        python_version="3.10",
        dependencies={"pytest": ">=7.0.0"},
        max_execution_time=60,
    )
    manifest = SkillManifest(
        metadata=metadata,
        description=description,
        requirements=requirements,
        version_compatibility="1.0",
        tags=["test", "integration"],
    )
    result = ExecutionResult(
        success=True,
        data={"result": "success", "value": 42},
        timestamp=created_at,
        duration_ms=123.0,
    )

    assert metadata.name == "test_skill"
    assert metadata.version == "1.0.0"
    assert metadata.author == "test_author"
    assert metadata.created_at == created_at
    assert metadata.updated_at == updated_at
    assert description.short_description == "Short description for integration testing"
    assert description.long_description == "Long description used by the integration test."
    assert {"test", "integration", "skill"}.issubset(set(description.trigger_words))
    assert description.use_cases == ["Validate skill manifests"]
    assert requirements.python_version == "3.10"
    assert requirements.dependencies["pytest"] == ">=7.0.0"
    assert requirements.max_execution_time == 60
    assert manifest.metadata.name == "test_skill"
    assert manifest.description.short_description == "Short description for integration testing"
    assert manifest.requirements is requirements
    assert manifest.version_compatibility == "1.0"
    assert manifest.tags == ["test", "integration"]
    assert result.success is True
    assert result.data == {"result": "success", "value": 42}
    assert result.error is None
    assert result.timestamp == created_at
    assert result.duration_ms == 123.0


@pytest.mark.parametrize(
    "metadata_data",
    [
        {"name": "test skill", "version": "1.0.0", "author": "test_author"},
        {"name": "test_skill", "version": "1.0", "author": "test_author"},
        {"name": "test_skill", "version": "1.0.0", "author": ""},
    ],
)
def test_invalid_metadata_is_rejected(metadata_data):
    with pytest.raises(ValidationError):
        SkillMetadata(**metadata_data)


@pytest.mark.parametrize(
    "description_data",
    [
        {"short_description": "short", "trigger_words": ["test"]},
        {"short_description": "valid description for testing", "trigger_words": []},
        {"short_description": "valid description for testing", "trigger_words": [""]},
    ],
)
def test_invalid_description_is_rejected(description_data):
    with pytest.raises(ValidationError):
        SkillDescription(**description_data)


@pytest.mark.parametrize(
    "requirements_data",
    [
        {"python_version": "3.10", "max_execution_time": 0},
        {"python_version": "3", "max_execution_time": 60},
    ],
)
def test_invalid_requirements_are_rejected(requirements_data):
    with pytest.raises(ValidationError):
        SkillRequirements(**requirements_data)


def test_execution_result_rejects_dict_errors_and_invalid_combinations():
    error = ExecutionError(
        type="validation_error",
        message="Validation failed",
        action_required="Fix the manifest",
        can_retry=False,
        details={"field": "metadata.version"},
    )

    with pytest.raises(ValidationError):
        ExecutionResult(
            success=True,
            data={"result": "success"},
            error=error,
        )

    with pytest.raises(ValidationError):
        ExecutionResult(
            success=False,
            data={"result": "should_not_exist"},
            error=error,
        )

    with pytest.raises(ValidationError):
        ExecutionResult(success=False, data={"result": "should_not_exist"})

    failed_result = ExecutionResult(
        success=False,
        error=ExecutionError(type="execution_error", message="Execution failed"),
        duration_ms=10.0,
    )

    assert failed_result.success is False
    assert failed_result.data is None
    assert isinstance(failed_result.error, ExecutionError)
    assert failed_result.error.type == "execution_error"
    assert failed_result.duration_ms == 10.0


def test_validate_skill_manifest_and_version_compatibility():
    manifest_data = {
        "metadata": {
            "name": "test_skill",
            "version": "1.0.0",
            "author": "test_author",
        },
        "description": {
            "short_description": "Short description for integration testing",
            "long_description": "Long description used by the integration test.",
            "trigger_words": ["test", "integration"],
            "use_cases": ["Validate skill manifests"],
        },
        "requirements": {
            "python_version": "3.10",
            "dependencies": {"pytest": ">=7.0.0"},
            "max_execution_time": 60,
        },
        "version_compatibility": "1.0",
        "tags": ["test", "integration"],
    }

    is_valid, error_message = validate_skill_manifest(manifest_data)

    assert is_valid is True
    assert error_message is None
    assert validate_version_compatibility("1.2", "1.3") is True
    assert validate_version_compatibility("2.0", "1.9") is False


def test_invalid_manifest_data_is_rejected():
    invalid_manifest_data = {
        "metadata": {
            "name": "bad name",
            "version": "1.0.0",
            "author": "test_author",
        },
        "description": {
            "short_description": "Short description for integration testing",
            "trigger_words": ["test"],
        },
    }

    is_valid, error_message = validate_skill_manifest(invalid_manifest_data)

    assert is_valid is False
    assert error_message


def test_retry_mechanisms_sync():
    network_call_count = 0

    @network_retry(
        max_attempts=3,
        max_delay=1,
        multiplier=0,
        exceptions=(RetryTestError,),
    )
    def network_failing_function():
        nonlocal network_call_count
        network_call_count += 1
        if network_call_count < 3:
            raise RetryTestError(f"Attempt {network_call_count} failed")
        return "network success"

    skill_call_count = 0

    @skill_retry(
        max_attempts=2,
        max_delay=1,
        multiplier=0,
        exceptions=(RetryTestError,),
    )
    def always_failing_skill_function():
        nonlocal skill_call_count
        skill_call_count += 1
        raise RetryTestError(f"Attempt {skill_call_count} failed")

    with patch("tenacity.nap.sleep"):
        assert network_failing_function() == "network success"
        with pytest.raises(RetryTestError):
            always_failing_skill_function()

    assert network_call_count == 3
    assert skill_call_count == 2


@pytest.mark.asyncio
async def test_retry_mechanisms_async():
    call_count = 0

    @async_network_retry(max_attempts=2, max_delay=0, multiplier=0)
    async def async_failing_function():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ConnectionError(f"Attempt {call_count} failed")
        return "async success"

    result = await async_failing_function()

    assert result == "async success"
    assert call_count == 2


def test_conditional_retry_sync():
    call_count = 0

    @conditional_retry(lambda value: value is False, max_attempts=3, max_delay=1)
    def eventually_true():
        nonlocal call_count
        call_count += 1
        return call_count == 3

    with patch("tenacity.nap.sleep"):
        assert eventually_true() is True

    assert call_count == 3


@settings(max_examples=50, deadline=1000, phases=[Phase.generate, Phase.shrink])
@given(
    name=valid_name_strategy,
    version=valid_version_strategy,
    author=valid_author_strategy,
    short_description=short_description_strategy,
    trigger_words=trigger_words_strategy,
    requirements=requirements_strategy,
    tags=tags_strategy,
)
def test_property_based_manifest_creation(
    name,
    version,
    author,
    short_description,
    trigger_words,
    requirements,
    tags,
):
    metadata = SkillMetadata(name=name, version=version, author=author)
    description = SkillDescription(
        short_description=short_description,
        trigger_words=trigger_words,
    )
    manifest = SkillManifest(
        metadata=metadata,
        description=description,
        requirements=requirements,
        version_compatibility="1.0",
        tags=tags,
    )
    expected_tags = [tag for tag in tags if len(tag) >= 2]

    assert manifest.metadata.name == name.lower()
    assert manifest.metadata.version == version
    assert manifest.metadata.author == author
    assert manifest.description.short_description == short_description
    assert set(manifest.description.trigger_words) == set(trigger_words)
    assert manifest.requirements.python_version == "3.10"
    assert manifest.requirements.dependencies == requirements.dependencies
    assert manifest.requirements.max_execution_time == requirements.max_execution_time
    assert manifest.version_compatibility == "1.0"
    assert manifest.tags == expected_tags


class SkillIntegrationStateMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.skills: dict[str, SkillManifest] = {}
        self.executions: list[ExecutionResult] = []

    @rule(
        name=valid_name_strategy,
        version=valid_version_strategy,
        author=valid_author_strategy,
        short_description=short_description_strategy,
        trigger_words=trigger_words_strategy,
    )
    def add_valid_skill(self, name, version, author, short_description, trigger_words):
        metadata = SkillMetadata(name=name, version=version, author=author)
        description = SkillDescription(
            short_description=short_description,
            trigger_words=trigger_words,
        )
        requirements = SkillRequirements(
            python_version="3.10",
            dependencies={"pytest": ">=7.0.0"},
            max_execution_time=60,
        )
        manifest = SkillManifest(
            metadata=metadata,
            description=description,
            requirements=requirements,
            version_compatibility="1.0",
            tags=["state", "machine"],
        )

        self.skills[manifest.metadata.name] = manifest

    @rule(
        skill_name=valid_name_strategy,
        success=st.booleans(),
    )
    def execute_skill(self, skill_name, success):
        if skill_name not in self.skills:
            return

        if success:
            result = ExecutionResult(
                success=True,
                data={"executed": skill_name, "success": True},
                duration_ms=1.0,
            )
        else:
            result = ExecutionResult(
                success=False,
                error=ExecutionError(
                    type="execution_error",
                    message=f"Failed to execute {skill_name}",
                    can_retry=True,
                ),
                duration_ms=1.0,
            )

        self.executions.append(result)

    @invariant()
    def stored_manifests_are_valid(self):
        for manifest in self.skills.values():
            assert manifest.description.trigger_words
            assert manifest.requirements.python_version == "3.10"
            assert manifest.requirements.max_execution_time == 60
            assert manifest.tags == ["state", "machine"]

    @invariant()
    def execution_results_follow_schema(self):
        for result in self.executions:
            assert isinstance(result, ExecutionResult)
            if result.success:
                assert result.data is not None
                assert result.error is None
            else:
                assert result.data is None
                assert isinstance(result.error, ExecutionError)


TestSkillIntegrationStateMachine = SkillIntegrationStateMachine.TestCase


def test_schema_serialization():
    created_at = datetime(2024, 1, 1, 12, 0, 0)
    updated_at = datetime(2024, 1, 2, 12, 0, 0)

    metadata = SkillMetadata(
        name="test_skill",
        version="1.2.3",
        author="test_author",
        created_at=created_at,
        updated_at=updated_at,
    )
    description = SkillDescription(
        short_description="Test skill for schema serialization",
        long_description="Detailed schema serialization description.",
        trigger_words=["test", "serialize"],
        use_cases=["Serialize manifests"],
    )
    requirements = SkillRequirements(
        python_version="3.10",
        dependencies={"pytest": ">=7.0.0"},
        max_execution_time=90,
    )
    manifest = SkillManifest(
        metadata=metadata,
        description=description,
        requirements=requirements,
        version_compatibility="1.0",
        tags=["test", "integration"],
    )
    result = ExecutionResult(
        success=True,
        data={"value": 42},
        timestamp=created_at,
        duration_ms=123.0,
    )

    dumped = manifest.model_dump(mode="json")
    serialized_result = result.to_dict()

    assert dumped["metadata"]["name"] == "test_skill"
    assert dumped["metadata"]["created_at"] == created_at.isoformat()
    assert dumped["metadata"]["updated_at"] == updated_at.isoformat()
    assert dumped["description"]["short_description"] == "Test skill for schema serialization"
    assert dumped["description"]["long_description"] == "Detailed schema serialization description."
    assert set(dumped["description"]["trigger_words"]) == {"test", "serialize"}
    assert dumped["requirements"]["python_version"] == "3.10"
    assert dumped["requirements"]["dependencies"] == {"pytest": ">=7.0.0"}
    assert dumped["requirements"]["max_execution_time"] == 90
    assert dumped["version_compatibility"] == "1.0"
    assert dumped["tags"] == ["test", "integration"]
    assert serialized_result["success"] is True
    assert serialized_result["data"] == {"value": 42}
    assert serialized_result["error"] is None
    assert serialized_result["timestamp"] == created_at.isoformat()
    assert serialized_result["duration_ms"] == 123.0

    schema = manifest.model_json_schema()

    assert "properties" in schema
    assert {"metadata", "description", "requirements", "version_compatibility", "tags"}.issubset(
        schema["properties"]
    )
