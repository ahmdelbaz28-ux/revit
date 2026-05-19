#!/usr/bin/env python3
"""
train_floorplan_model.py - Train YOLO Model for Floor Plan Detection
=================================================================

Generates synthetic floor plan dataset and trains YOLOv8n model.

Usage:
    python train_floorplan_model.py
"""

import os
import sys
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

# Add database-design to path
sys.path.insert(0, os.path.dirname(__file__))

# =============================================================================
# Synthetic Dataset Generator
# =============================================================================

def generate_synthetic_floorplan(width: int = 640, height: int = 640) -> tuple:
    """Generate a synthetic floor plan image with rooms"""
    
    img = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    rooms = []
    num_rooms = random.randint(3, 6)
    
    # Generate room rectangles
    for i in range(num_rooms):
        x1 = random.randint(50, width - 200)
        y1 = random.randint(50, height - 200)
        w = random.randint(100, 250)
        h = random.randint(100, 250)
        
        # Draw room rectangle
        draw.rectangle([x1, y1, x1 + w, y1 + h], outline='black', width=3)
        
        # Add room label
        room_type = random.choice(['Office', 'Meeting', 'Corridor', 'Lobby', 'Storage'])
        rooms.append({
            'x': x1 + w // 2,
            'y': y1 + h // 2,
            'w': w,
            'h': h,
            'type': room_type
        })
    
    return img, rooms


def save_yolo_annotation(rooms: list, image_path: Path, labels_dir: Path, img_width: int = 640, img_height: int = 640):
    """Save YOLO format annotations"""
    
    label_file = labels_dir / f"{image_path.stem}.txt"
    
    with open(label_file, 'w') as f:
        for room in rooms:
            # YOLO format: class_id cx cy w h (normalized)
            cx = (room['x'] + room['w'] // 2) / img_width
            cy = (room['y'] + room['h'] // 2) / img_height
            w = room['w'] / img_width
            h = room['h'] / img_height
            
            # Map room type to class_id
            class_id = {'Office': 0, 'Meeting': 1, 'Corridor': 2, 'Lobby': 3, 'Storage': 4}.get(room['type'], 0)
            
            f.write(f"{class_id} {cx:.4f} {cy:.4f} {w:.4f} {h:.4f}\n")
    
    return label_file


def create_data_yaml():
    """Create dataset/data.yaml for YOLO training"""
    
    yaml_content = """# Floor Plan Dataset
path: dataset
train: images/train
val: images/train

nc: 5
names:
  0: Office
  1: Meeting
  2: Corridor
  3: Lobby
  4: Storage
"""
    
    with open('dataset/data.yaml', 'w') as f:
        f.write(yaml_content)
    
    print("Created dataset/data.yaml")


def train_model():
    """Train YOLOv8n model"""
    
    print("Starting YOLOv8n training for 50 epochs...")
    
    try:
        from ultralytics import YOLO
        
        # Use YOLOv8n (nano) - smallest and fastest
        model = YOLO('yolov8n.pt')
        
        # Train on our synthetic dataset
        results = model.train(
            data='dataset/data.yaml',
            epochs=50,
            imgsz=640,
            batch=16,
            name='floorplan',
            augment=True,
           mosaic=0.5,
            flipud=0.3,
            fliplr=0.3,
            hsv_h=0.02,
            save=True,
            project='runs',
            exist_ok=True,
            verbose=True
        )
        
        # Export best model
        best_model_path = 'runs/floorplan/weights/best.pt'
        export_path = 'fire-alarm-db/models/best.pt'
        
        if os.path.exists(best_model_path):
            # Copy to models directory
            import shutil
            os.makedirs(os.path.dirname(export_path), exist_ok=True)
            shutil.copy(best_model_path, export_path)
            
            # Update model_path.txt
            with open('fire-alarm-db/models/model_path.txt', 'w') as f:
                f.write(export_path)
            
            print(f"Model trained and saved to {export_path}")
            return True
        else:
            print("Training completed but best.pt not found")
            return False
            
    except ImportError as e:
        print(f"Ultralytics not available: {e}")
        return False


def main():
    """Main training pipeline"""
    
    base_dir = Path(__file__).parent
    dataset_dir = base_dir / 'dataset'
    images_dir = dataset_dir / 'images' / 'train'
    labels_dir = dataset_dir / 'labels' / 'train'
    
    # Create directories
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)
    
    print("Generating 50 synthetic floor plan images...")
    
    # Generate 50 training images
    for i in range(50):
        img, rooms = generate_synthetic_floorplan()
        
        # Save image
        img_path = images_dir / f"floorplan_{i:04d}.jpg"
        img.save(img_path, 'JPEG', quality=95)
        
        # Save YOLO annotation
        save_yolo_annotation(rooms, img_path, labels_dir)
    
    print(f"Generated {50} images with YOLO annotations")
    
    # Create data.yaml
    create_data_yaml()
    
    # Train model
    success = train_model()
    
    if success:
        print("✅ Floor plan model training complete!")
    else:
        print("⚠️ Model training skipped (dependencies missing)")
    
    return success


if __name__ == "__main__":
    main()