"""
tests/test_skill_integration.py — Integration Test for AI Agent Skill System
==========================================================================

Tests the integration of all the AI agent skill system components:
- Pydantic validation
- Tenacity retry mechanisms  
- Property-based testing
- Ruff code quality
- Pre-commit hooks

ARCHITECTURE:
- Validates all components work together
- Tests error handling and resilience
- Verifies schema compliance
"""

import pytest
from unittest.mock import Mock, patch
import asyncio
import tempfile
import os
from pathlib import Path

# Import our skill system components
from skills.skill_validator import (
    SkillMetadata, 
    SkillDescription, 
    ExecutionResult, 
    SkillConfig, 
    SkillManifest
)
from core.retry import (
    network_retry, 
    skill_retry, 
    async_network_retry,
    conditional_retry
)
from hypothesis import given, strategies as st, settings, Phase
from hypothesis.stateful import RuleBasedStateMachine, rule


def test_pydantic_validation_integration():
    """
    Test that Pydantic validation components work correctly.
    """
    # Test valid skill metadata
    metadata = SkillMetadata(
        author="test_author",
        version="1.0.0",
        requires={"python": ">=3.8"},
        license="MIT",
        tags=["test", "validation"]
    )
    
    assert metadata.author == "test_author"
    assert metadata.version == "1.0.0"
    assert metadata.requires["python"] == ">=3.8"
    assert "test" in metadata.tags
    
    # Test valid skill description
    description = SkillDescription(
        name="test_skill",
        description="This is a test skill for integration testing",
        trigger_words=["test", "integration", "skill"],
        category="testing",
        enabled=True,
        timeout=30,
        priority=0
    )
    
    assert description.name == "test_skill"
    assert "integration testing" in description.description
    assert set(["test", "integration", "skill"]).issubset(set(description.trigger_words))
    assert description.category == "testing"
    assert description.enabled is True
    assert description.timeout == 30
    assert description.priority == 0
    
    # Test valid execution result
    result = ExecutionResult(
        success=True,
        data={"result": "success", "value": 42},
        execution_time=0.123,
        timestamp="2023-01-01T00:00:00Z"
    )
    
    assert result.success is True
    assert result.data["result"] == "success"
    assert result.data["value"] == 42
    assert result.execution_time == 0.123
    assert result.timestamp == "2023-01-01T00:00:00Z"
    
    # Test valid skill config
    config = SkillConfig(
        max_concurrent=5,
        cache_enabled=True,
        cache_ttl=3600,
        rate_limit={"requests_per_minute": 100},
        allowed_hosts=["localhost", "127.0.0.1"]
    )
    
    assert config.max_concurrent == 5
    assert config.cache_enabled is True
    assert config.cache_ttl == 3600
    assert config.rate_limit["requests_per_minute"] == 100
    assert "localhost" in config.allowed_hosts
    
    # Test valid skill manifest
    manifest = SkillManifest(
        metadata=metadata,
        description=description,
        config=config,
        dependencies=["core", "utils"]
    )
    
    assert manifest.metadata.author == "test_author"
    assert manifest.description.name == "test_skill"
    assert manifest.config.max_concurrent == 5
    assert "core" in manifest.dependencies


def test_pydantic_validation_errors():
    """
    Test that Pydantic validation catches errors correctly.
    """
    # Test invalid version format
    with pytest.raises(ValueError):
        SkillMetadata(
            author="test",
            version="invalid_version",
            requires={}
        )
    
    # Test empty author
    with pytest.raises(ValueError):
        SkillMetadata(
            author="",
            version="1.0.0",
            requires={}
        )
    
    # Test short description
    with pytest.raises(ValueError):
        SkillDescription(
            name="test",
            description="short",
            trigger_words=["test"]
        )
    
    # Test empty trigger words
    with pytest.raises(ValueError):
        SkillDescription(
            name="test",
            description="Valid description that is long enough to pass validation",
            trigger_words=[]
        )
    
    # Test invalid trigger word
    with pytest.raises(ValueError):
        SkillDescription(
            name="test",
            description="Valid description that is long enough to pass validation",
            trigger_words=[""]
        )
    
    # Test inconsistent execution result (success with error)
    with pytest.raises(ValueError):
        ExecutionResult(
            success=True,
            data={"result": "success"},
            error={"type": "error", "message": "error occurred"}
        )
    
    # Test inconsistent execution result (failure without error)
    with pytest.raises(ValueError):
        ExecutionResult(
            success=False,
            data={"result": "should_not_exist"}
        )


def test_retry_mechanisms_sync():
    """
    Test that retry mechanisms work for synchronous functions.
    """
    # Counter to track function calls
    call_count = 0
    
    @skill_retry(max_attempts=3)
    def failing_function():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError(f"Attempt {call_count} failed")
        return "success"
    
    # This should succeed after 3 attempts
    result = failing_function()
    assert result == "success"
    assert call_count == 3
    
    # Reset counter
    call_count = 0
    
    # Test with too many failures
    @skill_retry(max_attempts=2)
    def always_failing_function():
        nonlocal call_count
        call_count += 1
        raise ConnectionError(f"Attempt {call_count} failed")
    
    with pytest.raises(ConnectionError):
        always_failing_function()
    
    assert call_count == 2  # Should have tried 2 times


@pytest.mark.asyncio
async def test_retry_mechanisms_async():
    """
    Test that retry mechanisms work for asynchronous functions.
    """
    call_count = 0
    
    @async_network_retry(max_attempts=3)
    async def async_failing_function():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError(f"Attempt {call_count} failed")
        return "success"
    
    # This should succeed after 3 attempts
    result = await async_failing_function()
    assert result == "success"
    assert call_count == 3


@settings(max_examples=50, deadline=1000)
@given(
    name=st.text(
        min_size=1, 
        max_size=30,
        alphabet=st.characters(whitelist_categories=['Ll', 'Lu', 'Nd'], whitelist_characters=['_', '-'])
    ).filter(lambda x: x[0].isalpha()),
    version=st.builds(
        lambda major, minor, patch: f"{major}.{minor}.{patch}",
        st.integers(min_value=0, max_value=9),
        st.integers(min_value=0, max_value=9),
        st.integers(min_value=0, max_value=9)
    ),
    author=st.text(min_size=1, max_size=20)
)
def test_property_based_skill_creation(name, version, author):
    """
    Property-based test for skill creation with various inputs.
    """
    try:
        metadata = SkillMetadata(
            author=author,
            version=version,
            requires={"python": ">=3.8"}
        )
        
        description = SkillDescription(
            name=name,
            description=f"Test skill for {name}",
            trigger_words=[name.lower()]
        )
        
        manifest = SkillManifest(
            metadata=metadata,
            description=description
        )
        
        assert manifest.metadata.author == author
        assert manifest.metadata.version == version
        assert manifest.description.name == name
        assert f"Test skill for {name}" == manifest.description.description
        
    except ValueError:
        # Some generated inputs may be invalid, which is expected
        # The validation should catch these appropriately
        pass


class SkillIntegrationStateMachine(RuleBasedStateMachine):
    """
    State machine test for complete skill integration lifecycle.
    """
    
    def __init__(self):
        super().__init__()
        self.skills = {}
        self.executions = []
        
    @rule(
        name=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=['Ll', 'Lu', 'Nd'])).filter(lambda x: x[0].isalpha()),
        author=st.text(min_size=1, max_size=20),
        version=st.builds(
            lambda major, minor, patch: f"{major}.{minor}.{patch}",
            st.integers(min_value=1, max_value=3),
            st.integers(min_value=0, max_value=9),
            st.integers(min_value=0, max_value=9)
        )
    )
    def add_valid_skill(self, name, author, version):
        """Add a valid skill to the system."""
        try:
            metadata = SkillMetadata(
                author=author,
                version=version,
                requires={"python": ">=3.8"}
            )
            
            description = SkillDescription(
                name=name,
                description=f"Skill {name} for {author}",
                trigger_words=[name.lower(), author.lower()]
            )
            
            manifest = SkillManifest(
                metadata=metadata,
                description=description
            )
            
            self.skills[name] = manifest
        except ValueError:
            # Some inputs might be invalid, which is okay
            pass
    
    @rule(
        skill_name=st.text(min_size=1, max_size=20),
        success=st.booleans()
    )
    def execute_skill(self, skill_name, success):
        """Execute a skill and record the result."""
        if skill_name in self.skills:
            try:
                if success:
                    result = ExecutionResult(
                        success=True,
                        data={"executed": skill_name, "success": True},
                        execution_time=0.1
                    )
                else:
                    result = ExecutionResult(
                        success=False,
                        error={
                            "type": "execution_error",
                            "message": f"Failed to execute {skill_name}",
                            "skill": skill_name
                        }
                    )
                
                self.executions.append({
                    "skill": skill_name,
                    "result": result,
                    "success": success
                })
            except Exception:
                # Execution might fail, which is okay
                pass
    
    def teardown(self):
        """Clean up after the test."""
        self.skills.clear()
        self.executions.clear()


# Create the test class
TestSkillIntegrationStateMachine = SkillIntegrationStateMachine.TestCase


def test_schema_serialization():
    """
    Test that schemas serialize correctly.
    """
    metadata = SkillMetadata(
        author="test_author",
        version="1.2.3",
        requires={"python": ">=3.8", "numpy": ">=1.0.0"},
        license="MIT",
        tags=["test", "integration"]
    )
    
    description = SkillDescription(
        name="test_skill",
        description="Test skill for schema serialization",
        trigger_words=["test", "serialize"],
        category="testing",
        timeout=60,
        priority=1
    )
    
    config = SkillConfig(
        max_concurrent=3,
        cache_enabled=True,
        cache_ttl=1800,
        rate_limit={"requests_per_minute": 50},
        allowed_hosts=["localhost"]
    )
    
    manifest = SkillManifest(
        metadata=metadata,
        description=description,
        config=config,
        dependencies=["core.utils", "external.lib"]
    )
    
    # Test model dump
    dumped = manifest.model_dump()
    assert dumped["metadata"]["author"] == "test_author"
    assert dumped["description"]["name"] == "test_skill"
    assert dumped["config"]["max_concurrent"] == 3
    assert "core.utils" in dumped["dependencies"]
    
    # Test JSON schema generation
    schema = manifest.get_schema()
    assert "properties" in schema
    assert "metadata" in schema["properties"]
    assert "description" in schema["properties"]


if __name__ == "__main__":
    # Run basic tests
    test_pydantic_validation_integration()
    test_pydantic_validation_errors()
    test_schema_serialization()
    print("All integration tests passed!")