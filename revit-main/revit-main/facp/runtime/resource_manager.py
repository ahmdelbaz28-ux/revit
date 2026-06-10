"""
FACP Resource Manager
"""
from typing import Dict, Any, Optional, Callable
import time
import threading
import psutil
import os
from dataclasses import dataclass
from enum import Enum


@dataclass
class ResourceConstraints:
    """Resource constraints for FACP execution"""
    timeout_ms: int = 8000  # 8 seconds default
    max_memory_mb: int = 128  # 128 MB soft limit
    max_recursion_depth: int = 5
    max_cpu_percent: float = 80.0  # Max CPU utilization
    max_concurrent_requests: int = 100


class ResourceType(Enum):
    """Types of resources managed"""
    CPU = "cpu"
    MEMORY = "memory"
    THREAD = "thread"
    NETWORK = "network"
    FILESYSTEM = "filesystem"


class ResourceManager:
    """
    Resource manager that enforces constraints on FACP execution
    """
    def __init__(self, constraints: ResourceConstraints = None):
        self.constraints = constraints or ResourceConstraints()
        self.active_resources = {}  # resource_id -> resource_info
        self.resource_locks = {}  # resource_type -> threading.Lock
        self.process_monitor = ProcessMonitor()
        self.request_resources = {}  # request_id -> list of resource_ids
        self.lock = threading.Lock()

    def allocate_resources(self, request_id: str, resource_type: ResourceType, 
                         amount: float = 1.0, resource_specifics: Dict[str, Any] = None) -> Optional[str]:
        """Allocate resources for a request"""
        with self.lock:
            # Check if resource allocation would exceed constraints
            if not self._would_exceed_constraints(resource_type, amount):
                resource_id = f"{request_id}_{resource_type.value}_{int(time.time())}"
                
                self.active_resources[resource_id] = {
                    "type": resource_type,
                    "amount": amount,
                    "allocated_at": time.time(),
                    "request_id": request_id,
                    "specifics": resource_specifics or {}
                }
                
                if request_id not in self.request_resources:
                    self.request_resources[request_id] = []
                self.request_resources[request_id].append(resource_id)
                
                return resource_id
            else:
                return None

    def _would_exceed_constraints(self, resource_type: ResourceType, amount: float) -> bool:
        """Check if allocating resources would exceed constraints"""
        if resource_type == ResourceType.CPU:
            current_cpu = self.process_monitor.get_cpu_percent()
            return current_cpu + amount > self.constraints.max_cpu_percent
        elif resource_type == ResourceType.MEMORY:
            current_memory = self.process_monitor.get_memory_usage_mb()
            return current_memory + amount > self.constraints.max_memory_mb
        elif resource_type == ResourceType.THREAD:
            # For simplicity, just count active threads
            active_threads = threading.active_count()
            return active_threads > self.constraints.max_concurrent_requests
        else:
            # For other resources, just track them
            return False

    def release_resources(self, request_id: str):
        """Release all resources allocated to a request"""
        with self.lock:
            if request_id in self.request_resources:
                for resource_id in self.request_resources[request_id]:
                    if resource_id in self.active_resources:
                        del self.active_resources[resource_id]
                del self.request_resources[request_id]

    def check_resource_availability(self, resource_type: ResourceType, required_amount: float) -> bool:
        """Check if required resources are available"""
        return not self._would_exceed_constraints(resource_type, required_amount)

    def enforce_timeout(self, request_id: str, start_time: float) -> bool:
        """Check if request has exceeded timeout"""
        elapsed_ms = (time.time() - start_time) * 1000
        return elapsed_ms > self.constraints.timeout_ms

    def get_resource_usage(self, request_id: str) -> Dict[str, Any]:
        """Get resource usage for a request"""
        usage = {
            "request_id": request_id,
            "resources_allocated": 0,
            "total_memory_used_mb": 0,
            "cpu_percent": 0,
            "elapsed_time_ms": 0
        }
        
        if request_id in self.request_resources:
            usage["resources_allocated"] = len(self.request_resources[request_id])
            
            # Calculate memory usage for this request
            for resource_id in self.request_resources[request_id]:
                if resource_id in self.active_resources:
                    resource = self.active_resources[resource_id]
                    if resource["type"] == ResourceType.MEMORY:
                        usage["total_memory_used_mb"] += resource["amount"]
        
        usage["cpu_percent"] = self.process_monitor.get_cpu_percent()
        usage["elapsed_time_ms"] = (time.time() - start_time) * 1000 if 'start_time' in locals() else 0
        
        return usage

    def cleanup_expired_resources(self):
        """Clean up resources that have exceeded their allocation time"""
        with self.lock:
            current_time = time.time()
            expired_resources = []
            
            for resource_id, resource_info in self.active_resources.items():
                # For this simple implementation, assume resources expire after 1 hour
                if current_time - resource_info["allocated_at"] > 3600:
                    expired_resources.append(resource_id)
            
            for resource_id in expired_resources:
                del self.active_resources[resource_id]
                
                # Remove from request_resources mapping
                for req_id, resource_list in self.request_resources.items():
                    if resource_id in resource_list:
                        resource_list.remove(resource_id)
                        if not resource_list:
                            del self.request_resources[req_id]


class ProcessMonitor:
    """Monitor system resources"""
    
    def __init__(self):
        self.process = psutil.Process(os.getpid())

    def get_cpu_percent(self) -> float:
        """Get current CPU percent usage"""
        try:
            return self.process.cpu_percent()
        except:
            return 0.0

    def get_memory_usage_mb(self) -> float:
        """Get current memory usage in MB"""
        try:
            memory_bytes = self.process.memory_info().rss
            return memory_bytes / (1024 * 1024)  # Convert to MB
        except:
            return 0.0

    def get_total_memory_mb(self) -> float:
        """Get total system memory in MB"""
        try:
            return psutil.virtual_memory().total / (1024 * 1024)
        except:
            return 0.0

    def get_available_memory_mb(self) -> float:
        """Get available system memory in MB"""
        try:
            return psutil.virtual_memory().available / (1024 * 1024)
        except:
            return 0.0

    def get_active_thread_count(self) -> int:
        """Get active thread count"""
        return threading.active_count()


class ResourceEnforcementException(Exception):
    """Exception raised when resource constraints are violated"""
    def __init__(self, resource_type: ResourceType, message: str):
        self.resource_type = resource_type
        self.message = message
        super().__init__(f"Resource constraint violation ({resource_type.value}): {message}")


def with_resource_enforcement(constraints: ResourceConstraints = None):
    """Decorator to enforce resource constraints on functions"""
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            rm = ResourceManager(constraints)
            start_time = time.time()
            
            # Check timeout before execution
            if rm.enforce_timeout("temp", start_time):
                raise ResourceEnforcementException(ResourceType.CPU, "Timeout before execution")
            
            # Allocate memory resource
            mem_resource = rm.allocate_resources("temp", ResourceType.MEMORY, 10.0)  # 10MB
            if not mem_resource:
                raise ResourceEnforcementException(ResourceType.MEMORY, "Insufficient memory")
            
            try:
                result = func(*args, **kwargs)
                
                # Check if execution exceeded constraints
                if rm.enforce_timeout("temp", start_time):
                    raise ResourceEnforcementException(ResourceType.CPU, "Execution timeout")
                
                return result
            finally:
                rm.release_resources("temp")
        
        return wrapper
    return decorator