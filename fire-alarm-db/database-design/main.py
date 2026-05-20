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
import re
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from uvicorn import run

# Security Fix (VULN-019): Allowed file extensions and max size
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.pdf', '.dwg', '.dxf'}
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def _sanitize_filename(filename: str) -> str:
    """Security Fix (VULN-019/026): Remove path components and validate filename."""
    filename = os.path.basename(filename)
    filename = re.sub(r'[^\w\s.-]', '', filename)
    return filename


def _sanitize_for_log(value: str) -> str:
    """Security Fix (VULN-022): Remove CRLF characters to prevent log injection."""
    if not isinstance(value, str):
        value = str(value)
    return re.sub(r'[\r\n]', '_', value)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

# Security Fix (VULN-005): Restricted CORS origins via environment variable
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
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
        "status": "running",
        "docs": "/docs"
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
def get_domains():
    """
    Get list of available engineering domains.
    
    Returns:
    - domains: List of available domain names
    - registry: Mapping of domain names to logic classes
    """
    if not ENGINE_AVAILABLE:
        raise HTTPException(status_code=500, detail="Engineering engine not available")
    
    # Get available domains
    domains = EngineeringLogicFactory.get_available_domains()
    
    return {
        "domains": domains,
        "registry": EngineeringDesignEngine.domain_registry,
        "default": "FireAlarm"

@app.post("/api/rules-engine")
def run_rules_engine(rooms: List[dict]):
    """Run the Fire Alarm Rules Engine for device placement.
    
    Request body: list of Room objects with id, type, area, polygon
    Response: devices, zones, validation report
    """
    from rules_engine.core.engine import run_fire_alarm_engine
    return run_fire_alarm_engine(rooms)

    }


@app.post("/api/elite-design")
async def elite_design(
    image: UploadFile = File(None),
    project_name: str = Form(...),
    standard: str = Form('egyptian'),
    domain: str = Form('FireAlarm')
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
        raise HTTPException(status_code=500, detail="Pipeline not available")
    
    # Validate image
    if not image:
        raise HTTPException(status_code=400, detail="Image required")
    
    # Generate task ID
    task_id = str(uuid.uuid4())
    # Security Fix (VULN-022): Sanitize log inputs to prevent log injection
    logger.info(f"Task {task_id}: project={_sanitize_for_log(project_name)}")
    
    # Security Fix (VULN-019): Sanitize filename and validate extension
    safe_filename = _sanitize_filename(image.filename or "")
    image_ext = Path(safe_filename).suffix.lower()
    if image_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{image_ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}"
        )
    image_path = TEMP_DIR / f"{task_id}{image_ext}"
    
    try:
        content = await image.read()
        # Security Fix (VULN-019): Enforce maximum upload size
        if len(content) > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE_BYTES // (1024*1024)} MB"
            )
        if not content:
            raise HTTPException(status_code=400, detail="Empty file uploaded")
        with open(image_path, 'wb') as f:
            f.write(content)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to save image")
    
    # Initialize task (if no image provided, pipeline will use test data)
    if not content:
        # Create a dummy test image
        logger.info(f"Task {task_id}: No image provided, using test data")
        image_path = None
    
    # Create task
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
    
    # Start background thread
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
def get_task_status(task_id: str):
    """
    Get task status
    
    Returns:
    - task_id: Task UUID
    - status: "processing" | "completed" | "error"
    - project_name: Project name
    - download_url: URL to download ZIP (if completed)
    """
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = TASKS[task_id]
    
    response = {
        "task_id": task_id,
        "status": task['status'],
        "project_name": task.get('project_name')
    }
    
    # Add download URL if completed
    if task['status'] == 'completed' and task.get('zip_path'):
        response['download_url'] = f"/download/{task_id}"
        response['output_zip'] = task['zip_path']
    
    # Add error if failed
    if task['status'] == 'error':
        response['error'] = task.get('error', 'Unknown error')
    
    return response


@app.get("/download/{task_id}")
def download_result(task_id: str):
    """
    Download result ZIP file
    
    Returns:
    - File attachment: {project_name}_outputs.zip
    """
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = TASKS[task_id]
    
    if task['status'] != 'completed':
        raise HTTPException(status_code=400, detail="Task not completed")
    
    zip_path = task.get('zip_path')
    if not zip_path or not Path(zip_path).exists():
        raise HTTPException(status_code=404, detail="Result file not found")
    
    # Security Fix (VULN-026): Sanitize project_name for filename
    project_name = re.sub(r'[^\w\s.-]', '', task.get('project_name', 'design'))
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
    """Global exception handler — returns generic error to client.
    Security Fix (VULN-020): No internal details exposed to client.
    """
    ref_id = str(uuid.uuid4())[:8]
    logger.error(f"[{ref_id}] Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "reference_id": ref_id}
    )


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    # Get host and port
    # Security Fix (VULN-005): Bind to localhost by default
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 8000))
    
    print("\n" + "="*60)
    print("FIRE ALARM ELITE PIPELINE SERVER")
    print("="*60)
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"Pipeline: {'Available' if PIPELINE_AVAILABLE else 'Not Available'}")
    print("="*60 + "\n")
    
    uvicorn.run(app, host=host, port=port)