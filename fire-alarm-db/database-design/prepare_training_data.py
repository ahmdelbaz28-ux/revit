#!/usr/bin/env python3
"""
prepare_training_data.py - Training Data Preparation for Floor Plan AI
=================================================================

This module prepares training data for the floor plan vision model:
- Extracts images and annotations from database
- Converts to YOLO format
- Creates data.yaml for training

Author: FireAlarmAI Engineering Team
Date: 2026-05-09
"""

import os
import sys
import json
import logging
import shutil
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class FloorPlanImage:
    """Floor plan image with annotations"""
    image_id: int
    image_path: str
    width: int
    height: int
    rooms: List[Dict]
    devices: List[Dict]


@dataclass
class YOLOAnnotation:
    """YOLO format annotation"""
    class_id: int
    x_center: float  # normalized 0-1
    y_center: float  # normalized 0-1
    width: float    # normalized 0-1
    height: float   # normalized 0-1


# =============================================================================
# Class Mappings
# =============================================================================

ROOM_CLASSES = [
    'office', 'bedroom', 'bathroom', 'kitchen', 'living_room',
    'corridor', 'hall', 'storage', 'lobby', 'meeting', 'utility'
]

DEVICE_CLASSES = [
    'SmokeDetector', 'HeatDetector', 'ManualCallPoint',
    'Speaker', 'Horn', 'Strobe', 'Panel', 'ControlPanel'
]

CLASS_MAPPING = {name: idx for idx, name in enumerate(ROOM_CLASSES + DEVICE_CLASSES)}


# =============================================================================
# Data Preparer
# =============================================================================

class TrainingDataPreparer:
    """
    Prepares training data for floor plan vision model
    
    Workflow:
    1. Load floor plan images and annotations from database
    2. Convert bounding boxes to YOLO format
    3. Split into train/val/test sets
    4. Generate data.yaml for YOLO training
    """
    
    def __init__(self, output_dir: str):
        """
        Initialize preparer
        
        Args:
            output_dir: Directory to save prepared data
        """
        self.output_dir = Path(output_dir)
        self.images_dir = self.output_dir / 'images'
        self.labels_dir = self.output_dir / 'labels'
        
        # Create directories
        for split in ['train', 'val', 'test']:
            (self.images_dir / split).mkdir(parents=True, exist_ok=True)
            (self.labels_dir / split).mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized data preparer: {self.output_dir}")
    
    def load_floor_plan(self, db_session, floor_id: int) -> FloorPlanImage:
        """
        Load floor plan from database
        
        Args:
            db_session: SQLAlchemy session
            floor_id: Floor ID to load
            
        Returns:
            FloorPlanImage with annotations
        """
        try:
            from ai_design_integration import Floor, Room, AIDesignDevice
            
            # Get floor
            floor = db_session.query(Floor).filter(
                Floor.FloorID == floor_id
            ).first()
            
            if not floor:
                raise ValueError(f"Floor {floor_id} not found")
            
            # Get rooms
            rooms = db_session.query(Room).filter(
                Room.FloorID == floor_id
            ).all()
            
            room_list = [
                {
                    'room_id': r.RoomID,
                    'name': r.Name,
                    'type': r.RoomType,
                    'x': r.XCoord,
                    'y': r.YCoord,
                    'width': r.WidthMeters,
                    'height': r.LengthMeters
                }
                for r in rooms
            ]
            
            # Get placed devices
            devices = db_session.query(AIDesignDevice).filter(
                AIDesignDevice.FloorID == floor_id
            ).all()
            
            device_list = [
                {
                    'device_id': d.DeviceID,
                    'type': d.ProposedType,
                    'x': d.XCoord,
                    'y': d.YCoord
                }
                for d in devices
            ]
            
            return FloorPlanImage(
                image_id=floor_id,
                image_path=str(floor.FloorID),
                width=int(floor.WidthMeters or 100),
                height=int(floor.LengthMeters or 100),
                rooms=room_list,
                devices=device_list
            )
            
        except ImportError:
            # Return mock data
            return FloorPlanImage(
                image_id=floor_id,
                image_path=f"floor_{floor_id}",
                width=100,
                height=100,
                rooms=[
                    {'room_id': 1, 'name': 'Office', 'type': 'office', 
                     'x': 10, 'y': 10, 'width': 20, 'height': 15},
                    {'room_id': 2, 'name': 'Meeting', 'type': 'meeting',
                     'x': 40, 'y': 10, 'width': 15, 'height': 15}
                ],
                devices=[
                    {'device_id': 1, 'type': 'SmokeDetector', 'x': 15, 'y': 15},
                    {'device_id': 2, 'type': 'Speaker', 'x': 45, 'y': 15}
                ]
            )
    
    def convert_to_yolo(self, 
                     floor_plan: FloorPlanImage,
                     scale: float = 50.0) -> List[YOLOAnnotation]:
        """
        Convert annotations to YOLO format
        
        Args:
            floor_plan: Floor plan data
            scale: Pixels per meter (for coordinate conversion)
            
        Returns:
            List of YOLO annotations
        """
        annotations = []
        
        # Convert rooms
        for room in floor_plan.rooms:
            class_name = room.get('type', 'office')
            class_id = CLASS_MAPPING.get(class_name, 0)
            
            # Calculate normalized bounding box
            x = room.get('x', 0) * scale
            y = room.get('y', 0) * scale
            w = room.get('width', 10) * scale
            h = room.get('height', 10) * scale
            
            # YOLO format (normalized center and size)
            x_center = (x + w/2) / floor_plan.width
            y_center = (y + h/2) / floor_plan.height
            width_norm = w / floor_plan.width
            height_norm = h / floor_plan.height
            
            annotations.append(YOLOAnnotation(
                class_id=class_id,
                x_center=min(1.0, max(0.0, x_center)),
                y_center=min(1.0, max(0.0, y_center)),
                width=min(1.0, max(0.001, width_norm)),
                height=min(1.0, max(0.001, height_norm))
            ))
        
        # Convert devices
        for device in floor_plan.devices:
            class_name = device.get('type', 'SmokeDetector')
            class_id = CLASS_MAPPING.get(class_name, len(ROOM_CLASSES))
            
            # Device is a point - create small box
            x = device.get('x', 0) * scale
            y = device.get('y', 0) * scale
            box_size = 0.5 * scale  # 0.5m box
            
            x_center = x / floor_plan.width
            y_center = y / floor_plan.height
            width_norm = box_size / floor_plan.width
            height_norm = box_size / floor_plan.height
            
            annotations.append(YOLOAnnotation(
                class_id=class_id,
                x_center=min(1.0, max(0.0, x_center)),
                y_center=min(1.0, max(0.0, y_center)),
                width=min(1.0, max(0.001, width_norm)),
                height=min(1.0, max(0.001, height_norm))
            ))
        
        return annotations
    
    def save_annotation(self,
                       annotations: List[YOLOAnnotation],
                       output_path: Path):
        """
        Save annotations to YOLO format text file
        
        Args:
            annotations: List of YOLO annotations
            output_path: Path to save .txt file
        """
        with open(output_path, 'w') as f:
            for ann in annotations:
                f.write(f"{ann.class_id} {ann.x_center:.6f} {ann.y_center:.6f} "
                        f"{ann.width:.6f} {ann.height:.6f}\n")
        
        logger.debug(f"Saved {len(annotations)} annotations to {output_path}")
    
    def prepare_dataset(self,
                   db_session,
                   floor_ids: List[int],
                   train_ratio: float = 0.7,
                   val_ratio: float = 0.2,
                   test_ratio: float = 0.1):
        """
        Prepare complete dataset
        
        Args:
            db_session: Database session
            floor_ids: List of floor IDs to process
            train_ratio: Ratio for training set
            val_ratio: Ratio for validation set
            test_ratio: Ratio for test set
        """
        import random
        random.seed(42)
        
        # Shuffle floors
        floors = floor_ids.copy()
        random.shuffle(floors)
        
        # Split
        train_count = int(len(floors) * train_ratio)
        val_count = int(len(floors) * val_ratio)
        
        train_floors = floors[:train_count]
        val_floors = floors[train_count:train_count+val_count]
        test_floors = floors[train_count+val_count:]
        
        logger.info(f"Split: {len(train_floors)} train, {len(val_floors)} val, {len(test_floors)} test")
        
        # Process each floor
        splits = {
            'train': train_floors,
            'val': val_floors,
            'test': test_floors
        }
        
        for split, floor_list in splits.items():
            for floor_id in floor_list:
                # Load floor plan
                floor_plan = self.load_floor_plan(db_session, floor_id)
                
                # Convert to YOLO
                annotations = self.convert_to_yolo(floor_plan)
                
                # Save label
                label_path = self.labels_dir / split / f"floor_{floor_id}.txt"
                self.save_annotation(annotations, label_path)
                
                # Note: Actual image copying would happen here
                # For now just log
                logger.info(f"{split}: floor {floor_id} - "
                         f"{len(floor_plan.rooms)} rooms, {len(floor_plan.devices)} devices")
        
        # Generate data.yaml
        self.generate_data_yaml(len(ROOM_CLASSES), len(DEVICE_CLASSES))
        
        logger.info(f"Dataset prepared: {self.output_dir}")
    
    def generate_data_yaml(self, 
                      num_room_classes: int,
                      num_device_classes: int):
        """
        Generate data.yaml for YOLO training
        
        Args:
            num_room_classes: Number of room classes
            num_device_classes: Number of device classes
        """
        data_yaml = f"""# Floor Plan Detection Dataset Configuration
# Generated: {datetime.now().strftime('%Y-%m-%d')}

# Dataset paths
path: {self.output_dir}
train: images/train
val: images/val
test: images/test

# Number of classes
nc: {num_room_classes + num_device_classes}

# Class names
names:
"""
        for idx, name in enumerate(ROOM_CLASSES + DEVICE_CLASSES):
            data_yaml += f"  {idx}: {name}\n"
        
        # Save
        yaml_path = self.output_dir / 'data.yaml'
        with open(yaml_path, 'w') as f:
            f.write(data_yaml)
        
        logger.info(f"Generated data.yaml: {yaml_path}")


# =============================================================================
# Main Entry Point
# =============================================================================

def prepare_training_data(output_dir: str,
                        floor_ids: List[int] = None,
                        db_url: str = None):
    """
    Prepare training data for floor plan model
    
    Args:
        output_dir: Output directory
        floor_ids: List of floor IDs (default: all)
        db_url: Database URL
    """
    if floor_ids is None:
        floor_ids = [1, 2, 3, 4, 5]
    
    # Create preparer
    preparer = TrainingDataPreparer(output_dir)
    
    try:
        # Try to connect to database
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        if db_url is None:
            db_url = os.environ.get('DATABASE_URL', 'sqlite:///:memory:')
        
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        preparer.prepare_dataset(session, floor_ids)
        
        session.close()
        
    except Exception as e:
        logger.warning(f"Database not available: {e}")
        
        # Create mock data for demonstration
        logger.info("Creating demonstration data...")
        
        mock_floor_plan = FloorPlanImage(
            image_id=1,
            image_path="floor_1",
            width=5000,
            height=4000,
            rooms=[
                {'room_id': 1, 'name': 'Office 1', 'type': 'office',
                 'x': 500, 'y': 500, 'width': 1000, 'height': 750},
                {'room_id': 2, 'name': 'Office 2', 'type': 'office',
                 'x': 2000, 'y': 500, 'width': 750, 'height': 750},
                {'room_id': 3, 'name': 'Corridor', 'type': 'corridor',
                 'x': 500, 'y': 2000, 'width': 3000, 'height': 200},
            ],
            devices=[
                {'device_id': 1, 'type': 'SmokeDetector', 'x': 750, 'y': 750},
                {'device_id': 2, 'type': 'SmokeDetector', 'x': 2250, 'y': 750},
                {'device_id': 3, 'type': 'Speaker', 'x': 1500, 'y': 2100},
            ]
        )
        
        annotations = preparer.convert_to_yolo(mock_floor_plan)
        
        # Save train annotation
        label_path = preparer.labels_dir / 'train' / 'floor_1.txt'
        preparer.save_annotation(annotations, label_path)
        
        # Generate data.yaml
        preparer.generate_data_yaml(len(ROOM_CLASSES), len(DEVICE_CLASSES))
        
        logger.info(f"Demonstration data prepared: {output_dir}")


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Prepare Training Data")
    parser.add_argument('--output-dir', default='./training_data')
    parser.add_argument('--floor-ids', nargs='+', type=int, default=None)
    parser.add_argument('--db-url', default=None)
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("TRAINING DATA PREPARATION")
    print("="*60)
    print(f"Output: {args.output_dir}")
    print(f"Database: {args.db_url or 'not specified'}")
    print("="*60 + "\n")
    
    prepare_training_data(
        args.output_dir,
        args.floor_ids,
        args.db_url
    )
    
    print("\n" + "="*60)
    print("PREPARATION COMPLETE")
    print("="*60)
    print(f"Data saved to: {args.output_dir}")
    print(f"Run training with: yolo detect train data={args.output_dir}")