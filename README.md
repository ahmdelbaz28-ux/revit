# CAD/BIM Integration Platform

[![CI/CD Pipeline](https://github.com/ahmdelbaz28-ux/revit/actions/workflows/ci.yml/badge.svg)](https://github.com/ahmdelbaz28-ux/revit/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-green)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Security](https://img.shields.io/badge/security-rate%20limiting-brightgreen)](https://github.com/ahmdelbaz28-ux/revit/security)
[![OpenAPI](https://img.shields.io/badge/OpenAPI-Swagger%20UI-blue)](https://github.com/ahmdelbaz28-ux/revit/blob/main/backend/app.py)
[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://github.com/ahmdelbaz28-ux/revit/pkgs/container/revit)

Complete platform for AutoCAD and Revit integration with Digital Twin capabilities.

## Overview

This platform provides bidirectional conversion between AutoCAD DWG files and Revit RVT files through a sophisticated Digital Twin engine. The system enables seamless interoperability between 2D CAD drawings and 3D BIM models, supporting the entire AEC (Architecture, Engineering, Construction) workflow.

## Features

### Core Capabilities
- **AutoCAD Integration**: Connect to AutoCAD, read/write DWG files, create/draw entities
- **Revit Integration**: Connect to Revit, read/write RVT files, create/modify elements
- **Bidirectional Conversion**: Convert between AutoCAD and Revit formats
- **Digital Twin Engine**: Central conversion hub with semantic mapping
- **Version Management**: Track and rollback conversion history
- **Configuration Management**: Flexible mapping rules for conversion

### Technical Architecture
- **Backend**: FastAPI-based REST API
- **Services**: Modular service architecture for CAD/BIM operations
- **API Layer**: Comprehensive endpoints for all operations
- **Data Models**: Typed Pydantic models for request/response validation
- **Error Handling**: Comprehensive error handling and logging
- **Testing**: Complete test suite for all components

## Installation

### Prerequisites
- Python 3.8+
- Windows OS (for AutoCAD/Revit integration)
- AutoCAD (optional, for full functionality)
- Revit (optional, for full functionality)

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd revit-main
```

2. Create virtual environment:
```bash
python -m venv venv
venv\Scripts\activate  # On Windows
```

3. Install dependencies:
```bash
# P0.3: pyproject.toml is the single source of truth.
# requirements.txt has been removed.
pip install .

# For ML subsystem:
pip install .[ml]

# For development:
pip install .[dev]
```

4. Run the application:
```bash
cd backend
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

### AutoCAD Endpoints
- `POST /api/autocad/connect` - Connect to AutoCAD
- `POST /api/autocad/disconnect` - Disconnect from AutoCAD
- `POST /api/autocad/read_dwg` - Read DWG file
- `POST /api/autocad/write_dwg` - Write DWG file
- `POST /api/autocad/draw_line` - Draw line in AutoCAD
- `POST /api/autocad/draw_polyline` - Draw polyline in AutoCAD
- `POST /api/autocad/draw_circle` - Draw circle in AutoCAD
- `POST /api/autocad/draw_text` - Draw text in AutoCAD
- `GET /api/autocad/status` - Get connection status
- `POST /api/autocad/save` - Save current document
- `POST /api/autocad/upload_dwg` - Upload and read DWG file

### Revit Endpoints
- `POST /api/revit/connect` - Connect to Revit
- `POST /api/revit/disconnect` - Disconnect from Revit
- `POST /api/revit/read_rvt` - Read RVT file
- `POST /api/revit/write_rvt` - Write RVT file
- `POST /api/revit/create_wall` - Create wall in Revit
- `POST /api/revit/create_floor` - Create floor in Revit
- `POST /api/revit/create_column` - Create column in Revit
- `GET /api/revit/status` - Get connection status
- `POST /api/revit/save` - Save current document
- `POST /api/revit/get_elements` - Get elements from document
- `POST /api/revit/upload_rvt` - Upload and read RVT file

### Digital Twin Endpoints
- `POST /api/digital-twin/convert` - Bidirectional conversion
- `GET /api/digital-twin/history` - Get conversion history
- `POST /api/digital-twin/configure` - Update conversion config
- `POST /api/digital-twin/rollback/{version_id}` - Rollback to version
- `GET /api/digital-twin/mappings` - Get available mappings
- `GET /api/digital-twin/status` - Get service status
- `POST /api/digital-twin/update_mapping` - Update single mapping
- `GET /api/digital-twin/config` - Get current config

## Usage Examples

### AutoCAD Operations

Connect to AutoCAD:
```bash
curl -X POST "http://localhost:8000/api/autocad/connect" \
  -H "Content-Type: application/json" \
  -d '{"visible": true}'
```

Read a DWG file:
```bash
curl -X POST "http://localhost:8000/api/autocad/read_dwg" \
  -H "Content-Type: application/json" \
  -d '{"filepath": "path/to/drawing.dwg"}'
```

Draw a line in AutoCAD:
```bash
curl -X POST "http://localhost:8000/api/autocad/draw_line" \
  -H "Content-Type: application/json" \
  -d '{
    "start_point": [0, 0, 0],
    "end_point": [1000, 0, 0],
    "layer": "Walls",
    "color": 1
  }'
```

### Revit Operations

Connect to Revit:
```bash
curl -X POST "http://localhost:8000/api/revit/connect"
```

Read an RVT file:
```bash
curl -X POST "http://localhost:8000/api/revit/read_rvt" \
  -H "Content-Type: application/json" \
  -d '{"filepath": "path/to/model.rvt"}'
```

Create a wall in Revit:
```bash
curl -X POST "http://localhost:8000/api/revit/create_wall" \
  -H "Content-Type: application/json" \
  -d '{
    "start_point": [0, 0, 0],
    "end_point": [5000, 0, 0],
    "height": 3000.0,
    "level": "Level 1"
  }'
```

### Digital Twin Conversion

Convert AutoCAD to Revit:
```bash
curl -X POST "http://localhost:8000/api/digital-twin/convert" \
  -H "Content-Type: application/json" \
  -d '{
    "source_filepath": "input.dwg",
    "target_filepath": "output.rvt",
    "conversion_type": "autocad_to_revit"
  }'
```

Convert Revit to AutoCAD:
```bash
curl -X POST "http://localhost:8000/api/digital-twin/convert" \
  -H "Content-Type: application/json" \
  -d '{
    "source_filepath": "model.rvt",
    "target_filepath": "output.dwg",
    "conversion_type": "revit_to_autocad"
  }'
```

## ML Predictive Maintenance Subsystem (Q4 2026 Roadmap)

The platform now includes an ML-based predictive maintenance subsystem that
**complements** (does not replace) the existing statistical engine.

### Key Features
- **Ensemble prediction** combining XGBoost, Cox PH, and LSTM models
- **SHAP explainability** for every prediction (IEC 61508 compliance)
- **Advisory-only** outputs — NFPA 72 deterministic rules remain authoritative
- **Cross-references** existing statistical baseline for audit
- **Full REST API** at `/api/v1/ml/predictive-maintenance/*`
- **React dashboard** with risk gauge, model comparison, and SHAP visualisations

### Library Provenance
ML libraries curated from
[awesome-machine-learning](https://github.com/josephmisiti/awesome-machine-learning).

### Documentation
- See `ARCHITECTURE_ML_ADDENDUM.md` for full architectural details
- See `fireai/ml/README.md` for module documentation
- See `pyproject.toml [project.optional-dependencies.ml]` for ML dependencies

### Quick Start
```bash
pip install .[ml]
python scripts/train_ml_models_demo.py    # Train on synthetic data
python scripts/test_ml_subsystem.py       # Smoke test
pytest tests/ml/ -v                       # Full test suite
```

## Architecture

### Service Layer
- `AutoCADService`: Handles all AutoCAD operations via COM API
- `RevitService`: Handles all Revit operations via Revit API
- `DigitalTwinService`: Core conversion engine with semantic mapping
- `ConversionConfigManager`: Manages persistent conversion settings
- `VersionManager`: Tracks and manages conversion history

### Router Layer
- `autocad.py`: AutoCAD-specific endpoints
- `revit.py`: Revit-specific endpoints
- `digital_twin.py`: Digital Twin conversion endpoints
- All other standard FastAPI routers

### Data Flow
1. Client makes API request
2. Router validates request and forwards to service
3. Service performs CAD/BIM operation
4. Results returned to client
5. Operations logged for audit trail

## Configuration

The system supports extensive configuration for conversion mapping:

### Layer/Category Mapping
Map AutoCAD layers to Revit categories:
```json
{
  "layer_to_category": {
    "Walls": "Walls",
    "A-WALL": "Walls",
    "Doors": "Doors",
    "A-DOOR": "Doors"
  }
}
```

### Unit Conversion
Configure unit conversion between systems:
```json
{
  "source_units": "Millimeters",
  "target_units": "Millimeters",
  "scale_factor": 1.0
}
```

### Semantic Mapping
Define how elements are converted between systems:
- Lines on "Walls" layer → Revit Walls
- Hatches on "Floors" layer → Revit Floors
- Blocks named "Door" → Revit Door families
- Text → Revit Text Notes

## Testing

Run the complete test suite:
```bash
pytest tests/
```

Run specific test modules:
```bash
pytest tests/test_digital_twin.py
pytest tests/test_autocad.py
pytest tests/test_revit.py
```

## Error Handling

The system provides comprehensive error handling:

- **Connection Errors**: 503 Service Unavailable when CAD applications not available
- **File Errors**: 404 Not Found for missing files
- **Validation Errors**: 400 Bad Request for invalid parameters
- **General Errors**: 500 Internal Server Error for unexpected issues

## Deployment

For production deployment:

1. Use a WSGI server like Gunicorn:
```bash
gunicorn -w 4 -b 0.0.0.0:8000 backend.app:app
```

2. Configure reverse proxy with Nginx
3. Set up SSL certificates
4. Configure logging and monitoring

## Security Considerations

- Validate all file uploads to prevent malicious files
- Implement rate limiting for API endpoints
- Use authentication for production deployments
- Sanitize file paths to prevent directory traversal
- Validate CAD file contents before processing

## Troubleshooting

### Common Issues

1. **AutoCAD not found**: Ensure AutoCAD is installed and COM API enabled
2. **Revit not found**: Ensure Revit is installed with API support
3. **Permission errors**: Run with appropriate permissions for CAD applications
4. **File access errors**: Check file paths and permissions

### Logs

Check application logs in the console output or configured logging destination for detailed error information.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.