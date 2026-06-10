"""
SGL Validation Engine - Input Validation Subsystem
"""

import json
import re
from typing import Dict, Any, Tuple
from ..models import ExecutionRequest
from ..exceptions import ValidationException


class InputValidationEngine:
    """
    Input Validation Engine - Strict Schema Validation
    Enforces max payload size, rejects malformed JSON, sanitizes fields
    """
    
    def __init__(self, max_payload_size: int = 10 * 1024 * 1024):  # 10MB default
        self.max_payload_size = max_payload_size
        self.validation_rules = {}
        
    def validate_request(self, request: ExecutionRequest) -> Tuple[bool, str]:
        """
        Validate the execution request according to strict rules
        
        Args:
            request: The execution request to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check payload size
            payload_str = json.dumps(request.payload)
            payload_size = len(payload_str.encode('utf-8'))
            
            if payload_size > self.max_payload_size:
                return False, f"Payload size {payload_size} exceeds maximum allowed size {self.max_payload_size}"
            
            # Validate JSON structure (malformed JSON would cause earlier failure)
            # But we can do additional structural checks here
            if not self._validate_json_structure(request.payload):
                return False, "Malformed JSON structure detected"
            
            # Sanitize the payload
            sanitized_payload = self._sanitize_payload(request.payload)
            request.payload = sanitized_payload
            
            # Validate specific fields if needed
            if not self._validate_specific_fields(request):
                return False, "Specific field validation failed"
                
            request.validated = True
            return True, "Validation passed"
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    def _validate_json_structure(self, obj: Any) -> bool:
        """Validate basic JSON structure"""
        try:
            # Check for circular references by serializing
            json.dumps(obj)
            return True
        except (TypeError, ValueError):
            return False
    
    def _sanitize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize the payload by removing potentially dangerous fields"""
        sanitized = {}
        
        for key, value in payload.items():
            # Remove potentially dangerous keys
            if self._is_safe_key(key):
                if isinstance(value, str):
                    sanitized[key] = self._sanitize_string(value)
                elif isinstance(value, dict):
                    sanitized[key] = self._sanitize_payload(value)
                elif isinstance(value, list):
                    sanitized[key] = self._sanitize_list(value)
                else:
                    # Keep primitive types as-is
                    sanitized[key] = value
        
        return sanitized
    
    def _is_safe_key(self, key: str) -> bool:
        """Check if a key is safe to include in the payload"""
        # Block keys that could be used for injection attacks
        dangerous_patterns = [
            r'\$',  # Dollar sign (potential MongoDB injection)
            r'\.',  # Dot (potential MongoDB injection)
            r'<script',  # Script tags
            r'javascript:',  # JavaScript protocol
            r'on\w+\s*=',  # Event handlers
        ]
        
        lower_key = key.lower()
        for pattern in dangerous_patterns:
            if re.search(pattern, lower_key):
                return False
        
        return True
    
    def _sanitize_string(self, value: str) -> str:
        """Sanitize a string value"""
        # Remove potentially dangerous content
        sanitized = re.sub(r'<script[^>]*>.*?</script>', '', value, flags=re.IGNORECASE | re.DOTALL)
        sanitized = re.sub(r'javascript:', '', sanitized, flags=re.IGNORECASE)
        sanitized = sanitized.strip()
        
        return sanitized
    
    def _sanitize_list(self, lst: list) -> list:
        """Sanitize a list by sanitizing each element"""
        sanitized = []
        
        for item in lst:
            if isinstance(item, str):
                sanitized.append(self._sanitize_string(item))
            elif isinstance(item, dict):
                sanitized.append(self._sanitize_payload(item))
            elif isinstance(item, list):
                sanitized.append(self._sanitize_list(item))
            else:
                sanitized.append(item)
        
        return sanitized
    
    def _validate_specific_fields(self, request: ExecutionRequest) -> bool:
        """Validate specific fields in the request"""
        # Validate user_id format (basic alphanumeric with some allowed special chars)
        if not re.match(r'^[a-zA-Z0-9_-]+$', request.user_id):
            return False
            
        # Validate idempotency_key format (basic alphanumeric with hyphens/underscores)
        if not re.match(r'^[a-zA-Z0-9_-]+$', request.idempotency_key):
            return False
            
        # Validate risk level
        if request.risk_level.value not in ['low', 'medium', 'high', 'critical']:
            return False
            
        return True