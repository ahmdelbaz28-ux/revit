"""
Execution Isolation System for Distributed FACP System
"""
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from enum import Enum
from typing import Any, Callable, Dict


class ExecutionEnvironment(Enum):
    """Types of execution environments"""
    SANDBOXED_SUBPROCESS = "sandboxed_subprocess"
    CONTAINERIZED = "containerized"  # Conceptual for now
    THREAD_ISOLATED = "thread_isolated"
    VM_ISOLATED = "vm_isolated"     # Conceptual for now


class ExecutionIsolationManager:
    """
    Manages execution isolation for distributed system
    Ensures L3 engine nodes remain stateless and isolated
    """
    def __init__(self):
        self.active_processes = {}  # pid -> process_info
        self.active_containers = {}  # container_id -> container_info
        self.resource_limits = {}  # pid -> limits
        self.execution_logs = []  # Execution audit trail
        self.lock = threading.Lock()
        self.sandbox_base_path = tempfile.mkdtemp(prefix="facp_sandbox_")

    def create_sandboxed_execution(self, func: Callable, args: tuple = (), kwargs: dict = None,
                                   timeout: int = 8000, max_memory_mb: int = 512) -> Dict[str, Any]:
        """
        Create a sandboxed execution environment for a function
        """
        kwargs = kwargs or {}

        # Create temporary directory for this execution
        exec_dir = tempfile.mkdtemp(dir=self.sandbox_base_path)

        # Write function and arguments to a temporary file
        # This is a simplified approach - in a real system, we'd use proper sandboxing
        import marshal
        import pickle

        # Serialize function and arguments
        func_code = marshal.dumps(func.__code__)
        with open(os.path.join(exec_dir, "func.pkl"), "wb") as f:
            pickle.dump((func_code, args, kwargs), f)

        # Create execution script
        exec_script = f"""
import sys
import os
import pickle
import marshal
import types
import resource

# Set resource limits
try:
    # Limit virtual memory (in bytes)
    resource.setrlimit(resource.RLIMIT_AS, ({max_memory_mb * 1024 * 1024}, {max_memory_mb * 1024 * 1024}))
except:
    # On Windows or systems without resource module, skip this
    pass

# Change to execution directory
os.chdir(r"{exec_dir}")

# Load function and arguments
with open("func.pkl", "rb") as f:
    func_code, args, kwargs = pickle.load(f)

# Recreate function
func = types.FunctionType(marshal.loads(func_code), globals())

# Execute function
try:
    result = func(*args, **kwargs)
    # Write result to output file
    with open("result.pkl", "wb") as f:
        pickle.dump(("success", result), f)
except Exception as e:
    # Write exception to output file
    with open("result.pkl", "wb") as f:
        pickle.dump(("error", str(e)), f)
"""

        script_path = os.path.join(exec_dir, "exec_script.py")
        with open(script_path, "w") as f:
            f.write(exec_script)

        # Execute in subprocess with timeout
        start_time = time.time()
        try:
            proc = subprocess.run(
                [sys.executable, script_path],
                timeout=timeout/1000,  # Convert ms to seconds
                capture_output=True,
                cwd=exec_dir,
                check=False
            )

            execution_time = (time.time() - start_time) * 1000  # Convert to ms

            # Read result
            result_path = os.path.join(exec_dir, "result.pkl")
            if os.path.exists(result_path):
                with open(result_path, "rb") as f:
                    status, result = pickle.load(f)
            else:
                status = "error"
                result = f"No result file found. Process exited with code {proc.returncode}"

            # Cleanup
            shutil.rmtree(exec_dir)

            # Log execution
            with self.lock:
                self.execution_logs.append({
                    "timestamp": time.time(),
                    "execution_time_ms": execution_time,
                    "status": status,
                    "timeout": timeout,
                    "max_memory_mb": max_memory_mb,
                    "sandbox_path": exec_dir
                })

            return {
                "status": status,
                "result": result,
                "execution_time_ms": execution_time,
                "sandbox_path": exec_dir
            }

        except subprocess.TimeoutExpired:
            # Terminate the process if it timed out
            # In a real implementation, we'd need to kill the process tree
            execution_time = (time.time() - start_time) * 1000

            # Cleanup
            shutil.rmtree(exec_dir)

            return {
                "status": "error",
                "result": f"Execution timed out after {timeout}ms",
                "execution_time_ms": execution_time,
                "sandbox_path": exec_dir
            }
        except Exception as e:
            # Cleanup
            shutil.rmtree(exec_dir)

            return {
                "status": "error",
                "result": f"Execution failed: {str(e)}",
                "execution_time_ms": (time.time() - start_time) * 1000,
                "sandbox_path": exec_dir
            }

    def enforce_resource_limits(self, pid: int, timeout_ms: int, max_memory_mb: int):
        """
        Enforce resource limits on a process
        """
        self.resource_limits[pid] = {
            "timeout_ms": timeout_ms,
            "max_memory_mb": max_memory_mb,
            "applied_at": time.time()
        }

    def check_resource_compliance(self, pid: int) -> bool:
        """
        Check if a process is within resource limits
        """
        if pid not in self.resource_limits:
            return True  # No limits set

        limits = self.resource_limits[pid]

        # Check timeout (this is a simplified check - real implementation would monitor continuously)
        elapsed = (time.time() - limits["applied_at"]) * 1000
        if elapsed > limits["timeout_ms"]:
            return False

        # Memory check would require platform-specific code
        # For now, return True
        return True

    def terminate_process(self, pid: int, force: bool = False):
        """
        Safely terminate a process
        """
        try:
            if force:
                os.kill(pid, signal.SIGKILL)
            else:
                os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass  # Process already terminated
        except PermissionError:
            pass  # Insufficient permissions

    def cleanup_sandboxed_executions(self):
        """
        Clean up any remaining sandboxed executions
        """
        # In a real implementation, this would monitor and clean up processes
        # For now, just clean up the base path
        try:
            shutil.rmtree(self.sandbox_base_path)
            self.sandbox_base_path = tempfile.mkdtemp(prefix="facp_sandbox_")
        except:
            pass

    def get_execution_stats(self) -> Dict[str, Any]:
        """
        Get statistics about sandboxed executions
        """
        return {
            "total_executions": len(self.execution_logs),
            "successful_executions": len([log for log in self.execution_logs if log["status"] == "success"]),
            "failed_executions": len([log for log in self.execution_logs if log["status"] == "error"]),
            "average_execution_time": (
                sum(log["execution_time_ms"] for log in self.execution_logs) / len(self.execution_logs)
                if self.execution_logs else 0
            ),
            "sandbox_base_path": self.sandbox_base_path
        }


class SandboxController:
    """
    Controller for managing sandboxes across distributed nodes
    """
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.isolation_manager = ExecutionIsolationManager()
        self.active_sandboxes = {}  # sandbox_id -> sandbox_info
        self.sandbox_templates = {}  # template_name -> config
        self.lock = threading.Lock()

    def create_sandbox_template(self, name: str, config: Dict[str, Any]):
        """
        Create a template for sandboxes with specific configurations
        """
        self.sandbox_templates[name] = {
            "timeout_ms": config.get("timeout_ms", 8000),
            "max_memory_mb": config.get("max_memory_mb", 512),
            "network_access": config.get("network_access", False),
            "file_access": config.get("file_access", []),  # Restricted file paths
            "created_at": time.time()
        }

    def provision_sandbox(self, template_name: str, task_id: str = None) -> str:
        """
        Provision a new sandbox based on a template
        """
        if template_name not in self.sandbox_templates:
            raise ValueError(f"Sandbox template '{template_name}' not found")

        template = self.sandbox_templates[template_name]

        # Create sandbox directory
        sandbox_id = f"sandbox_{self.node_id}_{int(time.time())}_{len(self.active_sandboxes)}"
        sandbox_path = os.path.join(self.isolation_manager.sandbox_base_path, sandbox_id)
        os.makedirs(sandbox_path, exist_ok=True)

        # Configure sandbox
        sandbox_info = {
            "id": sandbox_id,
            "template": template_name,
            "config": template,
            "provisioned_at": time.time(),
            "task_id": task_id,
            "node_id": self.node_id,
            "sandbox_path": sandbox_path,
            "status": "ready"
        }

        with self.lock:
            self.active_sandboxes[sandbox_id] = sandbox_info

        return sandbox_id

    def execute_in_sandbox(self, sandbox_id: str, func: Callable, args: tuple = (),
                          kwargs: dict = None, custom_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute a function in a specific sandbox
        """
        if sandbox_id not in self.active_sandboxes:
            raise ValueError(f"Sandbox '{sandbox_id}' not found")

        sandbox_info = self.active_sandboxes[sandbox_id]

        # Merge custom config with template config
        config = sandbox_info["config"].copy()
        if custom_config:
            config.update(custom_config)

        # Execute in isolated environment
        result = self.isolation_manager.create_sandboxed_execution(
            func, args, kwargs,
            timeout=config["timeout_ms"],
            max_memory_mb=config["max_memory_mb"]
        )

        # Update sandbox status
        sandbox_info["last_execution"] = time.time()
        sandbox_info["last_result"] = result["status"]

        return result

    def destroy_sandbox(self, sandbox_id: str):
        """
        Destroy a sandbox and clean up resources
        """
        if sandbox_id not in self.active_sandboxes:
            return

        sandbox_info = self.active_sandboxes[sandbox_id]

        # Clean up sandbox directory
        try:
            shutil.rmtree(sandbox_info["sandbox_path"])
        except:
            pass  # Directory might already be cleaned up

        # Remove from active sandboxes
        with self.lock:
            del self.active_sandboxes[sandbox_id]

    def enforce_execution_constraints(self, request_data: Dict[str, Any]) -> tuple[bool, str]:
        """
        Enforce execution constraints based on request data
        """
        constraints = request_data.get("constraints", {})

        # Check timeout constraint
        timeout_ms = constraints.get("timeout_ms", 8000)
        if timeout_ms <= 0 or timeout_ms > 30000:  # Max 30 seconds for distributed
            return False, f"Invalid timeout constraint: {timeout_ms}ms (must be 1-30000ms)"

        # Check memory constraint
        max_memory_mb = constraints.get("max_memory_mb", 512)
        if max_memory_mb <= 0 or max_memory_mb > 1024:  # Max 1GB for distributed
            return False, f"Invalid memory constraint: {max_memory_mb}MB (must be 1-1024MB)"

        # Check recursion depth constraint
        max_depth = constraints.get("max_recursion_depth", 5)
        if max_depth <= 0 or max_depth > 10:
            return False, f"Invalid recursion depth constraint: {max_depth} (must be 1-10)"

        return True, "Constraints are valid"

    def validate_no_external_access(self, code: str) -> tuple[bool, list[str]]:
        """
        Validate that code doesn't attempt external access
        """
        forbidden_patterns = [
            "import requests",
            "import urllib",
            "import http",
            "import socket",
            "os.system",
            "subprocess.",
            "eval(",
            "exec(",
            "__import__",
        ]

        violations = []
        for pattern in forbidden_patterns:
            if pattern in code:
                violations.append(f"Potentially dangerous pattern found: {pattern}")

        return len(violations) == 0, violations

    def get_sandbox_health(self) -> Dict[str, Any]:
        """
        Get health status of all sandboxes
        """
        healthy_count = 0
        total_count = len(self.active_sandboxes)

        for _sandbox_id, info in self.active_sandboxes.items():
            # Check if sandbox directory still exists
            if os.path.exists(info["sandbox_path"]):
                healthy_count += 1

        return {
            "node_id": self.node_id,
            "total_sandboxes": total_count,
            "healthy_sandboxes": healthy_count,
            "unhealthy_sandboxes": total_count - healthy_count,
            "isolation_manager_stats": self.isolation_manager.get_execution_stats()
        }

    def cleanup_unused_sandboxes(self, max_age_minutes: int = 60):
        """
        Clean up sandboxes that haven't been used recently
        """
        current_time = time.time()
        cutoff_time = current_time - (max_age_minutes * 60)

        unused_sandboxes = []
        for sandbox_id, info in self.active_sandboxes.items():
            last_activity = info.get("last_execution", info["provisioned_at"])
            if last_activity < cutoff_time:
                unused_sandboxes.append(sandbox_id)

        for sandbox_id in unused_sandboxes:
            self.destroy_sandbox(sandbox_id)


def create_deterministic_execution_wrapper(func: Callable) -> Callable:
    """
    Create a wrapper that ensures deterministic execution
    """
    def wrapper(*args, **kwargs):
        # Set a fixed random seed based on input to ensure deterministic behavior
        import hashlib
        import random

        # Create deterministic seed from inputs
        input_str = f"{repr(args)}{repr(kwargs)}{func.__name__}"
        seed = int(hashlib.sha256(input_str.encode()).hexdigest(), 16) % (2**32)
        random.seed(seed)

        # Execute function
        return func(*args, **kwargs)

    # Preserve function metadata
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__

    return wrapper


class StatelessExecutionValidator:
    """
    Validator to ensure L3 engine nodes remain stateless
    """
    def __init__(self):
        self.stateful_patterns = [
            "global ",
            "nonlocal ",
            "__setattr__",
            "__getattr__",
            "setattr(",
            "getattr(",
            "globals()",
            "locals()",
            "vars(",
            "__dict__",
        ]

    def validate_stateless_code(self, code: str) -> tuple[bool, list[str]]:
        """
        Validate that code doesn't maintain state
        """
        violations = []
        for pattern in self.stateful_patterns:
            if pattern in code:
                violations.append(f"Potential stateful pattern: {pattern}")

        return len(violations) == 0, violations

    def validate_deterministic_function(self, func: Callable) -> tuple[bool, str]:
        """
        Validate that a function is deterministic
        """
        # Test the function with the same inputs multiple times
        # This is a basic check - more sophisticated validation would be needed for production

        import inspect

        # Check if function has side effects by examining source code
        try:
            source = inspect.getsource(func)

            # Look for potential side effects
            side_effect_indicators = [
                "print(",
                "input(",
                "open(",
                "file(",
                "sys.",
                "os.",
                "time.sleep",
                "random.",
                "datetime.",
            ]

            for indicator in side_effect_indicators:
                if indicator in source:
                    return False, f"Potential side effect found: {indicator}"

            return True, "Function appears deterministic"
        except:
            # If we can't inspect the source, assume it's potentially stateful
            return False, "Cannot validate function - source inspection failed"
