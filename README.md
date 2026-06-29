# 🔥 FireAI - Integrated CAD/BIM Safety Systems Platform

[![CI/CD Pipeline](https://github.com/ahmdelbaz28-ux/revit/actions/workflows/full-deploy.yml/badge.svg)](https://github.com/ahmdelbaz28-ux/revit/actions/workflows/full-deploy.yml)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-green)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Security](https://img.shields.io/badge/security-enterprise%20grade-brightgreen)](https://github.com/ahmdelbaz28-ux/revit/security)
[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://github.com/ahmdelbaz28-ux/revit/pkgs/container/revit)
[![HuggingFace](https://img.shields.io/badge/HuggingFace-Spaces-yellow)](https://huggingface.co/spaces/ahmdelbaz28/AHMEDETAP)
[![Render](https://img.shields.io/badge/Render-live-blue)](https://fireai.onrender.com)

<div align="center">

# 🚀 FireAI Platform

### Advanced CAD/BIM Integration with AI-Powered Fire Safety Engineering

[![Dashboard Preview](https://via.placeholder.com/1200x600/1a1a2e/00d4ff?text=FireAI+Dashboard+Preview)](https://github.com/ahmdelbaz28-ux/revit)

*Professional CAD/BIM Safety Systems Dashboard - Real-time monitoring and analysis*

</div>

---

## 📋 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Deployment](#deployment)
- [API Documentation](#api-documentation)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)

---

## 🎯 Overview

**FireAI** is a cutting-edge, enterprise-grade platform that revolutionizes fire safety engineering and building automation through advanced CAD/BIM integration. Our platform combines the power of AutoCAD, Revit, and Digital Twin technologies with AI-driven analysis to ensure compliance with NFPA 72 and NEC standards.

### Why FireAI?

- 🏆 **Industry-Leading**: Comprehensive fire protection engineering suite
- 🤖 **AI-Powered**: Machine learning algorithms for predictive analysis
- 🔒 **Enterprise Security**: Rate limiting, CORS hardening, HMAC integrity
- 🚀 **Multi-Platform**: Deploy to HuggingFace, Render, Kubernetes, or cloud
- 📊 **Real-Time**: Live monitoring and Digital Twin simulation
- ✅ **Compliant**: NFPA 72, NEC, and international regulatory standards

---

## ⭐ Key Features

### 🏗️ CAD/BIM Integration
- **AutoCAD Full API**: Complete DWG/DXF file manipulation
- **Revit Integration**: Native Revit API with Python.NET
- **Digital Twin**: Real-time 3D modeling and simulation
- **IFC Support**: Industry Foundation Classes interoperability

### 🔥 Fire Safety Engineering
- **NFPA 72 Compliance**: Automatic detector placement and spacing
- **Battery Calculations**: Advanced battery aging and derating analysis
- **Conduit Fill**: Electrical conduit fill calculations per NEC
- **Smoke Detector Layout**: Intelligent spacing and coverage analysis
- **FACP Systems**: Fire Alarm Control Panel engineering

### 🤖 AI & Machine Learning
- **Predictive Analytics**: ML-powered failure prediction
- **Learning Agents**: Self-improving AI systems
- **Natural Language Processing**: Skill-based AI agents
- **Computer Vision**: Image recognition for CAD elements

### 🔐 Security & Compliance
- **Rate Limiting**: Per-path API throttling
- **CORS Hardening**: Production-grade origin validation
- **HMAC Integrity**: Cryptographic audit trails
- **Secret Rotation**: Automated key management
- **Security Headers**: Enterprise-grade middleware

### 🌐 Multi-Platform Deployment
- **Hugging Face Spaces**: One-click AI deployment
- **Render.com**: Auto-scaling cloud hosting
- **Kubernetes**: Enterprise container orchestration
- **ETAP Sync**: Automatic repository synchronization

---

## 🏛️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FireAI Platform                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Frontend   │  │    Backend   │  │     AI       │    │
│  │  (React/TS)  │◄─►│  (FastAPI)   │◄─►│  (Python)   │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
│         │                  │                  │            │
│         ▼                  ▼                  ▼            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  HuggingFace │  │   Render     │  │ Kubernetes   │    │
│  │   Spaces     │  │   .com       │  │  (K8s)       │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | React, TypeScript, Tailwind CSS, Vite |
| **Backend** | FastAPI, Python 3.12, SQLAlchemy |
| **AI/ML** | PyTorch, TensorFlow, Hugging Face |
| **Database** | PostgreSQL, Redis, SQLite |
| **Security** | HMAC, JWT, Rate Limiting, CORS |
| **Deployment** | Docker, Kubernetes, Helm Charts |
| **CI/CD** | GitHub Actions, Automated Testing |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+
- Docker & Docker Compose
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/ahmdelbaz28-ux/revit.git
cd revit

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt
pip install -e .

# Install frontend dependencies
cd frontend
npm install
npm run build
cd ..

# Configure environment
cp .env.example .env
# Edit .env with your configuration
```

### Running the Application

```bash
# Start the backend server
cd backend
uvicorn app:app --reload --host 0.0.0.0 --port 8000

# In another terminal, start the frontend
cd frontend
npm run dev
```

Access the application:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/api/v1/health

---

## 🌍 Deployment

### Live Deployments

| Platform | URL | Status |
|----------|-----|--------|
| **Hugging Face Spaces** | [ahmedelbaz28/AHMEDETAP](https://huggingface.co/spaces/ahmdelbaz28/AHMEDETAP) | 🟢 Live |
| **Render.com** | [fireai.onrender.com](https://fireai.onrender.com) | 🟢 Live |
| **GitHub Pages** | [ahmdelbaz28-ux.github.io/revit](https://ahmdelbaz28-ux.github.io/revit) | 🟢 Live |

### Auto-Deployment

Every push to `main` or `develop` automatically triggers:

1. ✅ **Test Suite** - Full pytest with coverage
2. ✅ **Security Scan** - Bandit vulnerability analysis
3. ✅ **Frontend Build** - TypeScript compilation & optimization
4. ✅ **Multi-Platform Deploy** - Parallel deployment to all platforms
5. ✅ **ETAP Sync** - Automatic repository synchronization

### Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Developer Push to main/develop                             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  GitHub Actions CI/CD Pipeline                              │
│  • Run Tests (pytest)                                       │
│  • Security Scan (bandit)                                   │
│  • Build Frontend (npm)                                     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Parallel Deployment (if tests pass)                        │
│  ┌──────────────┬──────────────┬──────────────┐            │
│  │ HuggingFace  │    Render    │   K8s        │            │
│  │   Spaces     │   .com       │ (Staging/    │            │
│  │              │              │  Production) │            │
│  └──────────────┴──────────────┴──────────────┘            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  ETAP-AI-WORK Repository Auto-Sync                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 📚 API Documentation

### Authentication

All API endpoints require authentication via API key:

```bash
curl -H "X-API-Key: YOUR_API_KEY" http://localhost:8000/api/v1/projects
```

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check with API version |
| `/api/v1/projects` | GET | List all projects |
| `/api/v1/projects` | POST | Create new project |
| `/api/v1/autocad/*` | GET | AutoCAD operations |
| `/api/v1/revit/*` | GET | Revit integration |
| `/api/v1/digital-twin/*` | GET | Digital Twin simulation |
| `/api/v1/environment/*` | GET | Environmental data |

### Interactive Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 🧪 Testing

### Run Full Test Suite

```bash
# Run all tests with coverage
pytest tests/ -v --cov=fireai --cov=backend --cov-report=html

# Run specific test categories
pytest tests/test_security.py -v
pytest tests/test_revit.py -v
pytest tests/test_autocad.py -v

# Run property-based tests
pytest tests/property_based/ -v
```

### Test Coverage

- ✅ **208+ tests** passing
- ✅ **Security tests**: CORS, rate limiting, HMAC integrity
- ✅ **Integration tests**: AutoCAD, Revit, Digital Twin
- ✅ **Property-based tests**: Hypothesis-driven validation
- ✅ **Stress tests**: Load and performance testing

---

## 🛠️ Development

### Project Structure

```
revit/
├── backend/                 # FastAPI backend
│   ├── app.py              # Main application
│   ├── config.py           # Configuration
│   ├── auth.py             # Authentication
│   ├── middleware/         # Security middleware
│   ├── routers/            # API routes
│   ├── services/           # Business logic
│   └── core/               # Core utilities
├── frontend/               # React frontend
│   ├── src/
│   │   ├── components/     # React components
│   │   ├── pages/          # Page components
│   │   ├── engine/         # Calculation engines
│   │   └── styles/         # Global styles
│   └── package.json
├── fireai/                 # AI/ML modules
│   ├── core/               # Core AI functionality
│   ├── agents/             # AI agents
│   ├── analytics/          # Predictive analytics
│   └── bridges/            # External integrations
├── revit_integration/      # Revit-specific code
├── qomn_fire/              # Fire engineering modules
├── qomn_conduit/           # Conduit fill calculations
├── tests/                  # Test suite
│   ├── test_*.py           # Unit tests
│   ├── property_based/     # Hypothesis tests
│   └── factories/          # Test factories
├── deploy/                 # Deployment configs
│   ├── docker/             # Dockerfiles
│   ├── helm/               # Helm charts
│   └── k8s/                # Kubernetes manifests
└── .github/workflows/      # CI/CD pipelines
    ├── ci.yml              # Continuous integration
    └── full-deploy.yml     # Multi-platform deployment
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📊 Screenshots

### Dashboard Overview

![Dashboard](https://via.placeholder.com/1200x600/1a1a2e/00d4ff?text=FireAI+Dashboard+-+Real-time+Monitoring)

*Comprehensive dashboard with real-time project monitoring and analytics*

### Fire Safety Analysis

![Fire Safety](https://via.placeholder.com/1200x600/1a1a2e/00d4ff?text=NFPA+72+Compliance+Analysis)

*Automated NFPA 72 compliance checking and detector placement*

### Digital Twin Simulation

![Digital Twin](https://via.placeholder.com/1200x600/1a1a2e/00d4ff?text=Digital+Twin+3D+Simulation)

*Real-time 3D building simulation and modeling*

### API Documentation

![API Docs](https://via.placeholder.com/1200x600/1a1a2e/00d4ff?text=Interactive+API+Documentation)

*Auto-generated Swagger UI with full API documentation*

---

## 🎓 Use Cases

### 🏢 Commercial Buildings
- Fire alarm system design and verification
- Conduit routing and fill calculations
- Battery backup system analysis

### 🏭 Industrial Facilities
- Hazardous area classification (ATEX)
- Complex conduit systems
- Power distribution analysis

### 🏥 Healthcare Facilities
- NFPA 72 compliance verification
- Emergency lighting calculations
- Smoke control system design

### 🏗️ Construction Projects
- BIM integration and coordination
- Clash detection and resolution
- As-built documentation

---

## 📈 Roadmap

- [x] Core CAD/BIM integration
- [x] NFPA 72 compliance engine
- [x] Multi-platform deployment
- [x] AI-powered analysis
- [ ] Real-time collaboration
- [ ] Mobile applications
- [ ] Blockchain audit trails
- [ ] Quantum-resistant encryption

---

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

### Development Team

- **Lead Developer**: Ahmed ElBaz
- **AI/ML**: Machine Learning Team
- **DevOps**: Cloud Infrastructure Team

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **NFPA** - National Fire Protection Association standards
- **NEC** - National Electrical Code guidelines
- **Autodesk** - AutoCAD and Revit APIs
- **Hugging Face** - AI/ML infrastructure
- **Render** - Cloud hosting platform

---

## 📞 Contact

- **GitHub**: [@ahmdelbaz28-ux](https://github.com/ahmdelbaz28-ux)
- **Repository**: [revit](https://github.com/ahmdelbaz28-ux/revit)
- **HuggingFace**: [AHMEDETAP](https://huggingface.co/spaces/ahmdelbaz28/AHMEDETAP)
- **Live Demo**: [fireai.onrender.com](https://fireai.onrender.com)

---

<div align="center">

### ⭐ Star this repository if you find it helpful!

**FireAI** - Empowering fire safety engineering with AI

Made with ❤️ by the FireAI Team

</div>