# FireAI - Integrated CAD/BIM Safety Systems Platform

[![CI/CD Pipeline](https://github.com/ahmdelbaz28-ux/revit/actions/workflows/ci.yml/badge.svg)](https://github.com/ahmdelbaz28-ux/revit/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-green)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Security](https://img.shields.io/badge/security-rate%20limiting-brightgreen)](https://github.com/ahmdelbaz28-ux/revit/security)
[![OpenAPI](https://img.shields.io/badge/OpenAPI-Swagger%20UI-blue)](https://github.com/ahmdelbaz28-ux/revit/blob/main/backend/app.py)
[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://github.com/ahmdelbaz28-ux/revit/pkgs/container/revit)

FireAI is an advanced platform for integrated CAD/BIM systems with focus on fire safety engineering, electrical calculations, and building automation. The platform provides APIs for AutoCAD, Revit, and Digital Twin integrations with AI-powered analysis capabilities.

## Features

- **AutoCAD Integration**: Full API support for AutoCAD operations
- **Revit Integration**: Complete BIM integration with Revit API
- **Digital Twin**: Real-time modeling and simulation capabilities
- **AI-Powered Analysis**: Machine learning algorithms for predictive analysis
- **Safety Compliance**: NFPA 72 and NEC compliance checking
- **Conduit Fill Calculations**: Electrical conduit fill analysis
- **Security Headers**: Enterprise-grade security middleware
- **Rate Limiting**: API protection and throttling

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/ahmdelbaz28-ux/revit.git
   cd revit
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   ```bash
   cp .env.sample .env
   # Edit .env with your configuration
   ```

## Running the Server

To start the development server:

```bash
cd backend
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

The server will be available at `http://localhost:8000`.

## API Usage Example

Once the server is running, you can test the health endpoint:

```bash
curl http://localhost:8000/api/v1/health
```

For protected endpoints, include your API key:

```bash
curl -H "X-API-Key: YOUR_API_KEY" http://localhost:8000/api/v1/projects
```

## Project Structure

```
backend/
├── app.py                 # Main FastAPI application
├── config.py             # Configuration settings
├── auth.py               # Authentication middleware
├── middleware/           # Custom middleware
│   ├── csrf.py           # CSRF protection
│   └── security.py       # Security headers
├── routers/              # API route definitions
│   ├── autocad.py        # AutoCAD integration
│   ├── revit.py          # Revit integration
│   ├── digital_twin.py   # Digital twin endpoints
│   └── ...
├── services/             # Business logic
│   ├── autocad_service.py
│   ├── revit_service.py
│   └── ...
└── core/                 # Core utilities
    ├── redis_client.py   # Redis connection utilities
    └── ...
```

## Testing

Run the full test suite:

```bash
python -m pytest -v
```

For specific tests:

```bash
python -m pytest tests/test_auth_integration.py -v
```

## Security

The platform implements multiple layers of security:

- API key authentication
- Rate limiting with SlowAPI
- Content Security Policy (CSP) headers
- Cross-site request forgery (CSRF) protection
- Input validation and sanitization
- Secure session management

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For support, please contact the development team or create an issue in the GitHub repository.