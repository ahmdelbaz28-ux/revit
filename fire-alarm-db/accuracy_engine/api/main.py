from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Tuple
import io

from core.engine import run_accuracy_engine
from core.decision_pipeline import run_decision_pipeline

app = FastAPI(title="FireAlarmAI Accuracy Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class RoomModel(BaseModel):
    height: float = 3.0
    id: str
    type: str
    area: float
    polygon: List[Tuple[float, float]]

class EngineRequest(BaseModel):
    rooms: List[RoomModel]

@app.get("/")
def serve_ui():
    return FileResponse("index.html")

@app.post("/api/accuracy-engine")
def run_engine(request: EngineRequest):
    rooms = [r.model_dump() for r in request.rooms]
    result = run_accuracy_engine(rooms)
    return result

@app.get("/api/health")
def health():
    return {"status": "healthy", "engine": "accuracy_engine_v1"}


class DecisionRequest(BaseModel):
    rooms: List[RoomModel]

@app.post("/api/decision-pipeline")
def run_pipeline(request: DecisionRequest):
    rooms = [r.model_dump() for r in request.rooms]
    result = run_decision_pipeline(rooms)
    return result

@app.get("/api/export/dxf")
def export_dxf():
    import ezdxf

    doc = ezdxf.new()
    msp = doc.modelspace()

    msp.add_circle((0, 0), 0.3)

    buffer = io.BytesIO()
    doc.write(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/dxf",
        headers={"Content-Disposition": "attachment; filename=output.dxf"}
    )