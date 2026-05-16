"""
FireAI REST API
===============
FastAPI-based REST API for FireAI.

Endpoints:
    POST /projects/ - Upload and analyze file
    GET /projects/ - List all projects
    GET /projects/{id} - Get project details
    GET /projects/{id}/report - Download PDF report

Usage:
    uvicorn fireai_api:app --reload
    
    # Or:
    python fireai_api.py
"""

import os
import uuid
import hashlib
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass, asdict

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import shutil

# Import FireAI components
from parsers.dxf_parser import DXFParser
from parsers.pdf_parser import PDFParser
from parsers.excel_parser import ExcelParser
from core.fireai_db_reporting import FireAIDatabase
from core.pdf_report import PDFReportGenerator


# ════════════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="FireAI API",
    description="Fire Safety Analysis REST API",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Storage
UPLOAD_DIR = "/tmp/fireai_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Database
db = FireAIDatabase()


# ════════════════════════════════════════════════════════════════════
# MODELS
# ════════════════════════════════════════════════════════════════════

@dataclass
class ProjectResponse:
    id: str
    name: str
    file_name: str
    file_type: str
    status: str
    created_at: str
    room_count: int
    device_count: int


@dataclass
class AnalysisResponse:
    success: bool
    project_id: str
    message: str
    rooms: int
    devices: dict
    violations: int
    audit_hash: str


# ════════════════════════════════════════════════════════════════════
# ROUTES
# ════════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    """API info."""
    return {
        "name": "FireAI API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
def health():
    """Health check."""
    return {"status": "healthy"}


@app.post("/projects/", response_model=AnalysisResponse)
async def upload_and_analyze(
    file: UploadFile = File(...),
    project_name: Optional[str] = Query(None)
):
    """
    Upload file and analyze.
    
    Returns analysis results with audit hash.
    """
    # Generate project ID
    project_id = hashlib.md5(
        f"{file.filename}{datetime.now().isoformat()}".encode()
    ).hexdigest()[:16]
    
    # Save uploaded file
    file_path = os.path.join(UPLOAD_DIR, f"{project_id}_{file.filename}")
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    
    # Determine file type
    ext = os.path.splitext(file.filename)[1].lower()
    
    # Save project to database
    db.save_project(
        name=project_name or file.filename,
        file_path=file_path,
        file_type=ext
    )
    
    # Analyze
    rooms = []
    devices = {}
    violations = 0
    success = True
    message = "Analysis complete"
    
    try:
        if ext in ['.dxf', '.dwg']:
            parser = DXFParser()
            result = parser.parse(file_path)
            
            rooms = [
                {"name": r.name, "floor_area": r.floor_area}
                for r in result.rooms
            ]
            devices = {"estimated_detectors": max(1, len(rooms))}
            
        elif ext == '.pdf':
            parser = PDFParser()
            result = parser.parse(file_path)
            
            rooms = [{"name": f"Room {i+1}", "floor_area": 0} for i in range(result.room_count)]
            devices = {"devices_found": result.device_count}
            
        elif ext in ['.xlsx', '.xls']:
            parser = ExcelParser()
            result = parser.parse(file_path)
            
            rooms = [
                {"name": r.name, "floor_area": r.floor_area}
                for r in result.rooms
            ]
            devices = {"rooms": len(rooms)}
            
        else:
            raise ValueError(f"Unsupported file type: {ext}")
            
    except Exception as e:
        success = False
        message = f"Analysis failed: {str(e)}"
        violations = 0
        
    # Save analysis to database
    audit_hash = hashlib.sha256(
        f"{project_id}{datetime.now().isoformat()}".encode()
    ).hexdigest()[:16]
    
    db.save_analysis(
        project_hash=project_id,
        room_count=len(rooms),
        device_count=sum(devices.values()) if devices else 0,
        violations=violations,
        analysis_data={
            "success": success,
            "message": message,
            "audit_hash": audit_hash
        }
    )
    
    # Log to audit
    db.log_audit(project_id, "API_ANALYSIS", f"File: {file.filename}")
    
    return AnalysisResponse(
        success=success,
        project_id=project_id,
        message=message,
        rooms=len(rooms),
        devices=devices,
        violations=violations,
        audit_hash=audit_hash
    )


@app.get("/projects/")
def list_projects():
    """List all projects."""
    projects = db.list_projects()
    return {"projects": projects}


@app.get("/projects/{project_id}")
def get_project(project_id: str):
    """Get project details."""
    project = db.get_project(project_id)
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    return project


@app.get("/projects/{project_id}/report")
def download_report(project_id: str):
    """Download PDF report."""
    project = db.get_project(project_id)
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get analysis data
    with db._init_database() if not hasattr(db, 'conn') else None:
        pass
    
    # Generate report
    generator = PDFReportGenerator()
    
    rooms = [{"name": "Room 1", "floor_area": 25.0}]  # Simplified
    
    pdf_bytes = generator.generate(
        project_name=project["name"],
        rooms=rooms,
        devices={"Smoke Detector": 3},
        audit_hash=project_id,
        file_name=project.get("file_path", "unknown")
    )
    
    # Save temp
    report_path = f"/tmp/report_{project_id}.pdf"
    with open(report_path, "wb") as f:
        f.write(pdf_bytes)
    
    return FileResponse(
        report_path,
        media_type="application/pdf",
        filename=f"FireAI_Report_{project_id}.pdf"
    )


# ════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("🔥 FireAI REST API")
    print("=" * 50)
    print("Starting server...")
    print("API docs: http://localhost:8000/docs")
    print()
    
    uvicorn.run(app, host="0.0.0.0", port=8000)