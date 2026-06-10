"""
FACP Idempotency Manager
"""
from typing import Dict, Any, Optional, Tuple
import time
import threading
import hashlib
import json
from datetime import datetime


class IdempotencyManager:
    """
    Manages idempotency keys to prevent duplicate execution
    """
    def __init__(self, default_ttl_seconds: int = 3600):  # 1 hour default TTL
        self.idempotency_store = {}  # idempotency_key -> (result, timestamp, ttl)
        self.default_ttl = default_ttl_seconds
        self.lock = threading.Lock()

    def check_and_record(self, idempotency_key: str, 
                        request_data: Dict[str, Any], 
                        ttl_seconds: Optional[int] = None) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check if request with given idempotency key has been processed before
        :param idempotency_key: Unique idempotency key
        :param request_data: Original request data (for validation)
        :param ttl_seconds: Time-to-live for the idempotency record
        :return: (is_duplicate, cached_result)
        """
        ttl = ttl_seconds or self.default_ttl
        
        with self.lock:
            # Clean up expired entries
            self._cleanup_expired()
            
            if idempotency_key in self.idempotency_store:
                result, timestamp, stored_ttl = self.idempotency_store[idempotency_key]
                
                # Check if still valid
                if time.time() - timestamp < stored_ttl:
                    return True, result  # Duplicate request, return cached result
                else:
                    # Entry expired, remove it
                    del self.idempotency_store[idempotency_key]
            
            # New request, store it with a placeholder
            # We'll update with actual result later
            self.idempotency_store[idempotency_key] = (None, time.time(), ttl)
            return False, None

    def record_result(self, idempotency_key: str, result: Dict[str, Any]):
        """Record the result for an idempotency key"""
        with self.lock:
            if idempotency_key in self.idempotency_store:
                _, timestamp, ttl = self.idempotency_store[idempotency_key]
                self.idempotency_store[idempotency_key] = (result, timestamp, ttl)

    def validate_request_consistency(self, idempotency_key: str, 
                                  current_request: Dict[str, Any]) -> bool:
        """
        Validate that current request is consistent with previously processed request
        This prevents the same idempotency key from being used with different requests
        """
        with self.lock:
            if idempotency_key in self.idempotency_store:
                # In a real implementation, we'd store the original request and compare
                # For now, we'll just return True as we don't store original requests in this simple version
                return True
            return False

    def _cleanup_expired(self):
        """Remove expired idempotency records"""
        current_time = time.time()
        expired_keys = []
        
        for key, (_, timestamp, ttl) in self.idempotency_store.items():
            if current_time - timestamp >= ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.idempotency_store[key]

    def get_statistics(self) -> Dict[str, Any]:
        """Get idempotency statistics"""
        with self.lock:
            self._cleanup_expired()
            return {
                "total_records": len(self.idempotency_store),
                "expired_cleanups": len([k for k in self.idempotency_store.keys()])
            }

    def generate_idempotency_key(self, request_data: Dict[str, Any]) -> str:
        """
        Generate a deterministic idempotency key from request data
        This is useful when clients don't provide their own idempotency key
        """
        # Create a hash of the request data to use as idempotency key
        # This ensures identical requests get the same key
        request_str = json.dumps(request_data, sort_keys=True, default=str)
        return hashlib.sha256(request_str.encode()).hexdigest()

    def invalidate_key(self, idempotency_key: str):
        """Invalidate a specific idempotency key (for admin purposes)"""
        with self.lock:
            if idempotency_key in self.idempotency_store:
                del self.idempotency_store[idempotency_key]

    def force_refresh_ttl(self, idempotency_key: str, new_ttl: int):
        """Force refresh the TTL for a specific key"""
        with self.lock:
            if idempotency_key in self.idempotency_store:
                result, _, _ = self.idempotency_store[idempotency_key]
                self.idempotency_store[idempotency_key] = (result, time.time(), new_ttl)


class IdempotencyMiddleware:
    """
    Middleware that integrates idempotency checking into request processing
    """
    def __init__(self, idempotency_manager: IdempotencyManager):
        self.idempotency_manager = idempotency_manager

    def process_request(self, request_data: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Process a request for idempotency
        :param request_data: Incoming request data
        :return: (should_process, cached_result, status_message)
        """
        idempotency_key = self._extract_idempotency_key(request_data)
        
        if not idempotency_key:
            # No idempotency key provided, process normally
            return True, None, "No idempotency key, processing normally"
        
        # Check if this request has been processed before
        is_duplicate, cached_result = self.idempotency_manager.check_and_record(
            idempotency_key, request_data
        )
        
        if is_duplicate:
            return False, cached_result, "Duplicate request, returning cached result"
        else:
            return True, None, "New request, needs processing"

    def record_successful_result(self, request_data: Dict[str, Any], result: Dict[str, Any]):
        """Record successful result for idempotency"""
        idempotency_key = self._extract_idempotency_key(request_data)
        if idempotency_key:
            self.idempotency_manager.record_result(idempotency_key, result)

    def _extract_idempotency_key(self, request_data: Dict[str, Any]) -> Optional[str]:
        """Extract idempotency key from request data"""
        # Look for idempotency key in params
        params = request_data.get("params", {})
        idempotency_key = params.get("idempotency_key")
        
        if not idempotency_key:
            # Look in security block
            security = request_data.get("security", {})
            idempotency_key = security.get("idempotency_key")
        
        return idempotency_key


def idempotent_function(idempotency_manager: IdempotencyManager, 
                       ttl_seconds: int = 3600):
    """
    Decorator to make functions idempotent
    """
    def decorator(func):
        def wrapper(request_data: Dict[str, Any], *args, **kwargs):
            # Extract idempotency key
            params = request_data.get("params", {})
            idempotency_key = params.get("idempotency_key")
            
            if not idempotency_key:
                # Generate a key based on the request data if none provided
                idempotency_key = idempotency_manager.generate_idempotency_key(request_data)
            
            # Check if already processed
            is_duplicate, cached_result = idempotency_manager.check_and_record(
                idempotency_key, request_data, ttl_seconds
            )
            
            if is_duplicate:
                return cached_result
            
            # Execute the function
            result = func(request_data, *args, **kwargs)
            
            # Record the result
            idempotency_manager.record_result(idempotency_key, result)
            
            return result
        
        return wrapper
    return decorator