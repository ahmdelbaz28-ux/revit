"""
services/yolo/main.py — YOLO Layout Segmentation Service for FireAI

Standalone FastAPI service that detects layout segments in floor plan images.
Called by fireai.integration.document_intelligence via HTTP.

V140 Phase 10: Adapted from Chunkr's YOLO service but standalone —
no Chunkr dependencies, no AGPL contamination.
"""

import gc
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import List

import torch
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from huggingface_hub import hf_hub_download
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
max_batch_size = int(os.getenv("MAX_BATCH_SIZE", "10"))
overlap_threshold = float(os.getenv("OVERLAP_THRESHOLD", "0.1"))
score_threshold = float(os.getenv("SCORE_THRESHOLD", "0.15"))
conf_threshold = float(os.getenv("CONF_THRESHOLD", "0.1"))
imgsz = int(os.getenv("IMAGE_SIZE", "1024"))

# Global model
model = None


def download_model():
    """Download the DocLayout-YOLO model from HuggingFace."""
    filepath = hf_hub_download(
        repo_id="juliozhao/DocLayout-YOLO-DocStructBench",
        filename="doclayout_yolo_docstructbench_imgsz1024.pt",
    )
    from doclayout_yolo import YOLOv10
    m = YOLOv10(filepath)
    logger.info("YOLO model loaded successfully")
    return m


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("Using device: %s", device)
    model = download_model()
    yield
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


app = FastAPI(lifespan=lifespan, title="FireAI YOLO Segmentation Service")


# ─── Models ──────────────────────────────────────────────────────────────────

class BoundingBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class BoundingBoxOutput(BaseModel):
    left: float
    top: float
    width: float
    height: float


class InstanceOutput(BaseModel):
    boxes: List[BoundingBoxOutput]
    scores: List[float]
    classes: List[str]
    image_size: List[int]


class FinalPrediction(BaseModel):
    instances: InstanceOutput


# ─── YOLO Class Mapping ─────────────────────────────────────────────────────

# DocLayout-YOLO class indices → human-readable segment types
YOLO_CLASS_MAP = {
    0: "title",
    1: "text",
    2: "abandon",
    3: "figure",
    4: "figure_caption",
    5: "table",
    6: "table_caption",
    7: "table_footnote",
    8: "isolate_formula",
    9: "formula_caption",
}


def map_yolo_class(cls_idx: int) -> str:
    return YOLO_CLASS_MAP.get(cls_idx, f"unknown_{cls_idx}")


# ─── Processing ──────────────────────────────────────────────────────────────

async def process_image_batch(
    image_data_list: List[bytes],
    conf: float = None,
    img_size: int = None,
) -> List[FinalPrediction]:
    if conf is None:
        conf = conf_threshold
    if img_size is None:
        img_size = imgsz

    temp_files = []
    for image_data in image_data_list:
        temp_file = f"temp_{uuid.uuid4()}.jpg"
        with open(temp_file, "wb") as f:
            f.write(image_data)
        temp_files.append(temp_file)

    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        det_res = model.predict(temp_files, imgsz=img_size, conf=conf, device=device)

        results = []
        for res in det_res:
            img_shape = res.orig_shape if hasattr(res, "orig_shape") else (0, 0)

            if hasattr(res, "boxes") and res.boxes is not None and hasattr(res.boxes, "xyxy"):
                boxes = res.boxes.xyxy.cpu().numpy()
                cls = res.boxes.cls.cpu().numpy().astype(int)
                conf_scores = res.boxes.conf.cpu().numpy()

                bbox_output = []
                classes_str = []
                scores_list = []

                for i in range(len(boxes)):
                    bbox_output.append(BoundingBoxOutput(
                        left=float(boxes[i][0]),
                        top=float(boxes[i][1]),
                        width=float(boxes[i][2] - boxes[i][0]),
                        height=float(boxes[i][3] - boxes[i][1]),
                    ))
                    classes_str.append(map_yolo_class(int(cls[i])))
                    scores_list.append(float(conf_scores[i]))

                results.append(FinalPrediction(
                    instances=InstanceOutput(
                        boxes=bbox_output,
                        scores=scores_list,
                        classes=classes_str,
                        image_size=list(img_shape),
                    )
                ))
            else:
                results.append(FinalPrediction(
                    instances=InstanceOutput(
                        boxes=[], scores=[], classes=[], image_size=list(img_shape),
                    )
                ))

        return results

    finally:
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        gc.collect()


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.post("/batch")
async def batch_segment(files: List[UploadFile] = File(...)):
    """Process a batch of images and return layout segmentation results."""
    image_data_list = []
    for file in files:
        image_data = await file.read()
        image_data_list.append(image_data)

    results = await process_image_batch(image_data_list)
    return results


@app.get("/")
async def root():
    return {"message": "FireAI YOLO Segmentation Service", "status": "ok"}


@app.get("/health")
async def health():
    return {"status": "healthy", "device": "cuda" if torch.cuda.is_available() else "cpu"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
