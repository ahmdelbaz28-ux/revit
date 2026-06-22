"""
Sample test file demonstrating different timeout configurations for various test types.
This file illustrates how to apply different timeout values to different types of tests.
"""

import time
import pytest


@pytest.mark.unit
def test_fast_unit_test():
    """A fast unit test with short timeout."""
    time.sleep(0.1)  # Simulate a quick operation
    assert True


@pytest.mark.integration
@pytest.mark.timeout(60)  # 60 seconds for integration tests
def test_integration_operation():
    """An integration test with moderate timeout."""
    time.sleep(0.5)  # Simulate an integration operation
    assert True


@pytest.mark.slow
@pytest.mark.timeout(120)  # 2 minutes for slow tests
def test_slow_operation():
    """A slow test with extended timeout."""
    time.sleep(1)  # Simulate a slower operation
    assert True


@pytest.mark.safety_critical
@pytest.mark.timeout(300)  # 5 minutes for safety-critical tests
def test_safety_critical_operation():
    """A safety-critical test with longer timeout."""
    time.sleep(0.5)  # Simulate a safety-critical operation
    assert True


@pytest.mark.compliance
@pytest.mark.timeout(180)  # 3 minutes for compliance tests
def test_compliance_check():
    """A compliance test with extended timeout."""
    time.sleep(0.3)  # Simulate a compliance check
    assert True


def test_default_timeout_behavior():
    """A test that will use the default timeout."""
    time.sleep(0.2)  # Simulate an operation with default timeout
    assert True