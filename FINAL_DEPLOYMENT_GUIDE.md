# Final Deployment Guide

## Application: FireAI Digital Twin v1.0.0
## Platform: Linux ARM64 (aarch64)

---

## Prerequisites

### System Requirements
| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| CPU | ARM64 (Cortex-A72+) | ARM64 (Cortex-A76+) |
| RAM | 4 GB | 8 GB |
| Storage | 1 GB free | 2 GB free |
| Python | 3.12+ | 3.14 |
| Display | X11/Wayland (for GUI) | X11 with compositor |

### Runtime Dependencies
- Python 3.12+ with pip
- System libraries: libasound2t64, libxkbcommon0, libgbm1, libgtk-3-0, libnss3
- (Installed by AppImage if using --appimage-extract-and-run)

---

## Installation

### Option 1: AppImage (Recommended)

```bash
# Make executable
chmod +x FireAI-DigitalTwin-1.0.0-arm64.AppImage

# Run directly
./FireAI-DigitalTwin-1.0.0-arm64.AppImage

# If FUSE is not available, use:
./FireAI-DigitalTwin-1.0.0-arm64.AppImage --appimage-extract-and-run
```

### Option 2: Unpacked Build

```bash
# Extract and run from unpacked directory
./linux-arm64-unpacked/fireai-digital-twin
```

---

## First Launch

1. **Start the application**
   ```bash
   ./FireAI-DigitalTwin-1.0.0-arm64.AppImage
   ```

2. **Backend auto-start**
   - The Electron main process launches the Python backend automatically
   - Backend startup takes ~19 seconds (first-time import of fireai.core modules)
   - Health check polls every 1 second for up to 30 seconds
   - Status indicator in the UI shows backend connectivity

3. **Verify backend is running**
   ```bash
   curl http://localhost:8000/api/health
   # Expected: {"success":true,"data":{"status":"ok","database":"connected","core_modules":"loaded"}}
   ```

---

## Configuration

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| FIREAI_ENV | production | Environment mode (development/production) |
| FIREAI_BACKEND_PORT | 8000 | Backend API port |
| FIREAI_DB_DIR | ./db | Database directory |
| OPENAI_API_KEY | (none) | OpenAI API key (for memory features) |
| GEMINI_API_KEY | (none) | Gemini API key (for memory features) |

### Backend Configuration
The backend auto-configures from the project root directory structure:
- `backend/` — FastAPI application
- `core/` — Core data models and database
- `parsers/` — File parsers (DWG, DXF, IFC, PDF)
- `fireai/` — Engineering kernel and ML pipeline
- `db/` — SQLite database (auto-created at first launch)

---

## Deployment Topologies

### Standalone Desktop (Default)
- Electron window + embedded Python backend
- SQLite database in `~/.fireai/db/`
- No network dependencies for basic operations

### Client-Server (Advanced)
- Run backend on a server:
  ```bash
  cd /opt/fireai && python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
  ```
- Frontend connects to remote backend
- Configure via environment or build-time settings

---

## Backup & Recovery

### Database Backup
```bash
# SQLite database location
ls -la ./db/digital_twin.db

# Backup
cp ./db/digital_twin.db ./backups/digital_twin_$(date +%Y%m%d).db
```

### Recovery
```bash
# Restore from backup
cp ./backups/digital_twin_20260612.db ./db/digital_twin.db
```

---

## Security Configuration

### Default Security Settings (verified)
| Setting | Value |
|---------|-------|
| contextIsolation | true |
| nodeIntegration | false |
| sandbox | true |
| webSecurity | true |
| CSP | `default-src 'self'; connect-src 'self' http://localhost:* ws://localhost:*` |
| X-Frame-Options | DENY |
| X-Content-Type-Options | nosniff |
| Permissions-Policy | restricted |

### TLS/HTTPS (Production)
For production deployments with remote backend, configure:
```bash
# Generate self-signed certificate
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes

# Start backend with HTTPS
python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8000 --ssl-keyfile key.pem --ssl-certfile cert.pem
```

---

## Monitoring

### Health Check Endpoint
```
GET /api/health
```
Returns: `{"success":true,"data":{"status":"ok","database":"connected","core_modules":"loaded","uptime":123.45}}`

### Logs
- Backend logs: stdout (can be redirected to file)
- Electron logs: `~/.config/fireai-digital-twin/logs/`

---

## Troubleshooting

### Backend won't start
```bash
# Check if Python is available
python3 --version

# Try importing the app manually
cd /opt/fireai && python3 -c "from backend.app import app; print('OK')"
```

### AppImage won't run
```bash
# Try with --no-sandbox
./FireAI-DigitalTwin-1.0.0-arm64.AppImage --no-sandbox

# Or extract and run
./FireAI-DigitalTwin-1.0.0-arm64.AppImage --appimage-extract
./squashfs-root/AppRun
```

### Database issues
```bash
# Reset database
rm -rf ./db/digital_twin.db*
# Restart the application (database will be recreated)
```
