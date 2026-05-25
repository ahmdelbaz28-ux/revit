# 🤝 Contributing to FireAlarmAI

Thank you for considering contributing to FireAlarmAI! This guide will help you get started.

---

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Follow the project's coding standards
- Help others learn and grow

---

## How to Contribute

### 1. Adding a New Domain

To add a new engineering domain (e.g., "Lighting"):

**Step 1: Create Logic Class**

```python
# database-design/lighting_logic.py
from ai_design_integration import EngineeringLogic, AIDesignDevice

class LightingLogic(EngineeringLogic):
    DOMAIN_NAME = "Lighting"
    
    def analyze_room(self, room_data):
        # Implementation
        return {...}
    
    def place_devices(self, room, session_id, db_session):
        # Place LED fixtures, sensors
        return devices
    
    def calculate_cost(self, devices):
        # Calculate material + labor
        return {...}
```

**Step 2: Update EngineeringLogicFactory**

```python
# In ai_design_integration.py
class EngineeringLogicFactory:
    _LOGICS = {
        # ... existing ...
        'Lighting': LightingLogic,
    }
```

**Step 3: Add Seed Data**

Add device types and standards in `seed_all_domains.py`:

```python
DEVICE_TYPES['Lighting'] = [
    {'name': 'LED Panel', 'description': 'LED Light Panel'},
    {'name': 'Occupancy Sensor', 'description': 'Presence Sensor'},
    # ...
]
```

**Step 4: Update Tests**

Add tests in `test_multi_domain.py` for the new domain.

### 2. Code Style

- Use **4 spaces** for indentation (not tabs)
- **Max line length**: 100 characters
- Use **descriptive** variable names
- Add **docstrings** to all public functions
- Type hints where appropriate

### 3. Git Workflow

```bash
# Create branch
git checkout -b feature/your-feature

# Make changes
git add .
git commit -m "feat: Add feature description"

# Push
git push origin feature/your-feature

# Create PR
# Open pull request on GitHub
```

### 4. Pull Request Guidelines

- PR title: Clear description
- PR body: 
  - What changes
  - Why needed
  - How tested
- Link related issues

---

## Development Environment

```bash
# Clone
git clone https://github.com/ahmdelbaz28-ux/revit.git

# Install
pip install -r requirements.txt

# Test
python fire-alarm-db/database-design/test_multi_domain.py
```

---

## Testing

All new features must include tests:

- Unit tests for logic classes
- Integration tests for workflows
- Run existing tests before submitting PR

```bash
# Run tests
python -m pytest fire-alarm-db/database-design/tests/
```

---

## Documentation

- Update README.md for API changes
- Add docstrings to new functions
- Include examples where helpful

---

## Questions?

- Open an issue on GitHub
- Email: engineering@firealarmai.example.com

---

*Thank you for contributing to FireAlarmAI!*