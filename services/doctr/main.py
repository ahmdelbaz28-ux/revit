"""
services/doctr/main.py — DocTR OCR Service for FireAI

Standalone FastAPI service that provides OCR with bounding boxes.
Called by fireai.integration.document_intelligence via HTTP.

V140 Phase 10: Adapted from Chunkr's DocTR service but standalone —
no Chunkr dependencies, no AGPL contamination.
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import Generic, List, Optional, TypeVar

import torch
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel
from pydantic.generics import GenericModel

load_dotenv(override=True)

# Disable torch compile (causes issues with some models)
torch._dynamo.config.suppress_errors = True
torch.compile = lambda x, *args, **kwargs: x

# Configuration
batch_wait_time = float(os.getenv("OCR_BATCH_WAIT_TIME", "0.25"))
max_batch_size = int(os.getenv("OCR_MAX_BATCH_SIZE", "50"))
detection_model_name = os.getenv("OCR_DETECTION_MODEL", "db_resnet50")
recognition_model_name = os.getenv("OCR_RECOGNITION_MODEL", "parseq")

# Load models
from doctr.models import ocr_predictor

if detection_model_name == "db_resnet50":
    from doctr.models import db_resnet50
    detection_model = db_resnet50(pretrained=True).eval()
else:
    detection_module = __import__("doctr.models", fromlist=[detection_model_name])
    detection_model = getattr(detection_module, detection_model_name)(pretrained=True).eval()

if recognition_model_name == "parseq":
    from doctr.models import parseq
    recognition_model = parseq(pretrained=True).eval()
else:
    recognition_module = __import__("doctr.models", fromlist=[recognition_model_name])
    recognition_model = getattr(recognition_module, recognition_model_name)(pretrained=True).eval()

predictor = ocr_predictor(
    detection_model, recognition_model, pretrained=True,
    export_as_straight_boxes=True
)

if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    predictor = predictor.cuda()
else:
    print("Using CPU")

os.environ["USE_TORCH"] = "YES"
os.environ["USE_TF"] = "NO"


# ─── Models ──────────────────────────────────────────────────────────────────

class Detection(GenericModel, Generic[TypeVar("T")]):
    value: Optional[TypeVar("T")]
    confidence: Optional[float]


class Word(BaseModel):
    value: str
    confidence: float
    geometry: List[List[float]]
    objectness_score: float
    crop_orientation: Detection[int]


class Line(BaseModel):
    geometry: List[List[float]]
    objectness_score: float
    words: List[Word]


class Block(BaseModel):
    geometry: List[List[float]]
    objectness_score: float
    lines: List[Line]
    artefacts: List[str]


class PageContent(BaseModel):
    page_idx: int
    dimensions: List[int]
    orientation: Detection[float]
    language: Detection[str]
    blocks: List[Block]


class OCRResponse(BaseModel):
    page_content: PageContent
    processing_time: float


# ─── Processing ──────────────────────────────────────────────────────────────

async def process_ocr_batch(image_bytes_list: List[bytes]) -> List[OCRResponse]:
    from doctr.io import DocumentFile

    doc = await asyncio.get_event_loop().run_in_executor(
        None, DocumentFile.from_images, image_bytes_list
    )

    start_time = time.time()
    with torch.inference_mode():
        if torch.cuda.is_available():
            with torch.amp.autocast("cuda"):
                result = predictor(doc)
        else:
            result = predictor(doc)

    responses = []
    for page_idx, page in enumerate(result.pages):
        blocks = []
        for block in page.blocks:
            lines = []
            for line in block.lines:
                words = []
                for word in line.words:
                    words.append(Word(
                        value=word.value,
                        confidence=word.confidence,
                        geometry=word.geometry,
                        objectness_score=1.0,
                        crop_orientation=Detection(value=0, confidence=1.0),
                    ))
                lines.append(Line(
                    geometry=line.geometry,
                    objectness_score=1.0,
                    words=words,
                ))
            blocks.append(Block(
                geometry=block.geometry,
                objectness_score=1.0,
                lines=lines,
                artefacts=[],
            ))

        responses.append(OCRResponse(
            page_content=PageContent(
                page_idx=page_idx,
                dimensions=page.dimensions,
                orientation=Detection(value=0.0, confidence=1.0),
                language=Detection(value="en", confidence=1.0),
                blocks=blocks,
            ),
            processing_time=time.time() - start_time,
        ))

    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return responses


# ─── FastAPI App ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


app = FastAPI(lifespan=lifespan, title="FireAI DocTR OCR Service")


@app.post("/batch")
async def batch_ocr(files: List[UploadFile] = File(...)):
    """Process a batch of images and return OCR results with bounding boxes."""
    tasks = []
    for file in files:
        image_data = await file.read()
        tasks.append(image_data)

    results = []
    for i in range(0, len(tasks), max_batch_size):
        chunk = tasks[i : i + max_batch_size]
        chunk_results = await process_ocr_batch(chunk)
        results.extend(chunk_results)

    return results


@app.get("/")
async def root():
    return {"message": "FireAI DocTR OCR Service", "status": "ok"}


@app.get("/health")
async def health():
    return {"status": "healthy", "device": "cuda" if torch.cuda.is_available() else "cpu"}


if __name__ == "__main__":
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)
