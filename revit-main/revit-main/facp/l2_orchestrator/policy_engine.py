"""
FACP Policy Engine - Enforces policies for requests
"""
from typing import Dict, Any, List, Callable
from datetime import datetime, timedelta
import time
import threading


class Policy:
    """
    Base class for policies
    """
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.enabled = True
    
    def evaluate(self, request_data: Dict[str, Any], auth_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate the policy against request and auth context
        Returns: {"allowed": bool, "reason": str, "metadata": dict}
        """
        raise NotImplementedError("Subclasses must implement evaluate method")


class RateLimitPolicy(Policy):
    """
    Rate limiting policy
    """
    def __init__(self, name: str, max_requests: int, window_seconds: int):
        super().__init__(name, f"Limits requests to {max_requests} per {window_seconds} seconds")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.request_counts = {}  # user_id -> [(timestamp, count)]
        self.lock = threading.Lock()
    
    def evaluate(self, request_data: Dict[str, Any], auth_context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled:
            return {"allowed": True, "reason": "Policy disabled"}
        
        user_id = auth_context.get("user_id", "anonymous")
        current_time = time.time()
        
        with self.lock:
            # Clean up old entries
            if user_id in self.request_counts:
                self.request_counts[user_id] = [
                    (ts, count) for ts, count in self.request_counts[user_id]
                    if current_time - ts <= self.window_seconds
                ]
            
            # Count current requests in window
            current_requests = sum(count for ts, count in self.request_counts.get(user_id, []))
            
            if current_requests >= self.max_requests:
                return {
                    "allowed": False,
                    "reason": f"Rate limit exceeded: {self.max_requests} requests per {self.window_seconds}s",
                    "metadata": {
                        "current_requests": current_requests,
                        "limit": self.max_requests,
                        "window_seconds": self.window_seconds
                    }
                }
            
            # Add current request
            if user_id not in self.request_counts:
                self.request_counts[user_id] = []
            self.request_counts[user_id].append((current_time, 1))
        
        return {"allowed": True, "reason": "Rate limit check passed"}


class RoleBasedAccessPolicy(Policy):
    """
    Role-based access control policy
    """
    def __init__(self, name: str, required_roles: List[str], required_permissions: List[str] = None):
        super().__init__(name, f"Requires roles: {required_roles}, permissions: {required_permissions or []}")
        self.required_roles = required_roles
        self.required_permissions = required_permissions or []
    
    def evaluate(self, request_data: Dict[str, Any], auth_context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled:
            return {"allowed": True, "reason": "Policy disabled"}
        
        user_roles = auth_context.get("roles", [])
        user_permissions = auth_context.get("permissions", [])
        
        # Check roles
        has_required_role = any(role in user_roles for role in self.required_roles)
        if not has_required_role:
            return {
                "allowed": False,
                "reason": f"Missing required roles: {self.required_roles}",
                "metadata": {
                    "user_roles": user_roles,
                    "required_roles": self.required_roles
                }
            }
        
        # Check permissions
        if self.required_permissions:
            has_required_permissions = all(perm in user_permissions for perm in self.required_permissions)
            if not has_required_permissions:
                return {
                    "allowed": False,
                    "reason": f"Missing required permissions: {self.required_permissions}",
                    "metadata": {
                        "user_permissions": user_permissions,
                        "required_permissions": self.required_permissions
                    }
                }
        
        return {"allowed": True, "reason": "Role and permission check passed"}


class TimeBasedAccessPolicy(Policy):
    """
    Time-based access policy
    """
    def __init__(self, name: str, allowed_start_hour: int, allowed_end_hour: int, timezone: str = "UTC"):
        super().__init__(name, f"Allows access between {allowed_start_hour}:00 and {allowed_end_hour}:00 ({timezone})")
        self.allowed_start_hour = allowed_start_hour
        self.allowed_end_hour = allowed_end_hour
        self.timezone = timezone
    
    def evaluate(self, request_data: Dict[str, Any], auth_context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled:
            return {"allowed": True, "reason": "Policy disabled"}
        
        current_hour = datetime.now().hour
        
        if self.allowed_start_hour <= self.allowed_end_hour:
            # Same day range (e.g., 9AM to 5PM)
            in_range = self.allowed_start_hour <= current_hour < self.allowed_end_hour
        else:
            # Cross-day range (e.g., 8PM to 6AM)
            in_range = current_hour >= self.allowed_start_hour or current_hour < self.allowed_end_hour
        
        if not in_range:
            return {
                "allowed": False,
                "reason": f"Outside allowed hours: {self.allowed_start_hour}:00 to {self.allowed_end_hour}:00",
                "metadata": {
                    "current_hour": current_hour,
                    "allowed_start_hour": self.allowed_start_hour,
                    "allowed_end_hour": self.allowed_end_hour
                }
            }
        
        return {"allowed": True, "reason": "Time-based access check passed"}


class DataSizeLimitPolicy(Policy):
    """
    Policy to limit request/response size
    """
    def __init__(self, name: str, max_size_bytes: int):
        super().__init__(name, f"Limits data size to {max_size_bytes} bytes")
        self.max_size_bytes = max_size_bytes
    
    def evaluate(self, request_data: Dict[str, Any], auth_context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled:
            return {"allowed": True, "reason": "Policy disabled"}
        
        import json
        data_size = len(json.dumps(request_data).encode('utf-8'))
        
        if data_size > self.max_size_bytes:
            return {
                "allowed": False,
                "reason": f"Request size {data_size} bytes exceeds limit of {self.max_size_bytes}",
                "metadata": {
                    "current_size": data_size,
                    "limit": self.max_size_bytes
                }
            }
        
        return {"allowed": True, "reason": "Data size check passed"}


class BlacklistPolicy(Policy):
    """
    Policy to blacklist certain users, IPs, or methods
    """
    def __init__(self, name: str, blacklisted_users: List[str] = None, 
                 blacklisted_ips: List[str] = None, blacklisted_methods: List[str] = None):
        super().__init__(name, "Blocks blacklisted users, IPs, or methods")
        self.blacklisted_users = blacklisted_users or []
        self.blacklisted_ips = blacklisted_ips or []
        self.blacklisted_methods = blacklisted_methods or []
    
    def evaluate(self, request_data: Dict[str, Any], auth_context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled:
            return {"allowed": True, "reason": "Policy disabled"}
        
        # Check user
        user_id = auth_context.get("user_id", "")
        if user_id in self.blacklisted_users:
            return {
                "allowed": False,
                "reason": f"User {user_id} is blacklisted",
                "metadata": {"user_id": user_id}
            }
        
        # Check source IP (passed in auth context or request params)
        source_ip = auth_context.get("source_ip", request_data.get("_source_ip", ""))
        if source_ip in self.blacklisted_ips:
            return {
                "allowed": False,
                "reason": f"IP {source_ip} is blacklisted",
                "metadata": {"source_ip": source_ip}
            }
        
        # Check method
        method = request_data.get("method", "")
        if method in self.blacklisted_methods:
            return {
                "allowed": False,
                "reason": f"Method {method} is blacklisted",
                "metadata": {"method": method}
            }
        
        return {"allowed": True, "reason": "Blacklist check passed"}


class PolicyEngine:
    """
    Main policy engine that manages and evaluates policies
    """
    def __init__(self):
        self.policies: List[Policy] = []
        self.policy_order: List[str] = []  # Order in which policies should be evaluated
        self.lock = threading.Lock()
    
    def add_policy(self, policy: Policy, execute_first: bool = False):
        """
        Add a policy to the engine
        :param policy: Policy to add
        :param execute_first: Whether to evaluate this policy first
        """
        with self.lock:
            if policy.name in [p.name for p in self.policies]:
                # Replace existing policy
                self.policies = [p for p in self.policies if p.name != policy.name]
            
            self.policies.append(policy)
            
            if execute_first:
                self.policy_order.insert(0, policy.name)
            else:
                self.policy_order.append(policy.name)
    
    def remove_policy(self, policy_name: str):
        """Remove a policy by name"""
        with self.lock:
            self.policies = [p for p in self.policies if p.name != policy_name]
            if policy_name in self.policy_order:
                self.policy_order.remove(policy_name)
    
    def apply_policies(self, request_data: Dict[str, Any], auth_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply all policies to the request
        Returns: {"allowed": bool, "reason": str, "failed_policy": str}
        """
        # Evaluate policies in order
        for policy_name in self.policy_order:
            policy = next((p for p in self.policies if p.name == policy_name), None)
            if policy:
                result = policy.evaluate(request_data, auth_context)
                
                if not result["allowed"]:
                    return {
                        "allowed": False,
                        "reason": result["reason"],
                        "failed_policy": policy.name,
                        "metadata": result.get("metadata", {})
                    }
        
        return {"allowed": True, "reason": "All policies passed", "failed_policy": None}
    
    def enable_policy(self, policy_name: str):
        """Enable a policy"""
        policy = next((p for p in self.policies if p.name == policy_name), None)
        if policy:
            policy.enabled = True
    
    def disable_policy(self, policy_name: str):
        """Disable a policy"""
        policy = next((p for p in self.policies if p.name == policy_name), None)
        if policy:
            policy.enabled = False
    
    def get_policy_status(self, policy_name: str) -> Dict[str, Any]:
        """Get status of a specific policy"""
        policy = next((p for p in self.policies if p.name == policy_name), None)
        if policy:
            return {
                "name": policy.name,
                "description": policy.description,
                "enabled": policy.enabled,
                "type": type(policy).__name__
            }
        return None
    
    def get_all_policies_status(self) -> List[Dict[str, Any]]:
        """Get status of all policies"""
        return [self.get_policy_status(p.name) for p in self.policies if self.get_policy_status(p.name)]
    
    def get_status(self) -> Dict[str, Any]:
        """Get overall policy engine status"""
        return {
            "total_policies": len(self.policies),
            "enabled_policies": len([p for p in self.policies if p.enabled]),
            "policy_order": self.policy_order,
            "policies": self.get_all_policies_status()
        }
    
    def update_policy(self, policy_name: str, **updates):
        """
        Update policy configuration (for policies that support it)
        """
        policy = next((p for p in self.policies if p.name == policy_name), None)
        if policy:
            for attr, value in updates.items():
                if hasattr(policy, attr):
                    setattr(policy, attr, value)


class ChainedPolicy(Policy):
    """
    Policy that chains multiple policies together
    """
    def __init__(self, name: str, policies: List[Policy], chain_type: str = "and"):
        super().__init__(name, f"Chains policies with {chain_type.upper()} logic")
        self.policies = policies
        self.chain_type = chain_type  # "and" or "or"
    
    def evaluate(self, request_data: Dict[str, Any], auth_context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled:
            return {"allowed": True, "reason": "Policy disabled"}
        
        results = [policy.evaluate(request_data, auth_context) for policy in self.policies]
        
        if self.chain_type == "and":
            # All must pass
            all_passed = all(r["allowed"] for r in results)
            if all_passed:
                return {"allowed": True, "reason": "All chained policies passed"}
            else:
                failed_policy = next((p.name for p, r in zip(self.policies, results) if not r["allowed"]), "unknown")
                return {
                    "allowed": False,
                    "reason": f"Chained policy failed: {failed_policy}",
                    "metadata": {"failed_policy": failed_policy}
                }
        else:  # "or"
            # At least one must pass
            any_passed = any(r["allowed"] for r in results)
            if any_passed:
                return {"allowed": True, "reason": "At least one chained policy passed"}
            else:
                return {
                    "allowed": False,
                    "reason": "All chained policies failed",
                    "metadata": {"failed_policies": [p.name for p in self.policies]}
                }


class ConditionalPolicy(Policy):
    """
    Policy that applies only under certain conditions
    """
    def __init__(self, name: str, condition_func: Callable[[Dict[str, Any], Dict[str, Any]], bool], 
                 delegate_policy: Policy):
        super().__init__(name, "Applies policy based on condition")
        self.condition_func = condition_func
        self.delegate_policy = delegate_policy
    
    def evaluate(self, request_data: Dict[str, Any], auth_context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled:
            return {"allowed": True, "reason": "Policy disabled"}
        
        # Check if condition is met
        if self.condition_func(request_data, auth_context):
            # Apply delegate policy
            return self.delegate_policy.evaluate(request_data, auth_context)
        else:
            # Condition not met, policy doesn't apply
            return {"allowed": True, "reason": "Conditional policy not triggered"}