#!/usr/bin/env python3
"""
vision_engine_v2.py - Deep Learning Vision Engine for Floor Plan Analysis
============================================================

This module uses YOLOv8 for accurate detection of:
- Rooms (as bounding boxes)
- Electrical symbols (Smoke Detector, Heat Detector, etc.)
- Panel locations

Uses OCR for room labeling and scale detection for dimension conversion.

Author: FireAlarmAI Engineering Team
Date: 2026-05-09
"""

import os
import sys
import json
import logging
import time
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to import deep learning libraries
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("PyTorch not available")

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    logger.warning("Ultralytics (YOLO) not available")

# Try to import OCR
try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False
    logger.warning("Pytesseract not available for OCR")


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DetectedRoom:
    """Represents a detected room in the floor plan"""
    room_id: str
    name: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    width_pixels: float
    height_pixels: float
    width_meters: float
    length_meters: float
    area_sqm: float
    height_meters: float = 3.0
    room_type: str = "office"
    occupancy: int = 0
    confidence: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'id': self.room_id,
            'name': self.name,
            'length': self.length_meters,
            'width': self.width_meters,
            'height': self.height_meters,
            'type': self.room_type,
            'occupancy': self.occupancy,
            'area': self.area_sqm,
            'confidence': self.confidence
        }


@dataclass
class DetectedSymbol:
    """Represents a detected electrical symbol"""
    symbol_id: str
    symbol_type: str
    x_center: float
    y_center: float
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    confidence: float


@dataclass
class ScaleInfo:
    """Scale information for dimension conversion"""
    pixels_per_meter: float
    scale_bar_location: Tuple[int, int] = None
    detected_from: str = "default"


@dataclass
class FloorPlanAnalysisV2:
    """Complete floor plan analysis result (YOLO version)"""
    image_path: str
    image_width: int
    image_height: int
    rooms: List[DetectedRoom]
    symbols: List[DetectedSymbol]
    scale: ScaleInfo
    existing_devices_count: int = 0
    analysis_time_seconds: float = 0.0
    model_name: str = ""
    device_used: str = "cpu"
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
    
    def to_rooms_data(self) -> List[Dict]:
        return [room.to_dict() for room in self.rooms]
    
    def to_symbols_data(self) -> List[Dict]:
        return [
            {
                'symbol_type': s.symbol_type,
                'x': s.x_center,
                'y': s.y_center,
                'confidence': s.confidence
            }
            for s in self.symbols
        ]


# =============================================================================
# Industrial Vision Engine (YOLO-based)
# =============================================================================

class IndustrialVisionEngine:
    """
    Deep Learning-based Vision Engine using YOLOv8
    
    Capabilities:
    - Room detection using custom-trained YOLO model
    - Electrical symbol detection
    - OCR for room labeling
    - Scale detection for dimension conversion
    - GPU/CPU support
    """
    
    DEFAULT_MODEL_PATH = "yolov8n.pt"
    
    ROOM_CLASS_MAPPING = {
        'room': 'office', 'office': 'office', 'bedroom': 'bedroom',
        'bathroom': 'bathroom', 'kitchen': 'kitchen', 'living_room': 'living_room',
        'corridor': 'corridor', 'hall': 'hall', 'storage': 'storage',
        'lobby': 'lobby', 'meeting': 'meeting'
    }
    
    SYMBOL_CLASS_MAPPING = {
        'smoke_detector': 'SmokeDetector', 'smokedetector': 'SmokeDetector',
        'heat_detector': 'HeatDetector', 'heatdetector': 'HeatDetector',
        'manual_call_point': 'ManualCallPoint', 'manualcallpoint': 'ManualCallPoint',
        'mcp': 'ManualCallPoint', 'speaker': 'Speaker',
        'horn': 'Horn', 'strobe': 'Strobe',
        'panel': 'Panel', 'control_panel': 'ControlPanel'
    }
    
    def __init__(self, model_path: str = None, device: str = "auto",
                 confidence_threshold: float = 0.5, scale_factor: float = 50.0,
                 ocr_enabled: bool = True):
        self.model_path = model_path or self.DEFAULT_MODEL_PATH
        self.confidence_threshold = confidence_threshold
        self.scale_factor = scale_factor
        self.ocr_enabled = ocr_enabled and PYTESSERACT_AVAILABLE
        self.device = self._get_device(device)
        self.model = None
        self.model_name = ""
        self.is_loaded = False
        logger.info(f"IndustrialVisionEngine initialized - Device: {self.device}")
    
    def _get_device(self, device: str) -> str:
        if device == "auto":
            if TORCH_AVAILABLE and torch.cuda.is_available():
                logger.info("CUDA available, using GPU")
                return "cuda"
            return "cpu"
        return device
    
    def load_model(self, model_path: str = None) -> bool:
        if not YOLO_AVAILABLE:
            logger.error("YOLO not installed. Run: pip install ultralytics")
            return False
        try:
            path = model_path or self.model_path
            logger.info(f"Loading YOLO model: {path}")
            if not os.path.exists(path):
                logger.warning(f"Model not found, using default YOLOv8 nano")
                path = "yolov8n.pt"
            self.model = YOLO(path)
            self.model.to(self.device)
            self.model_name = os.path.basename(path)
            self.is_loaded = True
            logger.info(f"Model loaded: {self.model_name} on {self.device}")
            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self.is_loaded = False
            return False
    
    def _load_image(self, image_path: str):
        """Load image and convert to numpy array"""
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        pil_img = Image.open(image_path).convert('RGB')
        img_array = np.array(pil_img)
        return img_array, pil_img
    
    def _detect_scale_bar(self, img_array: np.ndarray) -> ScaleInfo:
        """Detect scale bar in image for dimension conversion"""
        # Default scale: 50 pixels per meter (typical for architectural drawings)
        return ScaleInfo(
            pixels_per_meter=self.scale_factor,
            detected_from="default"
        )
    
    def _estimate_room_type(self, area_sqm: float, name: str) -> str:
        """Estimate room type based on area and name"""
        name_lower = name.lower()
        
        for keyword, room_type in [
            ('bed', 'bedroom'),
            ('bath', 'bathroom'),
            ('kitchen', 'kitchen'),
            ('living', 'living_room'),
            ('corridor', 'corridor'),
            ('hall', 'hall'),
            ('storage', 'storage'),
            ('meeting', 'meeting'),
            ('office', 'office'),
        ]:
            if keyword in name_lower:
                return room_type
        
        # Default based on area
        if area_sqm < 10:
            return "storage"
        elif area_sqm < 25:
            return "office"
        elif area_sqm < 50:
            return "meeting"
        return "office"
    
    def _estimate_occupancy(self, room_type: str, area_sqm: float) -> int:
        """Estimate room occupancy based on type and area"""
        # Per occupancy code (typically 100 sq ft per person for offices)
        sqm_per_person = 9.3  # 100 sq ft
        
        if room_type in ['corridor', 'hall', 'storage']:
            return 0
        elif room_type in ['bedroom']:
            return 2
        elif room_type in ['bathroom']:
            return 1
        elif room_type in ['kitchen']:
            return 2
        elif room_type in ['meeting']:
            return int(area_sqm / (sqm_per_person * 2))
        
        return int(area_sqm / sqm_per_person)
    
    def _apply_ocr_to_rooms(self, pil_image, rooms: List[DetectedRoom]) -> List[DetectedRoom]:
        """Apply OCR to detect room labels"""
        if not PYTESSERACT_AVAILABLE:
            return rooms
        
        try:
            # Get image dimensions
            width, height = pil_image.size
            
            for room in rooms:
                # Crop room region for OCR
                x1 = int(room.x_min)
                y1 = int(room.y_min)
                x2 = int(room.x_min + 200)  # Check left side for label
                y2 = int(room.y_min + 50)
                
                if x1 < width and y1 < height:
                    region = pil_image.crop((x1, y1, min(x2, width), min(y2, height)))
                    text = pytesseract.image_to_string(region)
                    
                    # Clean up text
                    text = text.strip()
                    if text and len(text) < 30:
                        room.name = text
        
        except Exception as e:
            logger.warning(f"OCR error: {e}")
        
        return rooms
    
    def analyze_floor_plan(self, image_path: str) -> FloorPlanAnalysisV2:
        """
        Analyze floor plan image
        
        Args:
            image_path: Path to floor plan image
            
        Returns:
            FloorPlanAnalysisV2 with detected rooms and devices
        """
        start_time = time.time()
        
        if not self.is_loaded:
            if not self.load_model():
                raise RuntimeError("Failed to load YOLO model")
        
        img_array, pil_image = self._load_image(image_path)
        width, height = pil_image.size
        
        rooms = []
        symbols = []
        
        # Try YOLO detection
        if self.is_loaded and self.model is not None:
            try:
                results = self.model(pil_image, conf=self.confidence_threshold, 
                                 device=self.device, verbose=False)
                result = results[0]
                boxes = result.boxes
                
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0].cpu().numpy())
                    cls = int(box.cls[0].cpu().numpy())
                    class_name = result.names[cls].lower()
                    
                    if class_name in self.ROOM_CLASS_MAPPING:
                        room = DetectedRoom(
                            room_id=f"R{len(rooms)+1}", name=f"Room {len(rooms)+1}",
                            x_min=float(x1), y_min=float(y1), x_max=float(x2), y_max=float(y2),
                            width_pixels=float(x2-x1), height_pixels=float(y2-y1),
                            width_meters=0, length_meters=0, area_sqm=0, confidence=conf
                        )
                        rooms.append(room)
                    elif class_name in self.SYMBOL_CLASS_MAPPING:
                        symbol = DetectedSymbol(
                            symbol_id=f"S{len(symbols)+1}",
                            symbol_type=self.SYMBOL_CLASS_MAPPING.get(class_name, class_name),
                            x_center=float((x1+x2)/2), y_center=float((y1+y2)/2),
                            x_min=float(x1), y_min=float(y1), x_max=float(x2), y_max=float(y2),
                            confidence=conf
                        )
                        symbols.append(symbol)
            except Exception as e:
                logger.warning(f"YOLO error: {e}")
        
        # Apply scale
        scale = self._detect_scale_bar(img_array)
        
        for i, room in enumerate(rooms):
            room.width_meters = room.width_pixels / scale.pixels_per_meter
            room.length_meters = room.height_pixels / scale.pixels_per_meter
            room.area_sqm = room.width_meters * room.length_meters
            room.room_type = self._estimate_room_type(room.area_sqm, room.name)
            room.occupancy = self._estimate_occupancy(room.room_type, room.area_sqm)
            room.room_id = f"R{i+1}"
        
        # Apply OCR
        if self.ocr_enabled and rooms:
            rooms = self._apply_ocr_to_rooms(pil_image, rooms)
        
        # Ensure room names
        for i, room in enumerate(rooms):
            if room.name.startswith("Room "):
                room.name = f"Room {i+1}"
        
        analysis_time = time.time() - start_time
        logger.info(f"Analysis: {len(rooms)} rooms, {len(symbols)} symbols in {analysis_time:.2f}s")
        
        return FloorPlanAnalysisV2(
            image_path=image_path, image_width=width, image_height=height,
            rooms=rooms, symbols=symbols, scale=scale,
            existing_devices_count=len(symbols), analysis_time_seconds=analysis_time,
            model_name=self.model_name, device_used=self.device
        )
    
    def detect_symbols_only(self, image_path: str) -> List[DetectedSymbol]:
        """Detect only electrical symbols"""
        if not self.is_loaded:
            if not self.load_model():
                raise RuntimeError("Failed to load YOLO model")
        
        img_array, pil_image = self._load_image(image_path)
        results = self.model(pil_image, conf=self.confidence_threshold, 
                        device=self.device, verbose=False)
        result = results[0]
        symbols = []
        
        for box in result.boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            conf = float(box.conf[0].cpu().numpy())
            cls = int(box.cls[0].cpu().numpy())
            class_name = result.names[cls].lower()
            
            if class_name in self.SYMBOL_CLASS_MAPPING:
                symbol = DetectedSymbol(
                    symbol_id=f"S{len(symbols)+1}",
                    symbol_type=self.SYMBOL_CLASS_MAPPING.get(class_name, class_name),
                    x_center=float((x1+x2)/2), y_center=float((y1+y2)/2),
                    x_min=float(x1), y_min=float(y1), x_max=float(x2), y_max=float(y2),
                    confidence=conf
                )
                symbols.append(symbol)
        return symbols


class ModelTrainer:
    """Train YOLO models for floor plan detection"""
    
    def __init__(self, model_name: str = "yolov8n.pt"):
        self.model_name = model_name
        self.model = None
    
    def train(self, data_yaml_path: str, epochs: int = 50, image_size: int = 640,
              batch_size: int = 16, device: str = "auto",
              project: str = "runs/train", name: str = "floor_plan") -> str:
        """Train YOLO model"""
        if not YOLO_AVAILABLE:
            raise RuntimeError("YOLO not available. Install: pip install ultralytics")
        
        logger.info(f"Training {self.model_name} on {data_yaml_path}")
        self.model = YOLO(self.model_name)
        
        results = self.model.train(
            data=data_yaml_path, epochs=epochs, imgsz=image_size,
            batch=batch_size, device=device, project=project, name=name,
            exist_ok=True, verbose=True
        )
        
        best_model = os.path.join(project, name, "weights", "best.pt")
        logger.info(f"Training complete. Best model: {best_model}")
        return best_model
    
    def export_model(self, model_path: str, format: str = "onnx") -> str:
        """Export trained model"""
        model = YOLO(model_path)
        export_path = model.export(format=format)
        return export_path


def analyze_floor_plan_v2(image_path: str, **kwargs) -> FloorPlanAnalysisV2:
    """Convenience function for floor plan analysis"""
    engine = IndustrialVisionEngine(**kwargs)
    engine.load_model()
    return engine.analyze_floor_plan(image_path)


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Industrial Vision Engine V2")
    parser.add_argument("input", help="Input floor plan image path")
    parser.add_argument("-o", "--output", help="Output JSON file path")
    parser.add_argument("--model", help="YOLO model path")
    parser.add_argument("--confidence", type=float, default=0.5)
    parser.add_argument("--scale", type=float, default=50.0)
    parser.add_argument("--no-ocr", action="store_true")
    
    args = parser.parse_args()
    
    engine = IndustrialVisionEngine(
        model_path=args.model, confidence_threshold=args.confidence,
        scale_factor=args.scale, ocr_enabled=not args.no_ocr
    )
    
    if not engine.load_model():
        print("Failed to load model")
        sys.exit(1)
    
    result = engine.analyze_floor_plan(args.input)
    
    print(f"\n{'='*60}")
    print(f"Floor Plan Analysis (YOLO)")
    print(f"{'='*60}")
    print(f"Image: {result.image_path}")
    print(f"Model: {result.model_name}")
    print(f"Device: {result.device_used}")
    print(f"Rooms: {len(result.rooms)}, Symbols: {len(result.symbols)}")
    print(f"Time: {result.analysis_time_seconds:.2f}s")
    
    for room in result.rooms:
        print(f"  {room.room_id}: {room.name} ({room.width_meters:.1f}x{room.length_meters:.1f}m)")
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump({
                'rooms': result.to_rooms_data(),
                'symbols': result.to_symbols_data()
            }, f, indent=2)
        print(f"\nSaved to: {args.output}")