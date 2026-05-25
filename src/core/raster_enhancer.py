"""
RasterEnhancer - Computer Vision for Fire Alarm Drawings
====================================================

Turns raster/scanned PDFs into extractable content using:
- OpenCV for image enhancement and line detection
- Tesseract (when available) for OCR text extraction
- pdf2image for converting PDF pages to images

This is the bridge that converts "rejected" drawings to processable ones.
"""

import cv2
import fitz  # PyMuPDF for raster detection
import numpy as np
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple, Dict
from pdf2image import convert_from_path


@dataclass
class EnhancementResult:
    """Result from enhancing a raster PDF."""
    success: bool
    confidence: float  # 0.0 to 1.0
    text_extracted: str  # OCR text if available
    scale_estimate: Optional[float]  # meters per PDF unit
    method: str  # How we got the scale
    warnings: List[str]
    enhanced_image_path: Optional[str] = None


class RasterEnhancer:
    """Enhance raster PDFs to extract meaningful content."""
    
    # Standard architectural scales in pixels per meter
    # These are estimates based on typical drawing scales
    SCALE_PATTERNS = {
        "1/8\"=1'-0\"": 96.0,    # 1/8 inch = 1 foot = 96 px/m
        "1/4\"=1'-0\"": 192.0,   # 1/4 inch = 1 foot
        "3/32\"=1'-0\"": 96.0 * 3/32 * 12,  # ~101.6
        "1:100": 100.0,        # 1:100 metric
        "1:50": 50.0,         # 1:50 metric
    }
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self._doc = None
        
    def _load_doc(self):
        """Load PDF document."""
        if self._doc is None:
            self._doc = fitz.open(self.pdf_path)
        return self._doc
    
    def is_raster(self) -> bool:
        """Check if PDF is raster (scanned)."""
        doc = self._load_doc()
        # Check first page for raster content
        page = doc[0]
        images = page.get_images()
        text = page.get_text().strip()
        
        # Pure vector PDFs have little/no raster and have text
        has_text = len(text) > 100
        has_images = len(images) > 0
        
        # If lots of images and little text = likely raster
        if has_images and not has_text:
            return True
        if has_images and len(text) < len(" scale ") * 2:
            return True
        return False
    
    def enhance_image(self, page_num: int = 0, dpi: int = 300) -> np.ndarray:
        """
        Convert page to enhanced image for processing.
        
        Args:
            page_num: Page index (0-based)
            dpi: Resolution for conversion (higher = better OCR)
        
        Returns:
            Enhanced numpy array (image)
        """
        doc = self._load_doc()
        
        # Convert PDF page to image
        try:
            # Use pdf2image for high quality
            images = convert_from_path(
                self.pdf_path,
                first_page=page_num + 1,
                last_page=page_num + 1,
                dpi=dpi,
                fmt='png'
            )
            if not images:
                raise ValueError("No images converted")
            
            img = images[0]
            # Convert PIL to grayscale numpy
            gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
            
        except Exception as e:
            # Fallback: extract page as image
            page = doc[page_num]
            pix = page.get_pixmap(dpi=dpi)
            img_data = pix.tobytes("png")
            nparr = np.frombuffer(img_data, np.uint8)
            gray = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        
        # Apply enhancements for better OCR/line detection
        enhanced = self._apply_enhancements(gray)
        
        return enhanced
    
    def _apply_enhancements(self, gray: np.ndarray) -> np.ndarray:
        """
        Apply image enhancements for better feature detection.
        
        Steps:
        1. Denoise - remove noise
        2. Sharpen - enhance edges
        3. Threshold - clean up backgrounds
        4. Dilate - thicken lines for detection
        """
        # 1. Denoise
        denoised = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7)
        
        # 2. Increase contrast
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        contrast = clahe.apply(denoised)
        
        # 3. Sharpen
        kernel = np.array([[-1,-1,-1],
                          [-1, 9,-1],
                          [-1,-1,-1]])
        sharpened = cv2.filter2D(contrast, -1, kernel)
        
        # 4. Clean threshold
        _, thresh = cv2.threshold(sharpened, 0, 255, 
                                  cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        return thresh
    
    def detect_lines(self, enhanced: np.ndarray) -> List[Dict]:
        """
        Detect horizontal and vertical lines using HoughLines.
        
        Returns:
            List of detected lines with angle, length, position
        """
        lines = []
        
        # Detect lines using probabilistic Hough transform
        detected = cv2.HoughLinesP(
            enhanced,
            rho=1,
            theta=np.pi/180,
            threshold=50,
            minLineLength=30,
            maxLineGap=10
        )
        
        if detected is None:
            return lines
        
        for line in detected:
            x1, y1, x2, y2 = line[0]
            
            # Calculate angle
            angle = np.arctan2(y2-y1, x2-x1) * 180 / np.pi
            
            # Calculate length
            length = np.sqrt((x2-x1)**2 + (y2-y1)**2)
            
            lines.append({
                'x1': x1, 'y1': y1,
                'x2': x2, 'y2': y2,
                'angle': angle,
                'length': length,
                'is_horizontal': abs(angle) < 10 or abs(angle - 180) < 10,
                'is_vertical': abs(angle - 90) < 10 or abs(angle + 90) < 10,
            })
        
        return lines
    
    def extract_text(self, enhanced: np.ndarray) -> str:
        """
        Extract text using Tesseract OCR.
        
        Note: Requires tesseract-ocr to be installed on system.
        """
        try:
            import pytesseract
            text = pytesseract.image_to_string(enhanced)
            return text
        except Exception as e:
            return ""
    
    def find_scale_bar(self, text: str) -> Optional[float]:
        """
        Find scale information in extracted text.
        
        Searches for common scale patterns like:
        - "1/8\" = 1'-0\""
        - "1:100"
        - "SCALE: 1:50"
        """
        import re
        
        patterns = [
            r'(\d+/\d+)"\s*=\s*(\d+)',  # 1/8" = 1'-0"
            r'(\d+/\d+)\s*=\s*(\d+)',     # 1/8=1'-0"
            r'(\d+:\d+)',                 # 1:100, 1:50
            r'SCALE:\s*(\d+:\d+)',       # SCALE: 1:100
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Try to parse the scale
                scale_text = match.group(1)
                if '/' in scale_text:
                    # Convert architectural scale
                    parts = scale_text.split('/')
                    if len(parts) == 2:
                        frac = int(parts[0]) / int(parts[1])
                        # 1/8" = 1' means 96 pixels per foot = 96 * 12 / 1 = 1152 px/m
                        px_per_inch = frac * 12
                        return px_per_inch * 12  # Convert to meters
                
                if ':' in scale_text:
                    # Metric scale like 1:100
                    ratio = scale_text.split(':')[1]
                    try:
                        return float(ratio)
                    except:
                        pass
        
        return None
    
    def estimate_scale_from_lines(self, lines: List[Dict]) -> Optional[float]:
        """
        Estimate scale from detected lines.
        
        This uses line lengths to estimate the drawing scale.
        """
        if not lines:
            return None
        
        # Focus on horizontal/vertical lines
        h_lines = [l for l in lines if l['is_horizontal'] and l['length'] > 100]
        
        if not h_lines:
            return None
        
        # Sort by length
        h_lines.sort(key=lambda x: x['length'], reverse=True)
        
        # Take top 5 lengths
        top_lengths = [l['length'] for l in h_lines[:5]]
        avg_length = sum(top_lengths) / len(top_lengths)
        
        # Common architectural lengths in feet:
        # 10', 20', 30', 40', 50', 60', 100'
        # Convert to pixels at various scales
        
        # If avg_length is around 96-192, likely 1:100 scale
        if 50 < avg_length < 200:
            return 100.0  # Assume 1:100
        
        return None
    
    def process(self) -> EnhancementResult:
        """
        Main processing: enhance and extract from raster PDF.
        
        Returns:
            EnhancementResult with extracted data
        """
        warnings = []
        
        # Check if raster
        if not self.is_raster():
            return EnhancementResult(
                success=False,
                confidence=0.0,
                text_extracted="",
                scale_estimate=None,
                method="not_raster",
                warnings=["PDF is vector-based, no enhancement needed"]
            )
        
        # Enhance first page (usually contains scale)
        try:
            enhanced = self._get_image(dpi=300)
        except Exception as e:
            return EnhancementResult(
                success=False,
                confidence=0.0,
                text_extracted="",
                scale_estimate=None,
                method="conversion_failed",
                warnings=[f"Failed to convert PDF: {e}"]
            )
        
        # Extract text
        text = ""
        try:
            text = self.extract_text(enhanced)
        except Exception as e:
            warnings.append(f"OCR failed: {e}")
        
        # Find scale in text
        scale = self.find_scale_bar(text)
        method = "text_ocr"
        
        # If no text scale, try line detection
        if scale is None:
            try:
                lines = self.detect_lines(enhanced)
                scale = self.estimate_scale_from_lines(lines)
                method = "line_detection"
            except:
                pass
        
        if scale is None:
            warnings.append("Could not determine scale")
        
        # Calculate confidence
        confidence = 0.0
        if scale:
            confidence = 0.7  # Base
            if text:
                confidence += 0.2
            if len(lines) > 10:
                confidence += 0.1
        else:
            confidence = 0.3  # Best effort
        
        return EnhancementResult(
            success=scale is not None,
            confidence=min(1.0, confidence),
            text_extracted=text,
            scale_estimate=scale,
            method=method,
            warnings=warnings
        )
    
    def _get_image(self, dpi: int = 300) -> np.ndarray:
        """Get enhanced image from first page."""
        try:
            images = convert_from_path(
                self.pdf_path,
                first_page=1,
                last_page=1,
                dpi=dpi,
                fmt='png'
            )
            if images:
                gray = cv2.cvtColor(np.array(images[0]), cv2.COLOR_RGB2GRAY)
                return self._apply_enhancements(gray)
        except:
            pass
        
        # Fallback
        doc = self._load_doc()
        pix = doc[0].get_pixmap(dpi=dpi)
        img_data = pix.tobytes("png")
        nparr = np.frombuffer(img_data, np.uint8)
        gray = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        return self._apply_enhancements(gray)


def enhance_raster(pdf_path: str) -> EnhancementResult:
    """
    Convenience function to enhance a raster PDF.
    
    Returns EnhancementResult with extracted scale and text.
    """
    enhancer = RasterEnhancer(pdf_path)
    return enhancer.process()