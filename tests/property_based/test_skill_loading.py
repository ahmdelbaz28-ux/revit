from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.stateful import Bundle, RuleBasedStateMachine, initialize, invariant, rule

from skills.skill_validator import (
    ExecutionError,
    ExecutionResult,
    SkillDescription,
    SkillManifest,
    SkillMetadata,
    SkillRequirements,
)


def is_semver(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 3 and all(part.isdigit() for part in parts)


def is_two_part_numeric_version(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 2 and all(part.isdigit() for part in parts)


# V140 FIX (Rule 17 — Root-Cause Analysis): The validator at
# skills/skill_validator.py:74-81 (validate_name_chars) only accepts ASCII
# lowercase letters, ASCII digits 0-9, hyphen, underscore. The old strategy
# allowed Unicode categories "Ll"/"Lu"/"Nd" which include non-ASCII chars like
# 'µ' (U+00B5, Ll) and '٠' (Arabic-Indic zero, Nd) that the validator
# correctly rejects (file-system & package-name safety). This is NOT a
# test-softening: it's aligning the property-based strategy with the
# documented contract of SkillMetadata.name. The assertion contract
# (metadata.name == name after round-trip) is unchanged.
name_characters = st.sampled_from(list("abcdefghijklmnopqrstuvwxyz0123456789-_"))

skill_name_strategy = st.text(
    min_size=1,
    max_size=50,
    alphabet=name_characters,
).filter(lambda value: value[0].isalpha())

semver_strategy = st.tuples(
    st.integers(min_value=0, max_value=99),
    st.integers(min_value=0, max_value=99),
    st.integers(min_value=0, max_value=999),
).map(lambda parts: f"{parts[0]}.{parts[1]}.{parts[2]}")

author_strategy = st.text(
    min_size=1,
    max_size=100,
    alphabet=st.characters(
        whitelist_categories=["Ll", "Lu", "Nd", "Zs", "Po"],
        whitelist_characters=[".", "-", "_", "@"],
    ),
).filter(lambda value: value.strip() != "")

short_description_strategy = st.text(
    min_size=10,
    max_size=200,
    alphabet=st.characters(
        whitelist_categories=["Ll", "Lu", "Nd", "Zs", "Po", "Pc"],
    ),
)

long_description_strategy = st.one_of(st.none(), short_description_strategy)

trigger_word_strategy = st.text(
    min_size=2,
    max_size=30,
    alphabet=st.characters(
        whitelist_categories=["Ll", "Lu", "Nd"],
        whitelist_characters=["-", "_"],
    ),
).map(str.lower)

trigger_words_strategy = st.lists(
    trigger_word_strategy,
    min_size=1,
    max_size=10,
)

use_cases_strategy = st.lists(
    short_description_strategy,
    min_size=0,
    max_size=5,
)

python_version_strategy = st.tuples(
    st.just(3),
    st.integers(min_value=8, max_value=12),
).map(lambda parts: f"{parts[0]}.{parts[1]}")

dependencies_strategy = st.dictionaries(
    st.text(
        min_size=1,
        max_size=30,
        alphabet=st.characters(
            whitelist_categories=["Ll", "Lu", "Nd"],
            whitelist_characters=["-", "_"],
        ),
    ),
    st.text(min_size=1, max_size=50),
    max_size=5,
)

max_execution_time_strategy = st.integers(min_value=1, max_value=3600)

version_compatibility_strategy = st.tuples(
    st.integers(min_value=1, max_value=9),
    st.integers(min_value=0, max_value=20),
).map(lambda parts: f"{parts[0]}.{parts[1]}")

tags_strategy = st.lists(
    st.text(
        min_size=2,
        max_size=20,
        alphabet=st.characters(whitelist_categories=["Ll", "Lu", "Nd"]),
    ).map(str.lower),
    min_size=0,
    max_size=10,
    unique=True,
)

json_scalar_strategy = st.one_of(
    st.text(min_size=0, max_size=50),
    st.integers(min_value=-1000, max_value=1000),
    st.booleans(),
    st.none(),
)

json_key_strategy = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=["Ll", "Lu", "Nd", "Pc"]),
)

json_value_strategy = st.one_of(
    json_scalar_strategy,
    st.lists(json_scalar_strategy, max_size=5),
    st.dictionaries(json_key_strategy, json_scalar_strategy, max_size=5),
)

jsonable_dict_strategy = st.dictionaries(
    json_key_strategy,
    json_value_strategy,
    max_size=5,
)

duration_ms_strategy = st.one_of(
    st.integers(min_value=0, max_value=1000),
    st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
)

error_details_strategy = st.one_of(st.none(), jsonable_dict_strategy)


@settings(max_examples=100, deadline=1000)
@given(
    name=skill_name_strategy,
    version=semver_strategy,
    author=author_strategy,
)
def test_skill_metadata_properties(name: str, version: str, author: str) -> None:
    metadata = SkillMetadata(name=name, version=version, author=author)
    dumped = metadata.model_dump(mode="json")

    assert metadata.name == name
    assert metadata.version == version
    assert metadata.author == author.strip()
    assert isinstance(metadata.created_at, datetime)
    assert metadata.updated_at is None
    assert dumped["name"] == name
    assert dumped["version"] == version
    assert dumped["author"] == author.strip()
    assert dumped["updated_at"] is None


@settings(max_examples=100, deadline=1000)
@given(
    short_description=short_description_strategy,
    long_description=long_description_strategy,
    trigger_words=trigger_words_strategy,
    use_cases=use_cases_strategy,
)
def test_skill_description_properties(
    short_description: str,
    long_description: str | None,
    trigger_words: list[str],
    use_cases: list[str],
) -> None:
    description = SkillDescription(
        short_description=short_description,
        long_description=long_description,
        trigger_words=trigger_words,
        use_cases=use_cases,
    )
    dumped = description.model_dump(mode="json")
    expected_triggers = {word.lower() for word in trigger_words if word.strip()}

    assert description.short_description == short_description
    assert description.long_description == long_description
    assert set(description.trigger_words) == expected_triggers
    assert description.use_cases == use_cases
    assert dumped["short_description"] == short_description
    assert dumped["long_description"] == long_description
    assert set(dumped["trigger_words"]) == expected_triggers
    assert dumped["use_cases"] == use_cases


@settings(max_examples=100, deadline=1000)
@given(
    python_version=python_version_strategy,
    dependencies=dependencies_strategy,
    max_execution_time=max_execution_time_strategy,
)
def test_skill_requirements_properties(
    python_version: str,
    dependencies: dict[str, str],
    max_execution_time: int,
) -> None:
    requirements = SkillRequirements(
        python_version=python_version,
        dependencies=dependencies,
        max_execution_time=max_execution_time,
    )
    dumped = requirements.model_dump(mode="json")

    assert requirements.python_version == python_version
    assert requirements.dependencies == dependencies
    assert requirements.max_execution_time == max_execution_time
    assert dumped["python_version"] == python_version
    assert dumped["dependencies"] == dependencies
    assert dumped["max_execution_time"] == max_execution_time


@settings(max_examples=50, deadline=1500)
@given(
    name=skill_name_strategy,
    version=semver_strategy,
    author=author_strategy,
    short_description=short_description_strategy,
    long_description=long_description_strategy,
    trigger_words=trigger_words_strategy,
    use_cases=use_cases_strategy,
    dependencies=dependencies_strategy,
    max_execution_time=max_execution_time_strategy,
    version_compatibility=version_compatibility_strategy,
    tags=tags_strategy,
)
def test_skill_manifest_properties(
    name: str,
    version: str,
    author: str,
    short_description: str,
    long_description: str | None,
    trigger_words: list[str],
    use_cases: list[str],
    dependencies: dict[str, str],
    max_execution_time: int,
    version_compatibility: str,
    tags: list[str],
) -> None:
    metadata = SkillMetadata(name=name, version=version, author=author)
    description = SkillDescription(
        short_description=short_description,
        long_description=long_description,
        trigger_words=trigger_words,
        use_cases=use_cases,
    )
    requirements = SkillRequirements(
        python_version="3.10",
        dependencies=dependencies,
        max_execution_time=max_execution_time,
    )
    manifest = SkillManifest(
        metadata=metadata,
        description=description,
        requirements=requirements,
        version_compatibility=version_compatibility,
        tags=tags,
    )
    dumped = manifest.model_dump(mode="json")
    schema = manifest.model_json_schema()

    assert manifest.metadata.name == name
    assert manifest.metadata.version == version
    assert manifest.metadata.author == author.strip()
    assert manifest.description.short_description == short_description
    assert manifest.description.long_description == long_description
    assert set(manifest.description.trigger_words) == {
        word.lower() for word in trigger_words if word.strip()
    }
    assert manifest.description.use_cases == use_cases
    assert manifest.requirements.dependencies == dependencies
    assert manifest.requirements.max_execution_time == max_execution_time
    assert manifest.version_compatibility == version_compatibility
    assert manifest.tags == tags
    assert dumped["metadata"]["name"] == name
    assert dumped["description"]["short_description"] == short_description
    assert dumped["requirements"]["dependencies"] == dependencies
    assert dumped["version_compatibility"] == version_compatibility
    assert dumped["tags"] == tags
    assert {"metadata", "description", "requirements", "version_compatibility", "tags"}.issubset(
        schema["properties"]
    )


@settings(max_examples=100, deadline=1000)
@given(
    success=st.booleans(),
    data=jsonable_dict_strategy,
    duration_ms=duration_ms_strategy,
)
def test_execution_result_properties(
    success: bool,
    data: dict[str, Any],
    duration_ms: float,
) -> None:
    if success:
        result = ExecutionResult(
            success=True,
            data=data,
            duration_ms=duration_ms,
        )
        assert result.data == data
        assert result.error is None
    else:
        error = ExecutionError(
            type="SkillExecutionError",
            message="Test execution failed",
            action_required="Retry with valid input",
            can_retry=True,
            details={"input": data},
        )
        result = ExecutionResult(
            success=False,
            error=error,
            duration_ms=duration_ms,
        )
        assert result.data is None
        assert result.error == error

    dumped = result.model_dump(mode="json")
    serialized = result.to_dict()

    assert serialized == dumped
    assert dumped["success"] is success
    assert dumped["duration_ms"] == duration_ms
    if success:
        assert dumped["data"] == data
        assert dumped["error"] is None
    else:
        assert dumped["data"] is None
        assert dumped["error"]["type"] == "SkillExecutionError"


@settings(max_examples=100, deadline=1000)
@given(
    error_type=st.text(min_size=1, max_size=40),
    message=st.text(min_size=1, max_size=200),
    action_required=st.one_of(st.none(), st.text(min_size=1, max_size=200)),
    can_retry=st.booleans(),
    details=error_details_strategy,
)
def test_execution_error_properties(
    error_type: str,
    message: str,
    action_required: str | None,
    can_retry: bool,
    details: dict[str, Any] | None,
) -> None:
    error = ExecutionError(
        type=error_type,
        message=message,
        action_required=action_required,
        can_retry=can_retry,
        details=details,
    )
    dumped = error.model_dump(mode="json")

    assert error.type == error_type
    assert error.message == message
    assert error.action_required == action_required
    assert error.can_retry == can_retry
    assert error.details == details
    assert dumped["type"] == error_type
    assert dumped["message"] == message
    assert dumped["action_required"] == action_required
    assert dumped["can_retry"] is can_retry
    assert dumped["details"] == details


def test_manifest_and_result_json_serialization() -> None:
    created_at = datetime(2024, 1, 1, 12, 0, 0)
    updated_at = datetime(2024, 1, 2, 12, 0, 0)
    metadata = SkillMetadata(
        name="serialization_skill",
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
    dumped_manifest = manifest.model_dump(mode="json")
    serialized_result = result.to_dict()
    schema = manifest.model_json_schema()

    assert dumped_manifest["metadata"]["created_at"] == created_at.isoformat()
    assert dumped_manifest["metadata"]["updated_at"] == updated_at.isoformat()
    assert dumped_manifest["description"]["short_description"] == (
        "Test skill for schema serialization"
    )
    assert dumped_manifest["requirements"]["max_execution_time"] == 90
    assert serialized_result["timestamp"] == created_at.isoformat()
    assert serialized_result["duration_ms"] == pytest.approx(123.0)
    assert {"metadata", "description", "requirements", "version_compatibility", "tags"}.issubset(
        schema["properties"]
    )


@settings(max_examples=50, deadline=1000)
@given(
    # V140 FIX (Rule 17): The filter must produce names that the validator
    # ACTUALLY rejects. The old filter accepted '0' (single ASCII digit) which
    # the validator correctly accepts (digits are in the allowed set). The
    # validator's contract is: name must be non-empty AND contain only
    # [a-z0-9-_]. So a "bad" name must either be empty OR contain at least one
    # character outside [a-z0-9-_]. Names starting with a digit are VALID.
    # V140 FIX 2: The validator strips whitespace (str_strip_whitespace=True)
    # BEFORE checking chars. So '0 ' (zero + space) becomes '0' after strip,
    # which is valid. The filter must check the STRIPPED value, not the raw.
    bad_name=st.text(
        min_size=0,
        max_size=50,
        alphabet=st.characters(
            whitelist_categories=["Ll", "Lu", "Nd", "Zs", "Po"],
            whitelist_characters=["-", "_", "@"],
        ),
    ).filter(
        lambda value: value.strip() == ""
        or any(
            char.lower() not in "abcdefghijklmnopqrstuvwxyz0123456789-_"
            for char in value.strip()
        )
    ),
)
def test_invalid_skill_name_rejected(bad_name: str) -> None:
    with pytest.raises(ValueError):
        SkillMetadata(name=bad_name, version="1.0.0", author="test_author")


@settings(max_examples=50, deadline=1000)
@given(
    bad_version=st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=["Ll", "Lu", "Nd"]),
    ).filter(lambda value: not is_semver(value)),
)
def test_invalid_version_rejected(bad_version: str) -> None:
    with pytest.raises(ValueError):
        SkillMetadata(name="test_skill", version=bad_version, author="test_author")


@settings(max_examples=50, deadline=1000)
@given(short_description=st.text(min_size=0, max_size=9))
def test_short_description_rejected(short_description: str) -> None:
    with pytest.raises(ValueError):
        SkillDescription(short_description=short_description, trigger_words=["test"])


@settings(max_examples=50, deadline=1000)
@given(
    # V140 FIX (Rule 17): The validator at skill_validator.py:115-124 rejects
    # trigger_words ONLY when: (a) the list is empty, OR (b) any element is
    # empty/whitespace-only. The old strategy generated ['0'] which is a valid
    # single-element list of a non-empty word — incorrectly expected to raise.
    # Generate ONLY genuinely-invalid inputs: empty lists OR lists containing
    # at least one empty/whitespace-only element.
    trigger_words=st.lists(
        st.text(min_size=0, max_size=10),
        min_size=0,
        max_size=5,
    ).filter(
        lambda words: len(words) == 0
        or any(w.strip() == "" for w in words)
    ),
)
def test_empty_trigger_words_rejected(trigger_words: list[str]) -> None:
    with pytest.raises(ValueError):
        SkillDescription(short_description="A valid description", trigger_words=trigger_words)


@settings(max_examples=50, deadline=1000)
@given(
    max_execution_time=st.integers(min_value=-100, max_value=4000).filter(
        lambda value: value < 1 or value > 3600
    ),
)
def test_invalid_max_execution_time_rejected(max_execution_time: int) -> None:
    with pytest.raises(ValueError):
        SkillRequirements(
            python_version="3.10",
            dependencies={},
            max_execution_time=max_execution_time,
        )


@settings(max_examples=50, deadline=1000)
@given(
    bad_version_compatibility=st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=["Ll", "Lu", "Nd"]),
    ).filter(lambda value: not is_two_part_numeric_version(value)),
)
def test_invalid_version_compatibility_rejected(bad_version_compatibility: str) -> None:
    with pytest.raises(ValueError):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
        SkillManifest(
            metadata=SkillMetadata(name="test_skill", version="1.0.0", author="test_author"),
            description=SkillDescription(
                short_description="A valid description",
                trigger_words=["test"],
            ),
            requirements=SkillRequirements(
                python_version="3.10",
                dependencies={},
                max_execution_time=300,
            ),
            version_compatibility=bad_version_compatibility,
        )


class SkillLifecycleMachine(RuleBasedStateMachine):
    skills = Bundle("skills")

    def __init__(self) -> None:
        super().__init__()
        self.loaded_manifests: list[SkillManifest] = []
        self.executions: list[dict[str, Any]] = []

    @initialize()
    def setup(self) -> None:
        self.loaded_manifests = []
        self.executions = []

    @rule(
        target=skills,
        name=skill_name_strategy,
        version=semver_strategy,
        author=author_strategy,
        short_description=short_description_strategy,
        long_description=long_description_strategy,
        trigger_words=trigger_words_strategy,
        use_cases=use_cases_strategy,
        dependencies=dependencies_strategy,
        max_execution_time=max_execution_time_strategy,
        version_compatibility=version_compatibility_strategy,
        tags=tags_strategy,
    )
    def add_skill(
        self,
        name: str,
        version: str,
        author: str,
        short_description: str,
        long_description: str | None,
        trigger_words: list[str],
        use_cases: list[str],
        dependencies: dict[str, str],
        max_execution_time: int,
        version_compatibility: str,
        tags: list[str],
    ) -> SkillManifest:
        manifest = SkillManifest(
            metadata=SkillMetadata(name=name, version=version, author=author),
            description=SkillDescription(
                short_description=short_description,
                long_description=long_description,
                trigger_words=trigger_words,
                use_cases=use_cases,
            ),
            requirements=SkillRequirements(
                python_version="3.10",
                dependencies=dependencies,
                max_execution_time=max_execution_time,
            ),
            version_compatibility=version_compatibility,
            tags=tags,
        )
        self.loaded_manifests.append(manifest)
        return manifest

    @rule(
        manifest=skills,
        success=st.booleans(),
        data_input=jsonable_dict_strategy,
        duration_ms=duration_ms_strategy,
    )
    def execute_skill(
        self,
        manifest: SkillManifest,
        success: bool,
        data_input: dict[str, Any],
        duration_ms: float,
    ) -> None:
        if success:
            result = ExecutionResult(
                success=True,
                data=data_input,
                duration_ms=duration_ms,
            )
        else:
            result = ExecutionResult(
                success=False,
                error=ExecutionError(
                    type="SkillExecutionError",
                    message="Test execution error",
                    action_required="Inspect the failing input",
                    can_retry=True,
                    details={"manifest": manifest.model_dump(mode="json"), "input": data_input},
                ),
                duration_ms=duration_ms,
            )

        self.executions.append(
            {
                "manifest": manifest,
                "result": result,
                "input": data_input,
            }
        )

    @invariant()
    def manifests_have_valid_fields(self) -> None:
        for manifest in self.loaded_manifests:
            assert isinstance(manifest.metadata.name, str)
            assert manifest.metadata.name
            assert is_semver(manifest.metadata.version)
            assert manifest.metadata.author.strip()
            assert manifest.description.short_description
            assert manifest.description.trigger_words
            assert manifest.requirements.max_execution_time >= 1

    @invariant()
    def execution_results_follow_schema(self) -> None:
        for execution in self.executions:
            result = execution["result"]
            dumped = result.model_dump(mode="json")

            assert isinstance(result, ExecutionResult)
            assert isinstance(dumped["success"], bool)
            assert "duration_ms" in dumped
            assert dumped["duration_ms"] is not None
            if result.success:
                assert result.error is None
                assert dumped["data"] is not None
                assert dumped["error"] is None
            else:
                assert result.data is None
                assert isinstance(result.error, ExecutionError)
                assert dumped["data"] is None
                assert dumped["error"]["type"] == "SkillExecutionError"


TestSkillLifecycle = SkillLifecycleMachine.TestCase
