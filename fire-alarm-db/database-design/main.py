#!/usr/bin/env python3
"""
main.py - FastAPI Server for Fire Alarm Elite Pipeline
=============================================

FastAPI endpoints for the Fire Alarm Design System.

Endpoints:
- POST /api/elite-design: Submit design task
- GET /api/task/{task_id}: Get task status
- GET /download/{task_id}: Download result ZIP
- GET /healthz: Health check

Usage:
    python main.py
    uvicorn main:app --reload
"""

import os
import sys
import uuid
import threading
import zipfile
import tempfile
import logging
import secrets
import re
from pathlib import Path
from typing import Dict, Optional, List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Header, status
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from uvicorn import run

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# Security Configuration
# =============================================================================

ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:8000').split(',')
API_KEY = os.getenv('API_KEY')
if not API_KEY:
    logger.warning("API_KEY environment variable not set. Using insecure default.")
    API_KEY = secrets.token_urlsafe(32)

security = HTTPBearer()

def verify_api_key(credentials: HTTPAuthCredentials = Depends(security)) -> str:
    """Verify API key from Authorization header"""
    if credentials.credentials != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )
    return credentials.credentials

def validate_input_string(value: str, max_length: int = 255, pattern: Optional[str] = None) -> str:
    """Validate string input"""
    if not value or len(value) > max_length:
        raise ValueError(f"Invalid input: must be between 1 and {max_length} characters")
    if pattern and not re.match(pattern, value):
        raise ValueError(f"Invalid input format: {pattern}")
    return value

def validate_task_id(task_id: str) -> str:
    """Validate task ID to prevent path traversal"""
    try:
        uuid.UUID(task_id)
        return task_id
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid task ID format"
        )

# Import pipeline components
try:
    from elite_pipeline import run_elite_pipeline
    PIPELINE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Elite pipeline not available: {e}")
    PIPELINE_AVAILABLE = False

# Import engineering design components
try:
    from ai_design_integration import (
        EngineeringDesignEngine, 
        EngineeringLogicFactory,
        DomainEnum
    )
    ENGINE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Engineering engine not available: {e}")
    ENGINE_AVAILABLE = False


# =============================================================================
# FastAPI App
# =============================================================================

app = FastAPI(
    title="Fire Alarm Elite Pipeline",
    description="AI-Powered Fire Alarm Design System",
    version="1.0.0"
)

# Enable CORS with restricted origins
cors_origins = [origin.strip() for origin in ALLOWED_ORIGINS if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


# =============================================================================
# Global State
# =============================================================================

# Task storage: task_id -> {'status': str, 'result': dict, 'zip_path': str}
TASKS: Dict[str, dict] = {}

# Temp directory for uploads
TEMP_DIR = Path(tempfile.mkdtemp(prefix='firealarm_uploads_'))


# =============================================================================
# Background Task Runner
# =============================================================================

def run_design_task(task_id: str, image_path: str, project_name: str, standard: str = 'egyptian', domain: str = 'FireAlarm'):
    """Run design task in background thread"""
    try:
        logger.info(f"Starting task {task_id}: project={project_name}, domain={domain}")
        
        # Get database URL
        db_url = os.environ.get('DATABASE_URL')
        
        # Run pipeline
        result = run_elite_pipeline(
            image_path=image_path,
            project_name=project_name,
            db_url=db_url,
            standard=standard,
            domain=domain
        )
        
        # Update task status
        TASKS[task_id]['status'] = 'completed'
        TASKS[task_id]['result'] = result
        
        if result.get('output_zip'):
            TASKS[task_id]['zip_path'] = result['output_zip']
        
        logger.info(f"Task {task_id} completed: {result.get('status')}")
        
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}", exc_info=True)
        TASKS[task_id]['status'] = 'error'
        TASKS[task_id]['error'] = str(e)


# =============================================================================
# Endpoints
# =============================================================================

@app.get("/")
def root():
    """Root endpoint"""
    return {
        "service": "Fire Alarm Elite Pipeline",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/openapi.json")
def get_openapi():
    """Serve OpenAPI specification"""
    import json
    from pathlib import Path
    
    openapi_path = Path(__file__).parent.parent / "openapi.json"
    if openapi_path.exists():
        return JSONResponse(content=json.loads(openapi_path.read_text()))
    raise HTTPException(status_code=404, detail="OpenAPI spec not found")


@app.get("/docs")
def get_docs():
    """Swagger UI documentation page"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>FireAlarmAI API Docs</title>
        <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
        <style>
            body { margin: 0; padding: 0; background: #0f172a; }
            .swagger-container { min-height: 100vh; }
        </style>
    </head>
    <body>
        <div id="swagger-ui"></div>
        <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
        <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
        <script>
            window.onload = function() {
                SwaggerUIBundle({
                    url: '/openapi.json',
                    dom: '#swagger-ui',
                    deepLinking: true,
                    showExtensions: true,
                    tryItOutEnabled: true,
                    presets: [
                        SwaggerUIBundle.presets.apis,
                        SwaggerUIBundleStandalonePresets
                    ],
                    layout: 'StandaloneLayout'
                });
            };
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/healthz")
def healthz():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.get("/api/domains")
def get_domains(api_key: str = Depends(verify_api_key)):
    """
    Get list of available engineering domains.
    
    Returns:
    - domains: List of available domain names
    - registry: Mapping of domain names to logic classes
    """
    if not ENGINE_AVAILABLE:
        raise HTTPException(status_code=500, detail="Service unavailable")
    
    domains = EngineeringLogicFactory.get_available_domains()
    
    return {
        "domains": domains,
        "registry": EngineeringDesignEngine.domain_registry,
        "default": "FireAlarm"
    }

@app.post("/api/rules-engine")
def run_rules_engine(rooms: List[dict], api_key: str = Depends(verify_api_key)):
    """Run the Fire Alarm Rules Engine for device placement.
    
    Request body: list of Room objects with id, type, area, polygon
    Response: devices, zones, validation report
    """
    from rules_engine.core.engine import run_fire_alarm_engine
    return run_fire_alarm_engine(rooms)


@app.post("/api/elite-design")
async def elite_design(
    image: UploadFile = File(None),
    project_name: str = Form(...),
    standard: str = Form('egyptian'),
    domain: str = Form('FireAlarm'),
    api_key: str = Depends(verify_api_key)
):
    """
    Submit a new design task
    
    Accepts:
    - image: Floor plan image file (optional)
    - project_name: Name of the project
    - standard: Design standard (egyptian, nfpa, british)
    - domain: Engineering domain (FireAlarm, CCTV, PublicAddress, etc.)
    
    Returns:
    - task_id: UUID for the task
    - status: "processing"
    """
    if not PIPELINE_AVAILABLE:
        raise HTTPException(status_code=500, detail="Service unavailable")
    
    try:
        validate_input_string(project_name, max_length=100)
        validate_input_string(standard, max_length=50, pattern=r'^[a-z]+$')
        validate_input_string(domain, max_length=50, pattern=r'^[a-zA-Z0-9]+$')
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if not image:
        raise HTTPException(status_code=400, detail="Image required")
    
    task_id = str(uuid.uuid4())
    logger.info(f"Task {task_id}: project={project_name}")
    
    image_ext = Path(image.filename).suffix or '.png'
    if not image_ext.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
        raise HTTPException(status_code=400, detail="Invalid image format")
    
    image_path = TEMP_DIR / f"{task_id}{image_ext}"
    
    try:
        content = await image.read()
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large")
        with open(image_path, 'wb') as f:
            f.write(content)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save image: {e}")
        raise HTTPException(status_code=500, detail="Failed to process image")
    
    if not content:
        logger.info(f"Task {task_id}: No image provided, using test data")
        image_path = None
    
    TASKS[task_id] = {
        'status': 'processing',
        'project_name': project_name,
        'image_path': str(image_path) if image_path and content else None,
        'standard': standard,
        'domain': domain,
        'result': None,
        'zip_path': None,
        'error': None
    }
    
    thread = threading.Thread(
        target=run_design_task,
        args=(task_id, str(image_path) if image_path and content else None, project_name, standard, domain)
    )
    thread.daemon = True
    thread.start()
    
    return {
        "task_id": task_id,
        "status": "processing",
        "domain": domain,
        "message": "Design task started"
    }


@app.get("/api/task/{task_id}")
def get_task_status(task_id: str, api_key: str = Depends(verify_api_key)):
    """
    Get task status
    
    Returns:
    - task_id: Task UUID
    - status: "processing" | "completed" | "error"
    - project_name: Project name
    - download_url: URL to download ZIP (if completed)
    """
    validated_id = validate_task_id(task_id)
    
    if validated_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = TASKS[validated_id]
    
    response = {
        "task_id": validated_id,
        "status": task['status'],
        "project_name": task.get('project_name')
    }
    
    if task['status'] == 'completed' and task.get('zip_path'):
        response['download_url'] = f"/download/{validated_id}"
    
    if task['status'] == 'error':
        response['error'] = "Task processing failed"
    
    return response


@app.get("/download/{task_id}")
def download_result(task_id: str, api_key: str = Depends(verify_api_key)):
    """
    Download result ZIP file
    
    Returns:
    - File attachment: {project_name}_outputs.zip
    """
    validated_id = validate_task_id(task_id)
    
    if validated_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = TASKS[validated_id]
    
    if task['status'] != 'completed':
        raise HTTPException(status_code=400, detail="Task not completed")
    
    zip_path = task.get('zip_path')
    if not zip_path or not Path(zip_path).exists():
        raise HTTPException(status_code=404, detail="Result file not found")
    
    project_name = task.get('project_name', 'design')
    filename = f"{project_name}_outputs.zip"
    
    return FileResponse(
        zip_path,
        media_type='application/zip',
        filename=filename
    )


# =============================================================================
# Error Handlers
# =============================================================================

@app.exception_handler(Exception)
def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {type(exc).__name__}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    # Get host and port
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 8000))
    
    print("\n" + "="*60)
    print("FIRE ALARM ELITE PIPELINE SERVER")
    print("="*60)
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"Pipeline: {'Available' if PIPELINE_AVAILABLE else 'Not Available'}")
    print("="*60 + "\n")
    
    uvicorn.run(app, host=host, port=port)