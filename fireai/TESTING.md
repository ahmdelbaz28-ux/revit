# Testing

Tests are located in `tests/`. Run with:
```bash
pytest tests/
```
Coverage includes:
- Input validation (negative, NaN, Boolean, SQL injection, oversized polygons)
- NFPA spacing calculations
- CeilingSpec clamping
- ExpertSystem full pipeline
- API rate limiting (integration test)
- Safety refusal (kitchen with smoke detector)

To run a quick smoke test:
```bash
python -m pytest tests/ -v
```