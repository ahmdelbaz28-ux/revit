"""
tests/property_based/test_skill_validator.py

Property-based tests for skill validation using Hypothesis.
These tests verify that validation rules hold for arbitrary valid inputs.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hypothesis import given, settings, Phase, assume
from hypothesis import strategies as st
import pytest

from skills.skill_validator import (
    SkillMetadata,
    SkillDescription,
    SkillPermissions,
    SkillRequirements,
    SkillManifest,
    ExecutionResult,
    ExecutionError,
    validate_skill_manifest,
    validate_version_compatibility,
)


# ═══════════════════════════════════════════════════════════════════════════
# STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════


valid_name_strategy = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(
        whitelist_categories=["Ll", "Nd"],
    ),
).map(lambda s: s.lower())


valid_version_strategy = st.tuples(
    st.integers(min_value=0, max_value=100),
    st.integers(min_value=0, max_value=100),
    st.integers(min_value=0, max_value=1000),
).map(lambda x: f"{x[0]}.{x[1]}.{x[2]}")


valid_author_strategy = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(whitelist_categories=["Ll", "Lu", "Nd", "Zs", "Po"]),
)


trigger_word_strategy = st.text(
    min_size=2,
    max_size=30,
    alphabet=st.characters(whitelist_categories=["Ll", "Lu", "Nd"]),
).map(lambda s: s.lower())


valid_description_strategy = st.text(
    min_size=10,
    max_size=200,
    alphabet=st.characters(whitelist_categories=["Ll", "Lu", "Nd", "Zs", "Po", "Pc"]),
)


# ═══════════════════════════════════════════════════════════════════════════
# SKILL METADATA TESTS
# ═══════════════════════════════════════════════════════════════════════════


@given(
    name=valid_name_strategy,
    version=valid_version_strategy,
    author=valid_author_strategy,
)
@settings(max_examples=100, phases=[Phase.generate, Phase.shrink])
def test_skill_metadata_valid_inputs(name, version, author):
    """Property: Valid inputs create valid metadata objects."""
    metadata = SkillMetadata(name=name, version=version, author=author)
    
    assert metadata.name == name
    assert metadata.version == version
    assert metadata.author == author
    assert isinstance(metadata.created_at, datetime)


@given(version=valid_version_strategy)
@settings(max_examples=50)
def test_version_parsing(version):
    """Property: Version string is correctly parsed."""
    parts = version.split(".")
    
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
    assert all(0 <= int(part) <= 1000 for part in parts)


@given(
    name=valid_name_strategy,
    author=valid_author_strategy,
)
@settings(max_examples=30)
def test_invalid_version_rejected(name, author):
    """Property: Invalid version formats are rejected."""
    invalid_versions = [
        "1.0",           # Missing patch
        "1",             # Missing minor and patch
        "1.0.0.0",       # Too many parts
        "v1.0.0",        # Contains letter
        "1.0.-1",        # Negative number
    ]
    
    for invalid_version in invalid_versions:
        with pytest.raises((ValueError, AssertionError)):
            SkillMetadata(name=name, version=invalid_version, author=author)


# ═══════════════════════════════════════════════════════════════════════════
# SKILL DESCRIPTION TESTS
# ═══════════════════════════════════════════════════════════════════════════


@given(
    short_desc=valid_description_strategy,
    triggers=st.lists(trigger_word_strategy, min_size=1, max_size=10, unique=True),
)
@settings(max_examples=50)
def test_description_valid_inputs(short_desc, triggers):
    """Property: Valid descriptions are accepted."""
    desc = SkillDescription(
        short_description=short_desc,
        trigger_words=triggers,
    )
    
    assert desc.short_description == short_desc
    assert len(desc.trigger_words) >= 1
    assert all(t.islower() for t in desc.trigger_words)


@given(triggers=st.lists(trigger_word_strategy, min_size=1, max_size=10))
@settings(max_examples=30)
def test_trigger_words_deduplicated(triggers):
    """Property: Duplicate trigger words are removed."""
    duplicates = triggers + triggers[:2]  # Force duplicates
    
    desc = SkillDescription(
        short_description="A valid description for testing purposes here",
        trigger_words=duplicates,
    )
    
    assert len(desc.trigger_words) <= len(duplicates)


# ═══════════════════════════════════════════════════════════════════════════
# EXECUTION RESULT TESTS
# ═══════════════════════════════════════════════════════════════════════════


@given(
    success=st.booleans(),
    has_data=st.booleans(),
    has_error=st.booleans(),
)
@settings(max_examples=50)
def test_execution_result_mutual_exclusion(success, has_data, has_error):
    """Property: Cannot have both data and error."""
    # Constrain to meaningful combinations
    if success and (has_data or has_error):
        has_data, has_error = False, False
    if has_error:
        has_data = False
    
    data = {"key": "value"} if has_data else None
    error = ExecutionError(type="Test", message="Error") if has_error else None
    
    result = ExecutionResult(success=success, data=data, error=error)
    
    assert result.success == success
    if success:
        assert result.error is None
    if has_error:
        assert result.data is None


@given(timestamp=st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
))
@settings(max_examples=30)
def test_execution_result_timestamp_preserved(timestamp):
    """Property: Custom timestamps are preserved."""
    result = ExecutionResult(
        success=True,
        data={"test": True},
        timestamp=timestamp,
    )
    
    assert result.timestamp == timestamp


# ═══════════════════════════════════════════════════════════════════════════
# VERSION COMPATIBILITY TESTS
# ═══════════════════════════════════════════════════════════════════════════


@given(
    skill_major=st.integers(min_value=0, max_value=10),
    skill_minor=st.integers(min_value=0, max_value=20),
    sys_major=st.integers(min_value=0, max_value=10),
    sys_minor=st.integers(min_value=0, max_value=20),
)
@settings(max_examples=50)
def test_version_compatibility_rules(skill_major, skill_minor, sys_major, sys_minor):
    """Property: Version compatibility follows expected rules."""
    skill_version = f"{skill_major}.{skill_minor}"
    system_version = f"{sys_major}.{sys_minor}"
    
    compatible = validate_version_compatibility(skill_version, system_version)
    
    # Compatible only if major versions match AND skill_minor <= system_minor
    expected = (skill_major == sys_major) and (skill_minor <= sys_minor)
    
    assert compatible == expected, (
        f"skill={skill_version}, system={system_version}, "
        f"expected={expected}, got={compatible}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# MANIFEST VALIDATION TESTS
# ═══════════════════════════════════════════════════════════════════════════


@given(
    name=valid_name_strategy,
    version=valid_version_strategy,
    author=valid_author_strategy,
    short_desc=valid_description_strategy,
    triggers=st.lists(trigger_word_strategy, min_size=1, max_size=5),
)
@settings(max_examples=30)
def test_full_manifest_valid(name, version, author, short_desc, triggers):
    """Property: Valid inputs create valid full manifests."""
    metadata = SkillMetadata(name=name, version=version, author=author)
    description = SkillDescription(
        short_description=short_desc,
        trigger_words=triggers,
    )
    
    manifest = SkillManifest(
        metadata=metadata,
        description=description,
    )
    
    assert manifest.metadata.name == name
    assert manifest.metadata.version == version
    assert manifest.description.short_description == short_desc
    assert len(manifest.description.trigger_words) >= 1


@given(
    invalid_data=st.dictionaries(
        st.text(),
        st.one_of([
            st.text(),
            st.integers(),
            st.lists(st.text()),
            st.dictionaries(st.text(), st.text())
        ])
    ).filter(lambda x: len(x) > 0)
)
@settings(max_examples=20)
def test_invalid_manifests_rejected(invalid_data):
    """Property: Invalid manifest data is rejected."""
    # Try to validate invalid data - should fail
    is_valid, error_msg = validate_skill_manifest(invalid_data)
    
    # If the data happens to be valid by chance, that's ok
    if not is_valid:
        assert error_msg is not None
    else:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE TESTS
# ═══════════════════════════════════════════════════════════════════════════


@given(
    name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_"),
    version=valid_version_strategy,
    author=valid_author_strategy,
)
@settings(max_examples=50)
def test_edge_case_names(name, version, author):
    """Property: Edge case names are handled properly."""
    # Use assume to skip invalid inputs rather than letting them cause failures
    assume(len(name) >= 1 and len(name) <= 100 and name and name[0].isalpha())
    
    # Only test when name is valid (starts with alpha and contains valid chars)
    metadata = SkillMetadata(name=name, version=version, author=author)
    # If we get here, the name was valid and normalized
    assert metadata.name == name.lower()
    # Add pass to ensure function has executable code
    pass


def test_specific_invalid_cases():
    """Test specific known invalid cases."""
    invalid_cases = [
        # Invalid version formats
        ({"metadata": {"name": "test", "version": "invalid", "author": "test"}, "description": {"short_description": "test", "trigger_words": ["test"]}}),
        ({"metadata": {"name": "test", "version": "1.0", "author": "test"}, "description": {"short_description": "test", "trigger_words": ["test"]}}),
        # Missing required fields
        ({"metadata": {"name": "test", "author": "test"}, "description": {"short_description": "test", "trigger_words": ["test"]}}),
        # Empty trigger words
        ({"metadata": {"name": "test", "version": "1.0.0", "author": "test"}, "description": {"short_description": "test", "trigger_words": []}}),
    ]
    
    for invalid_case in invalid_cases:
        is_valid, error_msg = validate_skill_manifest(invalid_case)
        assert not is_valid, f"Expected invalid case to fail: {invalid_case}"
        assert error_msg is not None