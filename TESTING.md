# Testing Configuration Guide

This document outlines the testing configuration for the CAD/BIM integration platform, with special focus on timeout handling for different test types.

## Timeout Configuration

The project uses `pytest-timeout` to handle tests that may take longer than expected. Different types of tests have different timeout requirements:

- **Unit tests**: 120 seconds (2 minutes)
- **Integration tests**: 300 seconds (5 minutes) 
- **Slow tests**: 600 seconds (10 minutes)
- **Safety-critical tests**: 900 seconds (15 minutes)
- **Compliance tests**: 180 seconds (3 minutes)

## Configuration Files

Timeout settings are configured in:
- `pytest.ini`: Main pytest configuration with timeout defaults
- `pyproject.toml`: Additional timeout configuration under `[tool.pytest.ini_options]`

## Running Tests with Custom Timeouts

You can override the default timeout when running tests:

```bash
# Run with default timeout
python -m pytest tests/

# Run with custom timeout
python -m pytest tests/ --timeout=600

# Run specific test types with appropriate timeouts
python -m pytest tests/ -m integration --timeout=600
python -m pytest tests/ -m unit --timeout=120
```

## Adding New Test Types

When adding new types of tests that may require different timeout values:

1. Add the marker to `pytest.ini` and `pyproject.toml`
2. Set an appropriate timeout value based on the expected execution time
3. Use the marker in your test files:

```python
@pytest.mark.my_new_test_type
@pytest.mark.timeout(420)  # 7 minutes
def test_my_operation():
    # test implementation
    pass
```

## Troubleshooting Timeout Issues

If you encounter timeout issues:

1. Check if the timeout value is appropriate for the test
2. Consider whether the test is performing unnecessary operations
3. For long-running operations, consider mocking or using smaller datasets
4. Adjust the timeout value as needed, but keep it reasonable

## Best Practices

- Keep unit tests fast (< 1 second when possible)
- Use appropriate timeout values for different test categories
- Document why longer timeouts are needed for specific tests
- Monitor test execution times to optimize performance
- Use `--timeout=0` to disable timeouts during debugging