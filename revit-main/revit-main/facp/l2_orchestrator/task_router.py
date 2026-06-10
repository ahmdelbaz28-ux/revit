"""
FACP Task Router - Routes tasks to appropriate destinations
"""
from typing import Dict, Any, List, Optional
import re


class TaskRouter:
    """
    Routes tasks based on method names and other criteria
    """
    def __init__(self):
        # Methods that should be routed directly to L3 engine
        self.engine_methods = {
            "engine.calculate",
            "engine.validate", 
            "engine.transform",
            "engine.analyze",
            "engine.compute",
            "calc.run",
            "analysis.perform",
            "validation.check"
        }
        
        # Patterns for engine methods (using regex)
        self.engine_patterns = [
            r'^engine\..*',      # All engine.* methods
            r'^calc\..*',        # All calc.* methods  
            r'^analysis\..*',    # All analysis.* methods
            r'^validation\..*',  # All validation.* methods
            r'^compute\..*'      # All compute.* methods
        ]
        
        # Methods that should be handled by agents
        self.agent_methods = {
            "agent.plan",
            "orchestrator.route", 
            "task.schedule",
            "workflow.execute",
            "plan.create",
            "schedule.optimize"
        }
        
        # Patterns for agent methods
        self.agent_patterns = [
            r'^agent\..*',
            r'^orchestrator\..*',
            r'^task\..*',
            r'^workflow\..*',
            r'^plan\..*',
            r'^schedule\..*'
        ]

    def should_route_to_engine(self, method: str) -> bool:
        """
        Determine if a method should be routed to L3 engine
        """
        # Check exact matches first
        if method in self.engine_methods:
            return True
            
        # Check patterns
        for pattern in self.engine_patterns:
            if re.match(pattern, method):
                return True
                
        # If it's an agent method, don't route to engine
        if method in self.agent_methods:
            return False
            
        for pattern in self.agent_patterns:
            if re.match(pattern, method):
                return False
        
        # Default: if it looks like an engine operation, route to engine
        # This covers methods like "calculate_pressure", "validate_design", etc.
        engine_indicators = [
            "calculate", "compute", "analyze", "validate", "transform", 
            "evaluate", "assess", "determine", "find", "solve", "engine"
        ]
        
        method_lower = method.lower()
        for indicator in engine_indicators:
            if indicator in method_lower:
                return True
        
        # Default to engine for unknown methods (conservative approach)
        return True

    def should_route_to_agent(self, method: str) -> bool:
        """
        Determine if a method should be routed to an agent
        """
        return not self.should_route_to_engine(method)

    def get_destination(self, method: str) -> str:
        """
        Get the destination for a method
        """
        if self.should_route_to_engine(method):
            return "L3_ENGINE"
        else:
            return "AGENT"

    def add_engine_method(self, method: str):
        """Add a method to the engine routing list"""
        self.engine_methods.add(method)

    def add_agent_method(self, method: str):
        """Add a method to the agent routing list"""
        self.agent_methods.add(method)

    def remove_engine_method(self, method: str):
        """Remove a method from the engine routing list"""
        self.engine_methods.discard(method)

    def remove_agent_method(self, method: str):
        """Remove a method from the agent routing list"""
        self.agent_methods.discard(method)

    def add_engine_pattern(self, pattern: str):
        """Add a regex pattern for engine methods"""
        if pattern not in self.engine_patterns:
            self.engine_patterns.append(pattern)

    def add_agent_pattern(self, pattern: str):
        """Add a regex pattern for agent methods"""
        if pattern not in self.agent_patterns:
            self.agent_patterns.append(pattern)

    def get_routing_info(self, method: str) -> Dict[str, Any]:
        """
        Get detailed routing information for a method
        """
        is_engine = self.should_route_to_engine(method)
        destination = "L3_ENGINE" if is_engine else "AGENT"
        
        # Find which rules matched
        matching_engine_rules = []
        for rule in self.engine_methods:
            if method == rule:
                matching_engine_rules.append(f"exact_match: {rule}")
                
        for i, pattern in enumerate(self.engine_patterns):
            if re.match(pattern, method):
                matching_engine_rules.append(f"pattern_{i}: {pattern}")
        
        matching_agent_rules = []
        for rule in self.agent_methods:
            if method == rule:
                matching_agent_rules.append(f"exact_match: {rule}")
                
        for i, pattern in enumerate(self.agent_patterns):
            if re.match(pattern, method):
                matching_agent_rules.append(f"pattern_{i}: {pattern}")
        
        # Check indicators
        engine_indicators_found = []
        method_lower = method.lower()
        for indicator in ["calculate", "compute", "analyze", "validate", "transform", 
                         "evaluate", "assess", "determine", "find", "solve", "engine"]:
            if indicator in method_lower:
                engine_indicators_found.append(indicator)
        
        return {
            "method": method,
            "destination": destination,
            "is_engine_bound": is_engine,
            "matching_engine_rules": matching_engine_rules,
            "matching_agent_rules": matching_agent_rules,
            "engine_indicators": engine_indicators_found,
            "default_ruling": "engine" if is_engine else "agent"
        }

    def get_status(self) -> Dict[str, Any]:
        """Get router status information"""
        return {
            "engine_methods_count": len(self.engine_methods),
            "agent_methods_count": len(self.agent_methods),
            "engine_patterns_count": len(self.engine_patterns),
            "agent_patterns_count": len(self.agent_patterns),
            "total_routes": len(self.engine_methods) + len(self.agent_methods)
        }

    def get_all_engine_methods(self) -> List[str]:
        """Get all methods routed to engine"""
        return list(self.engine_methods)

    def get_all_agent_methods(self) -> List[str]:
        """Get all methods routed to agents"""
        return list(self.agent_methods)


class AdvancedTaskRouter(TaskRouter):
    """
    Advanced task router with additional routing capabilities
    """
    def __init__(self):
        super().__init__()
        # Context-aware routing rules
        self.context_routes = {}
        # Priority-based routing
        self.priority_routes = {}
        # Fallback routes
        self.fallback_routes = ["L3_ENGINE"]  # Default fallback is engine

    def route_with_context(self, method: str, context: Dict[str, Any]) -> str:
        """
        Route a method considering additional context
        """
        # Check context-specific routes first
        if method in self.context_routes:
            # Apply context-specific routing logic
            context_rules = self.context_routes[method]
            for condition, destination in context_rules.items():
                if self._evaluate_condition(context, condition):
                    return destination
        
        # Use regular routing
        return self.get_destination(method)

    def _evaluate_condition(self, context: Dict[str, Any], condition: str) -> bool:
        """
        Evaluate a context condition
        Example conditions: "user_role=admin", "data_size>1000", etc.
        """
        # Simple implementation - in reality this would be more sophisticated
        if "=" in condition:
            key, value = condition.split("=", 1)
            return str(context.get(key)) == value
        elif ">" in condition:
            key, value = condition.split(">", 1)
            try:
                return float(context.get(key, 0)) > float(value)
            except ValueError:
                return False
        elif "<" in condition:
            key, value = condition.split("<", 1)
            try:
                return float(context.get(key, 0)) < float(value)
            except ValueError:
                return False
        else:
            # Assume it's a boolean check
            return bool(context.get(condition, False))

    def add_context_route(self, method: str, condition: str, destination: str):
        """
        Add a context-aware route
        """
        if method not in self.context_routes:
            self.context_routes[method] = {}
        self.context_routes[method][condition] = destination

    def add_priority_route(self, method: str, priority: int, destination: str):
        """
        Add a priority-based route
        """
        if method not in self.priority_routes:
            self.priority_routes[method] = []
        self.priority_routes[method].append((priority, destination))
        # Sort by priority (higher numbers first)
        self.priority_routes[method].sort(key=lambda x: x[0], reverse=True)

    def route_with_priority(self, method: str) -> str:
        """
        Route using priority rules
        """
        if method in self.priority_routes:
            # Return the highest priority destination
            if self.priority_routes[method]:
                return self.priority_routes[method][0][1]
        
        # Fall back to regular routing
        return self.get_destination(method)

    def set_fallback_routes(self, routes: List[str]):
        """
        Set fallback routes (order matters - first available is used)
        """
        self.fallback_routes = routes

    def get_comprehensive_routing_info(self, method: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get comprehensive routing information considering context and priorities
        """
        basic_info = self.get_routing_info(method)
        
        # Add context-aware routing info
        context_result = None
        if context:
            context_result = self.route_with_context(method, context)
        
        # Add priority routing info
        priority_result = self.route_with_priority(method)
        
        return {
            **basic_info,
            "context_route_result": context_result,
            "priority_route_result": priority_result,
            "has_context_routes": method in self.context_routes,
            "has_priority_routes": method in self.priority_routes,
            "fallback_routes": self.fallback_routes
        }


class RouteOptimizer:
    """
    Optimizes routing decisions based on historical data
    """
    def __init__(self):
        self.route_performance = {}  # method -> {success_rate, avg_time, etc.}
        self.route_history = []  # List of routing decisions

    def record_route_outcome(self, method: str, destination: str, success: bool, execution_time: float):
        """
        Record the outcome of a routing decision
        """
        key = f"{method}:{destination}"
        if key not in self.route_performance:
            self.route_performance[key] = {
                "attempts": 0,
                "successes": 0,
                "total_time": 0.0,
                "avg_time": 0.0
            }
        
        perf = self.route_performance[key]
        perf["attempts"] += 1
        if success:
            perf["successes"] += 1
        perf["total_time"] += execution_time
        perf["avg_time"] = perf["total_time"] / perf["attempts"]
        
        # Record in history
        self.route_history.append({
            "method": method,
            "destination": destination,
            "success": success,
            "time": execution_time,
            "timestamp": __import__('time').time()
        })
        
        # Keep history size manageable
        if len(self.route_history) > 1000:  # Keep last 1000 entries
            self.route_history = self.route_history[-1000:]

    def get_optimized_destination(self, method: str) -> Optional[str]:
        """
        Get the statistically optimal destination for a method
        """
        # Find all destinations used for this method
        candidates = {}
        for key, perf in self.route_performance.items():
            if key.startswith(f"{method}:"):
                dest = key.split(":", 1)[1]
                candidates[dest] = perf
        
        if not candidates:
            return None
        
        # Choose destination with highest success rate, then lowest avg time
        best_dest = max(candidates.keys(), 
                       key=lambda d: (candidates[d]["successes"]/candidates[d]["attempts"], 
                                    -candidates[d]["avg_time"]))
        
        return best_dest

    def get_performance_report(self) -> Dict[str, Any]:
        """
        Get performance report for all routes
        """
        report = {}
        for key, perf in self.route_performance.items():
            if perf["attempts"] > 0:
                success_rate = perf["successes"] / perf["attempts"]
                report[key] = {
                    "success_rate": success_rate,
                    "attempts": perf["attempts"],
                    "successes": perf["successes"],
                    "average_time_ms": perf["avg_time"] * 1000,
                    "efficiency_score": success_rate / max(perf["avg_time"], 0.001)  # Avoid division by zero
                }
        
        return report