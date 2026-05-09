#!/usr/bin/env python3
"""
auto_train.py - Automated Training Pipeline for Floor Plan Vision Model
==============================================================

Train YOLOv8 model on floor plan images and labels.

Usage:
    python auto_train.py /path/to/dataset
    python auto_train.py  # Uses DATASET_DIR env var
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def train_model(dataset_dir: str, epochs: int = 100, imgsz: int = 640, 
              batch: int = 8, patience: int = 20, device: str = 'auto'):
    """
    Train YOLOv8 model on floor plan dataset
    
    Args:
        dataset_dir: Path to dataset (with images/train, labels/train, etc.)
        epochs: Number of training epochs
        imgsz: Image size
        batch: Batch size
        patience: Early stopping patience
        device: Device to use (auto/cpu/cuda)
        
    Returns:
        Path to best model
    """
    # Try to import vision_engine_v2
    try:
        sys.path.insert(0, dataset_dir)
        from vision_engine_v2 import ModelTrainer
        logger.info("Using ModelTrainer from vision_engine_v2")
    except ImportError:
        logger.warning("vision_engine_v2 not found in dataset_dir")
        
        # Try to import from project
        try:
            from vision_engine_v2 import ModelTrainer
        except ImportError:
            # Use ultralytics directly
            from ultralytics import YOLO
            ModelTrainer = None
    
    # Check dataset structure
    dataset_path = Path(dataset_dir)
    data_yaml = dataset_path / 'data.yaml'
    
    if not data_yaml.exists():
        # Create data.yaml
        logger.info("Creating data.yaml...")
        create_data_yaml(dataset_path)
    
    # Train model
    logger.info(f"Starting training: epochs={epochs}, imgsz={imgsz}, batch={batch}")
    
    if ModelTrainer:
        trainer = ModelTrainer(model_name='yolov8n.pt')
        best_model = trainer.train(
            data=str(data_yaml),
            epochs=epochs,
            image_size=imgsz,
            batch_size=batch,
            device=device,
            project='runs/train',
            name='floor_plan'
        )
    else:
        # Use ultralytics directly
        model = YOLO('yolov8n.pt')
        results = model.train(
            data=str(data_yaml),
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            patience=patience,
            device=device,
            project='runs/train',
            name='floor_plan',
            exist_ok=True,
            verbose=True
        )
        best_model = 'runs/train/floor_plan/weights/best.pt'
        logger.info(f"Training complete. Best model: {best_model}")
    
    return best_model


def create_data_yaml(dataset_path: Path):
    """Create data.yaml for YOLO training"""
    # Count classes from label files
    classes = set()
    
    # Check train labels
    train_labels = dataset_path / 'labels' / 'train'
    if train_labels.exists():
        for label_file in train_labels.glob('*.txt'):
            with open(label_file, 'r') as f:
                for line in f:
                    class_id = int(line.split()[0])
                    classes.add(class_id)
    
    num_classes = max(classes) + 1 if classes else 2
    
    # Default class names
    names = {i: f'class_{i}' for i in range(num_classes)}
    
    # Check for room/device classes
    room_classes = [
        'office', 'bedroom', 'bathroom', 'kitchen', 'living_room',
        'corridor', 'hall', 'storage', 'lobby', 'meeting'
    ]
    device_classes = [
        'SmokeDetector', 'HeatDetector', 'ManualCallPoint',
        'Speaker', 'Horn', 'Strobe', 'Panel'
    ]
    
    all_names = room_classes + device_classes
    for i in range(num_classes):
        if i < len(all_names):
            names[i] = all_names[i]
    
    # Create data.yaml
    data_yaml = f"""# Floor Plan Detection Dataset
# Generated automatically

path: {dataset_path}
train: images/train
val: images/val
test: images/test

nc: {num_classes}

names:
"""
    for idx, name in names.items():
        data_yaml += f"  {idx}: {name}\n"
    
    with open(dataset_path / 'data.yaml', 'w') as f:
        f.write(data_yaml)
    
    logger.info(f"Created data.yaml with {num_classes} classes")


def evaluate_model(model_path: str, dataset_dir: str) -> dict:
    """
    Evaluate model on validation set
    
    Args:
        model_path: Path to trained model
        dataset_dir: Path to dataset
        
    Returns:
        Dict with metrics
    """
    from ultralytics import YOLO
    
    logger.info(f"Evaluating model: {model_path}")
    
    model = YOLO(model_path)
    results = model.val(
        data=str(Path(dataset_dir) / 'data.yaml'),
        verbose=True
    )
    
    # Extract metrics
    metrics = {
        'map50': float(results.box.map50),
        'map': float(results.box.map),
        'precision': float(results.box.mp),
        'recall': float(results.box.mr)
    }
    
    logger.info(f"mAP@50: {metrics['map50']:.3f}")
    logger.info(f"mAP@50:95: {metrics['map']:.3f}")
    logger.info(f"Precision: {metrics['precision']:.3f}")
    logger.info(f"Recall: {metrics['recall']:.3f}")
    
    return metrics


def export_model(model_path: str, output_dir: str = '.') -> str:
    """
    Export model to ONNX format
    
    Args:
        model_path: Path to trained model
        output_dir: Output directory
        
    Returns:
        Path to exported ONNX model
    """
    from ultralytics import YOLO
    
    logger.info(f"Exporting model to ONNX: {model_path}")
    
    model = YOLO(model_path)
    export_path = model.export(format='onnx')
    
    logger.info(f"Exported to: {export_path}")
    
    return export_path


def save_model_path(model_path: str, output_file: str = 'model_path.txt'):
    """Save best model path to file"""
    with open(output_file, 'w') as f:
        f.write(model_path)
    logger.info(f"Saved model path to: {output_file}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Train YOLO on floor plan dataset')
    parser.add_argument('dataset_dir', nargs='?', default=None,
                        help='Path to dataset directory')
    parser.add_argument('--epochs', type=int, default=100)
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--batch', type=int, default=8)
    parser.add_argument('--patience', type=int, default=20)
    parser.add_argument('--device', default='auto')
    
    args = parser.parse_args()
    
    # Get dataset directory
    dataset_dir = args.dataset_dir or os.environ.get('DATASET_DIR')
    
    if not dataset_dir:
        parser.error("dataset_dir required as argument or DATASET_DIR env var")
        sys.exit(1)
    
    if not os.path.isdir(dataset_dir):
        logger.error(f"Dataset directory not found: {dataset_dir}")
        sys.exit(1)
    
    logger.info(f"Dataset: {dataset_dir}")
    logger.info(f"Training config: epochs={args.epochs}, imgsz={args.imgsz}, batch={args.batch}")
    
    # Train model
    best_model = train_model(
        dataset_dir,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        patience=args.patience,
        device=args.device
    )
    
    # Evaluate
    logger.info("\n" + "="*50)
    logger.info("EVALUATION")
    logger.info("="*50)
    
    metrics = evaluate_model(best_model, dataset_dir)
    
    # Warn if mAP50 is low
    if metrics['map50'] < 0.5:
        logger.warning("mAP@50 < 0.5! More training data may be needed.")
        logger.warning("Consider: more epochs, more data, or data augmentation")
    
    # Export to ONNX
    logger.info("\n" + "="*50)
    logger.info("EXPORT")
    logger.info("="*50)
    
    export_path = export_model(best_model)
    save_model_path(best_model)
    
    logger.info("\n" + "="*50)
    logger.info("TRAINING COMPLETE")
    logger.info("="*50)
    logger.info(f"Best model: {best_model}")
    logger.info(f"ONNX export: {export_path}")
    logger.info(f"Model path saved to: model_path.txt")


if __name__ == "__main__":
    main()