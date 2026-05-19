"""
Scale Bar Detector - Computer Vision for Scale Detection
==========================================================

Detects scale bars in raster/scanned PDFs using OpenCV.
 searches for common scale bar patterns:
- Line with dimension text (e.g., "0" ----- "10'-0"")
- Graphic scale bars with alternating colors
- CAD-style scale annotations

Returns scale in meters per PDF unit.
"""

import cv2
import numpy as np
import re
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict
from pdf2image import convert_from_path


@dataclass
class ScaleBarDetection:
    """Result of detecting a scale bar."""
    found: bool
    meters_per_unit: Optional[float]  # e.g., 101.6
    location: Tuple[int, int, int, int]  # bbox
    confidence: float  # 0.0 to 1.0
    method: str  # How detected


class ScaleBarDetector:
    """Detect scale bars in drawings using computer vision."""
    
    # Common scale bar patterns in architectural drawings
    SCALE_PATTERNS = {
        # Architectural (imperial)
        "1/8\"=1'-0\"": 96.0 * 12 / 8,    # 144 px/m
        "1/4\"=1'-0\"": 96.0 * 12 / 4,    # 288 px/m
        "3/32\"=1'-0\"": 96.0 * 12 * 3/32, # ~108 px/m
        "1/2\"=1'-0\"": 96.0 * 12 / 2,    # 576 px/m
        "1\"=1'-0\"": 96.0 * 12,          # 1152 px/m
        # Metric
        "1:100": 100.0,
        "1:50": 50.0,
        "1:200": 200.0,
        "1:500": 500.0,
    }
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self._doc = None
    
    def _load_doc(self):
        if self._doc is None:
            import fitz
            self._doc = fitz.open(self.pdf_path)
        return self._doc
    
    def get_page_image(self, page_num: int = 0, dpi: int = 300) -> np.ndarray:
        """Convert PDF page to image."""
        try:
            images = convert_from_path(
                self.pdf_path,
                first_page=page_num + 1,
                last_page=page_num + 1,
                dpi=dpi,
                fmt='png'
            )
            if images:
                # Convert to grayscale
                gray = cv2.cvtColor(np.array(images[0]), cv2.COLOR_RGB2GRAY)
                return gray
        except:
            pass
        
        # Fallback: use PyMuPDF
        doc = self._load_doc()
        pix = doc[page_num].get_pixmap(dpi=dpi)
        img_data = pix.tobytes("png")
        nparr = np.frombuffer(img_data, np.uint8)
        gray = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        return gray
    
    def _preprocess(self, gray: np.ndarray) -> np.ndarray:
        """Preprocess image for scale bar detection."""
        # Increase contrast
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        # Threshold
        _, binary = cv2.threshold(enhanced, 0, 255, 
                               cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        return binary
    
    def _find_horizontal_lines(self, binary: np.ndarray) -> List[Dict]:
        """Find horizontal lines (common in scale bars)."""
        # Morphological operations to connect lines
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 1))
        dilated = cv2.dilate(binary, kernel, iterations=2)
        
        # Find contours
        contours, _ = cv2.findContours(
            dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        lines = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            
            # Filter: horizontal lines (wide and short)
            if w > h * 3 and w > 50:
                lines.append({
                    'bbox': (x, y, w, h),
                    'aspect_ratio': w / max(h, 1),
                    'width': w,
                    'height': h,
                    'y_center': y + h // 2
                })
        
        return lines
    
    def _find_scale_bar_candidates(self, binary: np.ndarray) -> List[Dict]:
        """Find scale bar candidates (horizontal lines near bottom corners)."""
        h, w = binary.shape
        
        # Get horizontal lines
        lines = self._find_horizontal_lines(binary)
        
        candidates = []
        for line in lines:
            x, y, w, h = line['bbox']
            
            # Scale bars are typically in corners or at bottom
            in_corner = (y > binary.shape[0] * 0.7)  # Bottom third
            near_edge = (x < binary.shape[1] * 0.2) or (x > binary.shape[1] * 0.8)
            
            if in_corner or near_edge:
                candidates.append(line)
        
        return candidates
    
    def _extract_text_near_line(self, gray: np.ndarray, line_bbox: Tuple[int, int, int, int]) -> str:
        """Extract text near a detected line."""
        x, y, w, h = line_bbox
        h_img, w_img = gray.shape
        
        # Define ROI above the line
        roi_y = max(0, y - 50)
        roi_h = min(h_img - roi_y, y + h)
        
        roi = gray[roi_y:roi_y + roi_h, max(0, x - 50):x + w + 50]
        
        # Try OCR (if tesseract available)
        try:
            import pytesseract
            text = pytesseract.image_to_string(roi)
            return text
        except:
            # Fallback: try simple template matching
            return self._simple_text_detection(roi)
    
    def _simple_text_detection(self, roi: np.ndarray) -> str:
        """Simple text detection without OCR."""
        # Find connected components (potential characters)
        _, binary = cv2.threshold(roi, 127, 255, cv2.THRESH_BINARY)
        
        contours, _ = cv2.findContours(
            binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        # If we find small components, likely text
        if len(contours) > 5:
            return "[text_detected]"
        return ""
    
    def _parse_scale_text(self, text: str) -> Optional[float]:
        """Parse scale from text like '1/8"=1'-0"' or '1:100'."""
        text = text.lower().replace(' ', '')
        
        patterns = [
            # Architectural
            (r'(\d+/\d+)"?=?(\d+)\'-?(\d+)?', 'arch'),  # 1/8"=1'-0" or 1/8=1'-0"
            (r'(\d+/\d+)"?=1\'-0"', 'arch_short'),     # 1/8"=1'-0"
            (r'(\d+/\d+)\s*=\s*(\d+)', 'arch'),         # 1/8=10
            # Metric
            (r'(\d+):(\d+)', 'metric'),               # 1:100
            (r'scale[:\s]*(\d+):(\d+)', 'metric'),   # SCALE: 1:100
        ]
        
        for pattern, scale_type in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if scale_type == 'arch_short':
                    # 1/8" = 1'-0" = 96 * 12 / 8 = 144 px/m
                    frac = match.group(1).split('/')
                    if len(frac) == 2:
                        numerator = int(frac[0])
                        denominator = int(frac[1])
                        return 96.0 * 12 * numerator / denominator
                
                elif scale_type == 'arch':
                    # Parse architectural
                    parts = match.groups()
                    if '/' in parts[0]:
                        frac = parts[0].split('/')
                        numerator = int(frac[0])
                        denominator = int(frac[1])
                        return 96.0 * 12 * numerator / denominator
                    elif len(parts) >= 2:
                        # feet value
                        feet = int(parts[1])
                        return feet * 12 * 96  # approximate
                
                elif scale_type == 'metric':
                    # 1:100 means 100 units = 1 meter
                    ratio = int(match.group(2))
                    return float(ratio)
        
        return None
    
    def _detect_graphic_scale(self, gray: np.ndarray) -> Optional[Dict]:
        """Detect graphic scale bar (alternating colors pattern)."""
        h, w = gray.shape
        
        # Typically at bottom corners
        regions = [
            (h - 100, 0, 100, w),       # Bottom strip
            (0, 0, 100, 200),          # Top-left
            (0, w - 200, 100, 200),    # Top-right
        ]
        
        best_pattern = None
        best_confidence = 0
        
        for y, x, region_h, region_w in regions:
            if x + region_w > w or y + region_h > h:
                continue
            
            roi = gray[y:min(y+region_h, h), x:min(x+region_w, w)]
            if roi.size == 0:
                continue
            
            # Look for alternating pattern (classic scale bar)
            # Sum rows to find horizontal bars
            row_sums = np.sum(roi > 128, axis=1)
            
            # Find runs of similar values (bar segments)
            segments = []
            current = row_sums[0] if len(row_sums) > 0 else 0
            run_length = 0
            
            for val in row_sums:
                if abs(val - current) < 5:
                    run_length += 1
                else:
                    if run_length > 5:
                        segments.append((current, run_length))
                    current = val
                    run_length = 1
            
            # Check for alternating pattern (dark/light/dark/light)
            if len(segments) >= 3:
                diffs = [abs(segments[i][0] - segments[i+1][0]) 
                        for i in range(len(segments)-1)]
                if sum(d > 10 for d in diffs) >= 2:
                    best_pattern = {
                        'location': (x, y, region_w, region_h),
                        'segments': len(segments)
                    }
                    best_confidence = 0.6
        
        return best_pattern if best_pattern else None
    
    def detect(self, page_num: int = 0) -> ScaleBarDetection:
        """
        Main scale bar detection.
        
        Returns ScaleBarDetection with found scale.
        """
        # Get image
        try:
            gray = self.get_page_image(page_num, dpi=300)
        except Exception as e:
            return ScaleBarDetection(
                found=False,
                meters_per_unit=None,
                location=(0, 0, 0, 0),
                confidence=0.0,
                method="conversion_failed"
            )
        
        # Preprocess
        binary = self._preprocess(gray)
        
        # Try graphic scale bar detection
        graphic = self._detect_graphic_scale(gray)
        
        # Try line-based detection
        candidates = self._find_scale_bar_candidates(binary)
        
        scale = None
        location = (0, 0, 0, 0)
        confidence = 0.0
        method = "none"
        
        # Check each candidate
        for line in candidates:
            bbox = line['bbox']
            text = self._extract_text_near_line(gray, bbox)
            
            if text:
                parsed = self._parse_scale_text(text)
                if parsed:
                    scale = parsed
                    location = bbox
                    confidence = 0.8
                    method = "line_with_text"
                    break
        
        # If no line detection, try graphic pattern
        if not scale and graphic:
            location = graphic['location']
            # Estimate based on typical scale bar length
            confidence = 0.5
            method = "graphic_pattern"
        
        return ScaleBarDetection(
            found=scale is not None,
            meters_per_unit=scale,
            location=location,
            confidence=confidence,
            method=method
        )
    
    def detect_all_pages(self, max_pages: int = 3) -> ScaleBarDetection:
        """Try detecting scale on multiple pages."""
        doc = self._load_doc()
        
        for page_num in range(min(len(doc), max_pages)):
            result = self.detect(page_num)
            if result.found:
                return result
        
        # Return first page result anyway
        return self.detect(0)


def detect_scale_bar(pdf_path: str) -> ScaleBarDetection:
    """Convenience function."""
    detector = ScaleBarDetector(pdf_path)
    return detector.detect_all_pages()