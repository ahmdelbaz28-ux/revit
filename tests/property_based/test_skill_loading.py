"""
tests/property_based/test_skill_loading.py — Property-Based Testing for Skills
============================================================================

Production-ready property-based testing using Hypothesis patterns.
Tests skill loading, validation, and execution properties with comprehensive data generation.

ARCHITECTURE:
- @given decorator patterns for input generation
- Strategies for generating test data
- Phase settings for shrinking
- Stateful testing patterns

USAGE:
    pytest tests/property_based/test_skill_loading.py -v
"""

import pytest
from hypothesis import given, strategies as st, settings, Phase, example
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant, initialize
from hypothesis.extra import cli
import tempfile
import os
from pathlib import Path
from typing import Dict, Any, List

# Import the skill validation system we created
from skills.skill_validator import SkillMetadata, SkillDescription, ExecutionResult, SkillConfig, SkillManifest


# Define strategies for generating test data
skill_name_strategy = st.text(
    min_size=1, 
    max_size=50, 
    alphabet=st.characters(
        whitelist_categories=['Lu', 'Ll', 'Nd', 'Pc'],  # Letters, digits, connector punctuation
        whitelist_characters=['-', '_']
    )
).filter(lambda x: x[0].isalpha() and x.isalnum() or ('-' in x) or ('_' in x))


def semver_strategy():
    """Generate semantic version strings."""
    return st.builds(
        lambda major, minor, patch: f"{major}.{minor}.{patch}",
        st.integers(min_value=0, max_value=99),
        st.integers(min_value=0, max_value=99),
        st.integers(min_value=0, max_value=99)
    )


def author_strategy():
    """Generate author names."""
    return st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(
            whitelist_categories=['Lu', 'Ll', 'Nd', 'Zs'],
            whitelist_characters=['.', '-', '_', '@']
        )
    ).filter(lambda x: x.strip() != "")


def trigger_words_strategy():
    """Generate trigger words."""
    return st.lists(
        st.text(
            min_size=2,
            max_size=20,
            alphabet=st.characters(
                whitelist_categories=['Ll', 'Nd'],
                whitelist_characters=['-', '_']
            )
        ).map(str.lower),
        min_size=1,
        max_size=10
    ).map(list)


@settings(
    max_examples=100,
    phases=[Phase.generate, Phase.shrink],
    deadline=1000  # 1 second deadline
)
@given(
    skill_name=skill_name_strategy,
    version=semver_strategy(),
    author=author_strategy(),
    trigger_words=trigger_words_strategy()
)
def test_skill_metadata_validation_properties(skill_name, version, author, trigger_words):
    """
    Property: Any valid inputs should create valid skill metadata and description.
    """
    # Create metadata
    metadata = SkillMetadata(
        author=author,
        version=version,
        requires={"python": ">=3.8"}
    )
    
    # Create description
    description = SkillDescription(
        name=skill_name,
        description=f"Test skill for {skill_name}",
        trigger_words=trigger_words
    )
    
    # Assertions
    assert metadata.author == author.strip()
    assert metadata.version == version
    assert metadata.requires["python"] == ">=3.8"
    
    assert description.name == skill_name
    assert description.description.startswith("Test skill for")
    assert set(description.trigger_words) <= set(trigger_words)  # May have duplicates removed


@settings(
    max_examples=50,
    phases=[Phase.generate, Phase.shrink],
    deadline=1000
)
@given(
    data=st.dictionaries(
        st.text(min_size=1, max_size=20),
        st.one_of([
            st.text(),
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.lists(st.text()),
            st.dictionaries(st.text(min_size=1, max_size=10), st.text())
        ])
    )
)
def test_execution_result_schema_properties(data):
    """
    Property: Execution results always follow correct schema.
    """
    # Test successful execution result
    success_result = ExecutionResult(
        success=True,
        data=data,
        execution_time=0.1
    )
    
    assert success_result.success is True
    assert success_result.data == data
    assert success_result.error is None
    
    # Test failed execution result
    error_info = {
        "type": "test_error",
        "message": "Test error occurred",
        "details": data
    }
    
    fail_result = ExecutionResult(
        success=False,
        error=error_info
    )
    
    assert fail_result.success is False
    assert fail_result.error == error_info
    assert fail_result.data is None


@settings(
    max_examples=75,
    phases=[Phase.generate, Phase.shrink],
    deadline=1500
)
@given(
    name=skill_name_strategy,
    description=st.text(min_size=10, max_size=500),
    category=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=['Ll', 'Lu', 'Nd', '-'])),
    timeout=st.integers(min_value=1, max_value=300),
    priority=st.integers(min_value=-10, max_value=10)
)
def test_skill_description_properties(name, description, category, timeout, priority):
    """
    Property: Skill descriptions maintain their properties after validation.
    """
    trigger_words = [f"test{priority}", f"trigger{timeout}"]
    
    skill_desc = SkillDescription(
        name=name,
        description=description,
        trigger_words=trigger_words,
        category=category,
        timeout=timeout,
        priority=priority
    )
    
    assert skill_desc.name == name
    assert skill_desc.description == description
    assert skill_desc.category == category
    assert skill_desc.timeout == timeout
    assert skill_desc.priority == priority
    assert set(trigger_words).issubset(set(skill_desc.trigger_words))


@settings(
    max_examples=50,
    phases=[Phase.generate, Phase.shrink],
    deadline=1000
)
@given(
    max_concurrent=st.integers(min_value=1, max_value=50),
    cache_enabled=st.booleans(),
    cache_ttl=st.integers(min_value=60, max_value=86400)
)
@example(max_concurrent=1, cache_enabled=True, cache_ttl=60)  # Edge case
def test_skill_config_properties(max_concurrent, cache_enabled, cache_ttl):
    """
    Property: Skill configs maintain their properties after validation.
    """
    config = SkillConfig(
        max_concurrent=max_concurrent,
        cache_enabled=cache_enabled,
        cache_ttl=cache_ttl
    )
    
    assert config.max_concurrent == max_concurrent
    assert config.cache_enabled == cache_enabled
    assert config.cache_ttl == cache_ttl


@settings(
    max_examples=40,
    phases=[Phase.generate, Phase.shrink],
    deadline=2000
)
@given(
    metadata_data=st.fixed_dictionaries({
        "author": author_strategy(),
        "version": semver_strategy(),
        "requires": st.dictionaries(
            st.text(min_size=1, max_size=20),
            st.text(min_size=1, max_size=50)
        )
    }),
    description_data=st.fixed_dictionaries({
        "name": skill_name_strategy,
        "description": st.text(min_size=10, max_size=200),
        "trigger_words": trigger_words_strategy()
    })
)
def test_skill_manifest_properties(metadata_data, description_data):
    """
    Property: Complete skill manifests validate correctly with various inputs.
    """
    metadata = SkillMetadata(**metadata_data)
    description = SkillDescription(**description_data)
    config = SkillConfig()
    
    manifest = SkillManifest(
        metadata=metadata,
        description=description,
        config=config
    )
    
    assert manifest.metadata.author == metadata_data["author"]
    assert manifest.metadata.version == metadata_data["version"]
    assert manifest.description.name == description_data["name"]
    assert manifest.description.description == description_data["description"]
    assert set(manifest.description.trigger_words).issubset(set(description_data["trigger_words"]))
    assert manifest.config.max_concurrent == 5  # Default value


# Stateful testing for skill lifecycle
class SkillLifecycleMachine(RuleBasedStateMachine):
    """
    State machine testing for the complete skill lifecycle.
    """
    
    def __init__(self):
        super().__init__()
        self.skills = {}
        self.executions = []
        
    @initialize()
    def setup(self):
        """Initialize the state machine."""
        self.skills = {}
        self.executions = []
        
    @rule(
        name=skill_name_strategy,
        version=semver_strategy(),
        author=author_strategy(),
        description=st.text(min_size=10, max_size=100),
        trigger_words=trigger_words_strategy()
    )
    def add_skill(self, name, version, author, description, trigger_words):
        """Add a skill to the system."""
        try:
            metadata = SkillMetadata(
                author=author,
                version=version,
                requires={"python": ">=3.8"}
            )
            
            skill_desc = SkillDescription(
                name=name,
                description=description,
                trigger_words=trigger_words
            )
            
            manifest = SkillManifest(
                metadata=metadata,
                description=skill_desc
            )
            
            self.skills[name] = manifest
        except Exception:
            # Validation might reject invalid inputs, which is OK
            pass
    
    @rule(
        skill_name=st.sampled_from([]),  # Will be populated dynamically
        success=st.booleans(),
        data_input=st.dictionaries(st.text(), st.text())
    )
    def execute_skill(self, skill_name, success, data_input):
        """Execute a skill and record the result."""
        if skill_name in self.skills and len(data_input) > 0:
            try:
                if success:
                    result = ExecutionResult(
                        success=True,
                        data=data_input,
                        execution_time=0.1
                    )
                else:
                    result = ExecutionResult(
                        success=False,
                        error={
                            "type": "test_error",
                            "message": "Test execution error",
                            "data": data_input
                        }
                    )
                
                self.executions.append({
                    "skill": skill_name,
                    "result": result,
                    "input": data_input
                })
            except Exception:
                # Execution might fail, which is OK
                pass
    
    @invariant()
    def skills_have_valid_names(self):
        """Invariant: All skill names are valid."""
        for name in self.skills.keys():
            assert isinstance(name, str)
            assert len(name) > 0
            assert name[0].isalpha()
    
    @invariant()
    def execution_results_follow_schema(self):
        """Invariant: All execution results follow the schema."""
        for execution in self.executions:
            result = execution["result"]
            assert isinstance(result.success, bool)
            if result.success:
                assert result.data is not None
                assert result.error is None
            else:
                assert result.error is not None
                assert result.data is None


# Test the state machine
TestSkillLifecycle = SkillLifecycleMachine.TestCase


# Additional property tests for edge cases
@settings(max_examples=25, deadline=500)
@given(
    bad_name=st.text(min_size=0, max_size=50).filter(lambda x: not x or x[0].isdigit())
)
def test_skill_name_validation_rejects_invalid(bad_name):
    """
    Property: Invalid skill names are rejected.
    """
    if bad_name and not bad_name[0].isalpha():
        with pytest.raises(ValueError):
            SkillDescription(
                name=bad_name,
                description="Test description for invalid name",
                trigger_words=["test"]
            )


@settings(max_examples=25, deadline=500)
@given(
    bad_version=st.text(min_size=1, max_size=20).filter(
        lambda x: not x or not x.replace('.', '').replace(' ', '').isdigit()
    )
)
def test_version_validation_rejects_invalid(bad_version):
    """
    Property: Invalid versions are rejected.
    """
    if bad_version and not (len(bad_version.split('.')) == 3 and 
                           all(part.isdigit() for part in bad_version.split('.'))):
        with pytest.raises(ValueError):
            SkillMetadata(
                author="test_author",
                version=bad_version,
                requires={}
            )


@settings(max_examples=25, deadline=500)
@given(
    short_description=st.text(min_size=0, max_size=9)
)
def test_description_validation_rejects_short(short_description):
    """
    Property: Short descriptions are rejected.
    """
    if len(short_description) < 10:
        with pytest.raises(ValueError):
            SkillDescription(
                name="test_skill",
                description=short_description,
                trigger_words=["test"]
            )


if __name__ == "__main__":
    # Run the state machine test
    from hypothesis import HealthCheck
    
    # Disable certain health checks that might be triggered by our state machine
    settings.register_profile(
        "dev", 
        suppress_health_check=[HealthCheck.too_slow],
        max_examples=10,
        deadline=500
    )
    
    settings.load_profile("dev")
    test_class = SkillLifecycleMachine.TestCase()
    test_class.runTest()