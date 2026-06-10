"""
FACP Execution Context
"""
from typing import Dict, Any, Optional, List
import time
import threading
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum


class ExecutionMode(Enum):
    """Execution modes for different contexts"""
    DETERMINISTIC = "deterministic"
    ORCHESTRATED = "orchestrated"
    VALIDATION = "validation"


@dataclass
class ExecutionContextConfig:
    """Configuration for execution context"""
    mode: ExecutionMode = ExecutionMode.DETERMINISTIC
    timeout_ms: int = 8000
    max_recursion_depth: int = 5
    enable_tracing: bool = True
    enable_audit: bool = True
    fail_fast: bool = True
    retry_count: int = 0
    circuit_breaker_enabled: bool = True


class ExecutionContext:
    """
    Execution context that manages state and constraints for FACP execution
    """
    def __init__(self, config: ExecutionContextConfig = None, request_id: str = None):
        self.config = config or ExecutionContextConfig()
        self.request_id = request_id or f"ctx_{int(time.time())}_{threading.get_ident()}"
        self.start_time = time.time()
        self.execution_stack = []  # Track execution depth
        self.variables = {}  # Context variables
        self.audit_log = []  # Execution audit trail
        self.errors = []  # Execution errors
        self.results = {}  # Execution results
        self.lock = threading.Lock()
        self.circuit_open = False
        self.circuit_failure_count = 0
        self.circuit_last_failure = 0
        self.circuit_reset_timeout = 60  # 60 seconds before resetting circuit

    def enter_scope(self, scope_name: str, data: Dict[str, Any] = None):
        """Enter a new execution scope"""
        with self.lock:
            scope_info = {
                "name": scope_name,
                "enter_time": time.time(),
                "data": data or {},
                "depth": len(self.execution_stack)
            }
            self.execution_stack.append(scope_info)
            
            if self.config.enable_tracing:
                self._log_audit("scope_enter", scope_info)

    def exit_scope(self, scope_name: str = None):
        """Exit current execution scope"""
        with self.lock:
            if self.execution_stack:
                scope_info = self.execution_stack.pop()
                
                if scope_name and scope_info["name"] != scope_name:
                    self.add_error(f"Mismatched scope exit: expected {scope_name}, got {scope_info['name']}")
                
                exit_info = {
                    "name": scope_info["name"],
                    "exit_time": time.time(),
                    "duration": time.time() - scope_info["enter_time"],
                    "depth": len(self.execution_stack)
                }
                
                if self.config.enable_tracing:
                    self._log_audit("scope_exit", exit_info)

    def set_variable(self, key: str, value: Any):
        """Set a variable in the execution context"""
        with self.lock:
            self.variables[key] = value
            if self.config.enable_tracing:
                self._log_audit("variable_set", {"key": key, "value": str(value)[:100]})  # Truncate large values

    def get_variable(self, key: str, default: Any = None) -> Any:
        """Get a variable from the execution context"""
        with self.lock:
            return self.variables.get(key, default)

    def add_result(self, key: str, value: Any):
        """Add a result to the execution context"""
        with self.lock:
            self.results[key] = value
            if self.config.enable_tracing:
                self._log_audit("result_added", {"key": key, "value": str(value)[:100]})

    def get_result(self, key: str, default: Any = None) -> Any:
        """Get a result from the execution context"""
        with self.lock:
            return self.results.get(key, default)

    def add_error(self, error_msg: str, error_code: str = "GENERIC_ERROR"):
        """Add an error to the execution context"""
        with self.lock:
            error_info = {
                "timestamp": time.time(),
                "message": error_msg,
                "error_code": error_code,
                "stack_depth": len(self.execution_stack)
            }
            self.errors.append(error_info)
            
            # Handle circuit breaker logic
            if self.config.circuit_breaker_enabled:
                self._handle_circuit_breaker(error_info)
            
            if self.config.enable_tracing:
                self._log_audit("error_added", error_info)

    def has_errors(self) -> bool:
        """Check if execution context has errors"""
        with self.lock:
            return len(self.errors) > 0

    def get_errors(self) -> List[Dict[str, Any]]:
        """Get all errors from execution context"""
        with self.lock:
            return self.errors.copy()

    def is_timeout_exceeded(self) -> bool:
        """Check if execution has exceeded timeout"""
        elapsed_ms = (time.time() - self.start_time) * 1000
        return elapsed_ms > self.config.timeout_ms

    def get_elapsed_time_ms(self) -> float:
        """Get elapsed execution time in milliseconds"""
        return (time.time() - self.start_time) * 1000

    def get_current_depth(self) -> int:
        """Get current execution depth"""
        with self.lock:
            return len(self.execution_stack)

    def is_max_depth_exceeded(self) -> bool:
        """Check if maximum recursion depth is exceeded"""
        return self.get_current_depth() > self.config.max_recursion_depth

    def _log_audit(self, event_type: str, details: Dict[str, Any]):
        """Log audit event"""
        audit_entry = {
            "timestamp": time.time(),
            "event_type": event_type,
            "details": details,
            "request_id": self.request_id
        }
        self.audit_log.append(audit_entry)

    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Get execution audit log"""
        with self.lock:
            return self.audit_log.copy()

    def _handle_circuit_breaker(self, error_info: Dict[str, Any]):
        """Handle circuit breaker logic"""
        self.circuit_failure_count += 1
        self.circuit_last_failure = time.time()
        
        # Open circuit if too many failures in a short time
        if self.circuit_failure_count >= 5:  # 5 failures
            recent_failures = [
                entry for entry in self.audit_log 
                if entry["event_type"] == "error_added" and 
                time.time() - entry["timestamp"] < 30  # Last 30 seconds
            ]
            
            if len(recent_failures) >= 5:
                self.circuit_open = True

    def is_circuit_open(self) -> bool:
        """Check if circuit breaker is open"""
        if not self.config.circuit_breaker_enabled:
            return False
            
        # Reset circuit if enough time has passed
        if (self.circuit_open and 
            time.time() - self.circuit_last_failure > self.circuit_reset_timeout):
            self.circuit_open = False
            self.circuit_failure_count = 0
        
        return self.circuit_open

    def should_retry(self) -> bool:
        """Check if execution should be retried"""
        if self.config.retry_count <= 0:
            return False
            
        return len([e for e in self.errors if e.get("error_code") != "PERMANENT_ERROR"]) > 0

    def get_retry_count(self) -> int:
        """Get remaining retry count"""
        return max(0, self.config.retry_count - len([e for e in self.errors if e.get("error_code") != "PERMANENT_ERROR"]))

    def capture_snapshot(self) -> Dict[str, Any]:
        """Capture a snapshot of the current execution state"""
        with self.lock:
            return {
                "request_id": self.request_id,
                "config": self.config.__dict__,
                "start_time": self.start_time,
                "elapsed_time_ms": self.get_elapsed_time_ms(),
                "execution_stack_depth": len(self.execution_stack),
                "variables_count": len(self.variables),
                "results_count": len(self.results),
                "errors_count": len(self.errors),
                "audit_log_count": len(self.audit_log),
                "circuit_open": self.circuit_open,
                "circuit_failure_count": self.circuit_failure_count,
                "timeout_exceeded": self.is_timeout_exceeded(),
                "max_depth_exceeded": self.is_max_depth_exceeded()
            }

    def reset_for_retry(self):
        """Reset context for retry (keep some state, clear others)"""
        with self.lock:
            # Keep configuration and request ID
            # Clear execution-specific state
            self.start_time = time.time()
            self.execution_stack = []
            self.errors = []
            self.circuit_open = False
            self.circuit_failure_count = 0


class ContextManager:
    """Manager for execution contexts"""
    
    def __init__(self):
        self.contexts = {}  # request_id -> ExecutionContext
        self.lock = threading.Lock()
    
    def create_context(self, config: ExecutionContextConfig = None, request_id: str = None) -> ExecutionContext:
        """Create a new execution context"""
        context = ExecutionContext(config, request_id)
        
        with self.lock:
            self.contexts[context.request_id] = context
            
        return context
    
    def get_context(self, request_id: str) -> Optional[ExecutionContext]:
        """Get an existing execution context"""
        with self.lock:
            return self.contexts.get(request_id)
    
    def remove_context(self, request_id: str):
        """Remove an execution context"""
        with self.lock:
            if request_id in self.contexts:
                del self.contexts[request_id]
    
    def get_all_contexts(self) -> Dict[str, ExecutionContext]:
        """Get all active contexts"""
        with self.lock:
            return self.contexts.copy()
    
    def cleanup_expired_contexts(self, max_age_seconds: int = 3600):  # 1 hour
        """Clean up expired contexts"""
        with self.lock:
            current_time = time.time()
            expired_contexts = []
            
            for req_id, ctx in self.contexts.items():
                if current_time - ctx.start_time > max_age_seconds:
                    expired_contexts.append(req_id)
            
            for req_id in expired_contexts:
                del self.contexts[req_id]