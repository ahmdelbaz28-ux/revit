# AI Agent Skill System

Production-ready AI agent skill system with integrated validation, retry mechanisms, and quality assurance patterns.

## Overview

This system implements best practices from leading Python libraries:
- **Pydantic** - Robust data validation and serialization
- **Hypothesis** - Property-based testing for reliability
- **Ruff** - Fast linting and code quality
- **Pre-commit** - Automated quality gates

## Architecture

### Core Components

#### 1. Skill Validator (`skill_validator.py`)
- **Pydantic BaseModel** patterns for data validation
- **Field validation** with custom validators
- **Model serialization** with `model_dump` and JSON schema
- **Error handling** with ValidationError
- **Generic models** for reusability

```python
from skills.skill_validator import SkillMetadata, SkillDescription, ExecutionResult

# Create validated skill metadata
metadata = SkillMetadata(
    author="developer",
    version="1.0.0",  # Enforced semantic versioning
    requires={"python": ">=3.8"}
)

# Create validated skill description
description = SkillDescription(
    name="data_analyzer",
    description="Analyzes data patterns and trends",
    trigger_words=["analyze", "data", "patterns"],
    timeout=60
)

# Create validated execution result
result = ExecutionResult(
    success=True,
    data={"analysis": "completed", "results": [1, 2, 3]},
    execution_time=0.5
)
```

#### 2. Property-Based Testing (`tests/property_based/`)
- **@given decorator** patterns for input generation
- **Strategies** for generating comprehensive test data
- **Phase settings** for optimization and shrinking
- **Stateful testing** patterns

## Features

### Data Validation
- Semantic version enforcement
- Input sanitization and normalization
- Schema validation with detailed error reporting
- Flexible field constraints

### Fault Tolerance
- Use `tenacity` directly for retry strategies (the project already depends on it)
- Timeout management
- Graceful degradation

### Quality Assurance
- Property-based testing for edge cases
- Multi-stage quality gates
- Automated code formatting
- Security scanning

## Usage

### Creating Skills
```python
from skills.skill_validator import SkillManifest, SkillConfig

manifest = SkillManifest(
    metadata=SkillMetadata(
        author="your_name",
        version="1.0.0",
        requires={"python": ">=3.8", "numpy": ">=1.0.0"}
    ),
    description=SkillDescription(
        name="my_skill",
        description="Does amazing things",
        trigger_words=["amazing", "things"]
    ),
    config=SkillConfig(
        max_concurrent=5,
        cache_enabled=True,
        cache_ttl=3600
    )
)
```

### Running Tests
```bash
# Property-based tests
python -m pytest tests/property_based/

# Integration tests
python -m pytest tests/test_skill_integration.py
```

### Quality Checks
```bash
# Run pre-commit hooks
pre-commit run --all-files

# Format code
ruff format .

# Check linting
ruff check --fix
```

## Configuration

### Ruff Settings
Located in `pyproject.toml`, includes:
- Line length: 100 characters
- Target version: Python 3.8
- Selected rules: E, W, F, I, N, UP, B, C4, DTZ, SIM, PGH, PL, PT, RUF
- Import organization for project structure

### Pre-commit Hooks
Located in `.pre-commit-config.yaml`, includes:
- **Stage 1**: Code quality and formatting
- **Stage 2**: Type checking
- **Stage 3**: Security scanning
- **Stage 4**: Testing
- **Stage 5**: Skill validation
- **Stage 6**: General code quality

## Best Practices

### For Skill Development
1. Always use validated models for data
2. For retry, use `tenacity` directly — `from tenacity import retry, stop_after_attempt, wait_exponential`
3. Test with property-based testing
4. Follow code quality guidelines
5. Validate inputs and outputs

### For Integration
1. Use the skill manifest for configuration
2. Handle execution results consistently
3. Monitor execution metrics
4. Implement proper error handling
5. Follow security guidelines

## Quality Metrics

- **Validation**: 100% field validation coverage
- **Testing**: Property-based tests with 100+ examples
- **Code Quality**: Ruff compliance with 0 violations
- **Security**: Bandit scanning integrated
- **Reliability**: Use `tenacity` for retry; circuit-breaker libs for breaker patterns

## Maintenance

### Adding New Skills
1. Create skill with validated models
2. For retry, decorate with `tenacity.retry` directly
3. Add property-based tests
4. Update pre-commit hooks if needed

### Updating Dependencies
1. Update `pyproject.toml`
2. Run `pip install -e .`
3. Test all components
4. Update documentation if needed

## Contributing

1. Fork the repository
2. Create feature branch
3. Add pre-commit hooks: `pre-commit install`
4. Make changes following quality standards
5. Run tests: `python -m pytest tests/`
6. Submit pull request

## License

MIT License - See LICENSE file for details.