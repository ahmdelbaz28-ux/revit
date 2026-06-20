## Quick Start

**FireAI Digital Twin Platform v1.0.0**

### Table of Contents
1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Running Your First Project](#running-your-first-project)
5. [Basic Operations](#basic-operations)
6. [Troubleshooting](#troubleshooting)
7. [Next Steps](#next-steps)

## Prerequisites

Before installing FireAI, ensure your system meets the following requirements:

### System Requirements
- **Operating System**: Windows 10/11, macOS 10.15+, or Linux (Ubuntu 18.04+, CentOS 7+)
- **RAM**: Minimum 8GB (16GB recommended for optimal performance)
- **Storage**: 10GB available disk space
- **Python**: Version 3.12 or higher
- **pip**: Python package installer (usually comes with Python)
- **Node.js**: Version 18+ (for frontend development)
- **Docker**: Optional, for containerized deployments (recommended)

### Recommended Development Environment
- **IDE**: Visual Studio Code, PyCharm, or similar Python IDE
- **Terminal**: Command line interface (PowerShell, Terminal, or Command Prompt)

## Installation

### Method 1: Using Docker (Recommended for Production)

1. **Clone the repository**
   ```bash
   git clone https://github.com/ahmdelbaz28-ux/revit.git
   cd revit
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and set FIREAI_API_KEY and FIREAI_EVIDENCE_HMAC_KEY
   ```

3. **Build and run with Docker Compose**
   ```bash
   docker-compose up -d
   ```

4. **Open the application**
   Navigate to `http://localhost:8000`

### Method 2: From Source (Development)

1. **Clone the repository**
   ```bash
   git clone https://github.com/ahmdelbaz28-ux/revit.git
   cd revit
   ```

2. **Install Python dependencies**
   ```bash
   # P0.3: pyproject.toml is the single source of truth.
   # requirements.txt has been removed.
   pip install .
   ```

3. **Build the frontend**
   ```bash
   cd frontend && npm install && npm run build && cd ..
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

5. **Run the application**
   ```bash
   export FIREAI_ENV=development
   export FIREAI_API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
   python -m backend.app
   ```

6. **Open the application**
   Navigate to `http://localhost:8000`

## Configuration

### Basic Configuration

1. **Create environment file**
   ```bash
   cp .env.example .env
   ```

2. **Edit configuration file**
   Open `.env` and set the following required parameters:

   ```bash
   # FireAI Configuration
   FIREAI_ENV=production
   PORT=8000

   # Security - generate keys using:
   # python3 -c "import secrets; print(secrets.token_hex(32))"
   FIREAI_API_KEY=your-secret-key-here
   FIREAI_EVIDENCE_HMAC_KEY=your-hmac-key-here

   # CORS - allowed origins (comma-separated)
   CORS_ORIGINS=http://localhost:5173,http://localhost:8000

   # Content Security Policy
   CSP_CONNECT_SRC=http://localhost:5173 ws://localhost:5173 http://localhost:8000
   ```

3. **Environment Variables** (Alternative method)
   You can also set configuration via environment variables:

   ```bash
   export FIREAI_API_KEY="your-api-key"
   export FIREAI_ENV="production"
   export LOG_LEVEL="INFO"
   ```

### Security Setup

1. **Generate secure keys**
   ```bash
   # Generate JWT secret
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   
   # Generate encryption key
   python -c "import secrets; print(secrets.token_bytes(32).hex())"
   ```

2. **Set up SSL certificates** (Production)
   ```bash
   openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
   ```

## Running Your First Project

### Using the Web Interface

1. **Start the web server**
   ```bash
   cd /workspace/project/revit
   export FIREAI_ENV=development
   export FIREAI_API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
   python -m backend.app
   ```

2. **Open your browser** and navigate to `http://localhost:8000`

3. **Sign in** with your credentials (first time users should register)

4. **Create a new project** using the web interface:
   - Click "New Project"
   - Upload your CAD/BIM files (DWG, DXF, IFC, PDF)
   - Configure project parameters
   - Run NFPA 72 compliance analysis

### Using the API

1. **Start the API server**
   ```bash
   python -m backend.app --host 0.0.0.0 --port 8000
   ```

2. **Check API health**
   ```bash
   curl http://localhost:8000/api/health
   ```

3. **Create a project via API**
   ```bash
   curl -X POST http://localhost:8000/api/projects \
     -H "Content-Type: application/json" \
     -H "X-API-Key: YOUR_API_KEY" \
     -d '{
       "name": "My First Fire Alarm Project",
       "description": "Office building fire alarm system",
       "jurisdiction": "NFPA_72_2022"
     }'
   ```

## Basic Operations

### Managing Projects

1. **List all projects**
   ```bash
   curl http://localhost:8000/api/projects -H "X-API-Key: YOUR_API_KEY"
   ```

2. **View project details**
   ```bash
   curl http://localhost:8000/api/projects/{project_id} -H "X-API-Key: YOUR_API_KEY"
   ```

3. **Delete a project**
   ```bash
   curl -X DELETE http://localhost:8000/api/projects/{project_id} -H "X-API-Key: YOUR_API_KEY"
   ```

### Configuration Management

1. **View current configuration**
   ```bash
   cat .env
   ```

2. **Update configuration**
   Edit the `.env` file and restart the application.

### Integration Management

1. **Check system health**
   ```bash
   curl http://localhost:8000/api/health
   ```

2. **Upload CAD files for analysis**
   ```bash
   curl -X POST http://localhost:8000/api/projects/{id}/upload \
     -H "X-API-Key: YOUR_API_KEY" \
     -F "file=@floor_plan.dwg"
   ```

3. **Export project results**
   ```bash
   curl http://localhost:8000/api/projects/{id}/export/pdf \
     -H "X-API-Key: YOUR_API_KEY" \
     -o report.pdf
   ```

### Security Operations

1. **Generate new API key**
   ```bash
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```

2. **View security headers**
   ```bash
   curl -I http://localhost:8000/api/health
   ```

## Troubleshooting

### Common Issues

#### Installation Issues

**Problem**: Package installation fails with dependency errors
**Solution**:
```bash
# Upgrade pip first
pip install --upgrade pip

# Install with no cache
pip install --no-cache-dir .

# Or install dependencies individually
pip install --force-reinstall .
```

#### Configuration Issues

**Problem**: Application fails to start due to configuration errors
**Solution**:
1. Check that `.env` file exists
2. Ensure FIREAI_API_KEY is set
3. Verify that referenced files and directories are accessible
4. Check that ports are not in use

#### Connection Issues

**Problem**: Cannot connect to the application
**Solution**:
1. Verify that the application is running (`ps aux | grep backend.app`)
2. Check network connectivity
3. Confirm CORS settings in `.env`
4. Review firewall and security settings

### Diagnostic Commands

1. **System diagnostics**
   ```bash
   curl http://localhost:8000/api/health
   ```

2. **Check system requirements**
   ```bash
   python3 --version  # Should be 3.12+
   node --version     # Should be 18+
   ```

3. **View logs**
   ```bash
   tail -f /workspace/project/revit/app.log
   ```

4. **Check running processes**
   ```bash
   ps aux | grep -E "(python|uvicorn)" | grep -v grep
   ```

### Getting Help

1. **View help information**
   ```bash
   python -m backend.app --help
   ```

2. **Check documentation**
   ```bash
   cat README.md
   cat docs/API.md
   ```

3. **Community support**
   - Check the [GitHub Issues](https://github.com/ahmdelbaz28-ux/revit/issues) page
   - Email support: engineering@fireai.org

## Next Steps

### Learning More

1. **Complete the tutorials**
   - Follow the step-by-step tutorials in the [docs/](./docs/) directory
   - Try different types of projects and configurations

2. **Explore advanced features**
   - NFPA 72 compliance checking
   - CAD file parsing (DWG, DXF, IFC)
   - FACP selection and NAC design
   - Voltage drop calculations

3. **Contribute to the project**
   - Review the [CONTRIBUTING.md](./CONTRIBUTING.md) guide
   - Submit bug reports or feature requests
   - Contribute code improvements

### Production Deployment

When ready for production deployment:

1. **Security hardening**
   - Implement proper authentication and authorization
   - Configure SSL/TLS encryption
   - Set up proper logging and monitoring

2. **Performance optimization**
   - Configure caching appropriately
   - Set up load balancing if needed
   - Optimize database queries

3. **Monitoring and maintenance**
   - Set up comprehensive monitoring
   - Implement backup and disaster recovery procedures
   - Plan for regular updates and maintenance

### Support and Resources

- **Official Documentation**: [README.md](./README.md)
- **API Reference**: [docs/API.md](./docs/API.md)
- **GitHub Repository**: [https://github.com/ahmdelbaz28-ux/revit](https://github.com/ahmdelbaz28-ux/revit)
- **Commercial Support**: engineering@fireai.org

---

*FireAI Digital Twin Platform v1.0.0 - Safety-Critical Fire Protection Engineering*