# 🔥 FireAlarmAI - Multi-Domain Building Design Platform

<p align="center">
  <a href="https://docker.com"><img src="https://img.shields.io/badge/Docker-Ready-blue?style=for-the-badge" alt="Docker"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge" alt="Python"></a>
  <a href="https://postgresql.org"><img src="https://img.shields.io/badge/PostgreSQL-14+-blue?style=for-the-badge" alt="PostgreSQL"></a>
  <a href="https://fastapi.tiangolo.com"><img src="https://img.shields.io/badge/FastAPI-Web-blue?style=for-the-badge" alt="FastAPI"></a>
  <a href="https://ultralytics.com"><img src="https://img.shields.io/badge/YOLOv8-Vision-red?style=for-the-badge" alt="YOLOv8"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License"></a>
</p>

> AI-powered multi-domain building engineering design platform for Fire Alarm, CCTV, Access Control, Public Address, Data Networks, Lighting, and Power systems.

## 🚀 Features

| Feature | Description |
|---------|-------------|
| **Vision AI** | YOLOv8-powered floor plan analysis for automatic room detection |
| **7 Engineering Domains** | FireAlarm, CCTV, AccessControl, PublicAddress, DataNetwork, Lighting, Power |
| **Auto-Routing** | NetworkX-based constraint routing with cable management |
| **Rule Validation** | NFPA72, BS5839, and international standards compliance |
| **BOQ Generation** | Automatic Bill of Quantities with manufacturer pricing |
| **Multi-Format Output** | DWG, PDF, Excel, JSON export formats |
| **Strategy Pattern** | Swappable engineering logic for easy domain extension |
| **PostgreSQL Database** | Relational database with full historical tracking |
| **REST API** | FastAPI-powered web services |
| **Docker Ready** | Containerized deployment |

## 📋 Table of Contents

1. [Architecture](#architecture)
2. [Quick Start](#quick-start)
3. [API Documentation](#api-documentation)
4. [Domains](#domains)
5. [Configuration](#configuration)
6. [Contributing](#contributing)
7. [License](#license)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FireAlarmAI Platform                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐           │
│  │   Upload     │───▶│   Vision    │───▶│   Design    │           │
│  │   (Image)   │    │   (YOLOv8)  │    │   (AI)      │           │
│  └──────────────┘    └──────────────┘    └──────────────┘           │
│                                                │                  │
│                                                ▼                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐           │
│  │  Routing    │◀───│  Validate   │◀───│  Devices   │           │
│  │  (NetworkX)│    │  (Rules)   │    │  (Placed)  │           │
│  └──────────────┘    └──────────────┘    └──────────────┘           │
│                                                │                  │
│                                                ▼                  │
│                                    ┌────────────────────────┐         │
│                                    │     Outputs            │         │
│                                    │  DWG | PDF | BOQ      │         │
│                                    └────────────────────────┘         │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                         Database (PostgreSQL)                       │
│  Project │ Rooms │ Sessions │ Devices │ Standards │ Catalog              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Using Docker Compose

```bash
# Clone the repository
git clone https://github.com/ahmdelbaz28-ux/revit.git
cd revit

# Start all services
docker-compose up -d

# Or run individually
docker-compose up -d db     # PostgreSQL
docker-compose up -d api   # FastAPI server
```

---

## 🎯 Quick Demo (Copy & Paste)

Test the API instantly after running `docker-compose up -d`:

```bash
# 1. Check service health
curl http://localhost:8000/healthz

# 2. List available engineering domains
curl http://localhost:8000/api/domains

# 3. Submit a FireAlarm design task (with sample image)
curl -X POST http://localhost:8000/api/elite-design \
  -F "image=@floorplan.png" \
  -F "project_name=Demo Office" \
  -F "domain=FireAlarm"

# 4. Check task status (replace TASK_ID)
curl http://localhost:8000/api/task/TASK_ID

# 5. Download results (when completed)
curl -O http://localhost:8000/download/TASK_ID
```

---

## 🔄 Architecture Flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                      Design Pipeline Flow                         │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                               │
│    ┌─────────┐      ┌─────────┐      ┌─────────┐      ┌─────────┐  │
│    │ Upload │ ───▶ │ Vision  │ ───▶ │ Design  │ ───▶ │Routing │  │
│    │Image  │      │ YOLOv8 │      │   AI   │      │NetworkX│  │
│    └─────────┘      └─────────┘      └─────────┘      └─────────┘  │
│                                                      │       │
│                                                      ▼       │
│    ┌─────────┐      ┌─────────┐             ┌─────────────────┐ │
│    │  ZIP   │ ◀───  │ Validate│ ◀─────────  │   Devices       │ │
│    │Output │       │  Rules  │             │   Placed        │ │
│    └─────────┘      └─────────┘             └─────────────────┘ │
│                                                               │
├──────────────────────────────────────────────────────────────────────────────┤
│  PostgreSQL: Project → Rooms → Sessions → Devices → Outputs      │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Manual Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment
export DATABASE_URL="postgresql://postgres:password@localhost/firealarmdb"

# Create database
python -c "from ai_design_integration import DatabaseManager; DatabaseManager('$DATABASE_URL').create_tables()"

# Seed reference data
python seed_all_domains.py

# Start server
python main.py
# Server runs on http://localhost:8000
```

---

## 📚 API Documentation

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info |
| `/healthz` | GET | Health check |
| `/api/domains` | GET | List available domains |
| `/api/elite-design` | POST | Submit design task |
| `/api/task/{task_id}` | GET | Get task status |
| `/download/{task_id}` | GET | Download results |

### API Example

```bash
# Get available domains
curl http://localhost:8000/api/domains

# Submit a design task
curl -X POST http://localhost:8000/api/elite-design \
  -F "image=@floorplan.png" \
  -F "project_name=My Building" \
  -F "domain=FireAlarm"
```

---

## 🏢 Domains

| Domain | Logic | Devices |
|--------|-------|---------|
| **FireAlarm** | Smoke/Heat detectors per area, notification appliances | SmokeDetector, HeatDetector, Speaker, ManualCallPoint |
| **CCTV** | Corner cameras, corridor coverage | IP Camera, PTZ Camera, NVR |
| **AccessControl** | Card/biometric readers, door locks | Card Reader, Biometric Reader, Electric Lock |
| **PublicAddress** | Ceiling speakers, wall speakers | Ceiling Speaker, Amplifier, Mixer |
| **DataNetwork** | Outlet placement, AP coverage | Switch, Router, Access Point |
| **Lighting** | Lux-based placement, emergency lights | LED Panel, Emergency Light, Sensor |
| **Power** | Socket distribution, DB sizing | MCB, RCCB, Distribution Board |

---

## ⚙️ Configuration

| Variable | Description | Default |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:password@localhost/firealarmdb` |
| `API_HOST` | Server host | `0.0.0.0` |
| `API_PORT` | Server port | `8000` |
| `YOLO_MODEL` | Path to YOLO model | `models/fire_alarm_yolo.pt` |
| `UPLOAD_DIR` | Upload directory | `./uploads` |

---

## 🤝 Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines on how to add new domains and contribute to the project.

---

## 📄 License

MIT License - See [LICENSE](../LICENSE) for details.

---

<p align="center">
  <strong>FireAlarmAI</strong> - AI-Powered Building Engineering Design<br>
  Built with ❤️ by OpenHands
</p>