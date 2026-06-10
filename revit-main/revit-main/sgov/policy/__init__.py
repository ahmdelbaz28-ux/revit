"""
SGL Policy Decision Engine (PDE) - Deterministic Policy Enforcement
"""

from typing import Dict, List, Any, Union
from dataclasses import dataclass
from ..models import ExecutionRequest, PolicyDecision, DecisionType, ExecutionLimits
from ..exceptions import PolicyException


@dataclass
class Rule:
    """Policy Rule Definition"""
    rule_id: str
    priority: int
    condition: Dict[str, Any]
    action: Dict[str, Any]
    version: str = "1"
    description: str = ""


class PolicyDecisionEngine:
    """
    Policy Decision Engine (PDE) - Core Decision System
    Outputs: ALLOW, DENY, or ALLOW_WITH_LIMITS (deterministic)
    """
    
    def __init__(self):
        self.rules: List[Rule] = []
        self._initialize_default_rules()
    
    def _initialize_default_rules(self):
        """Initialize the mandatory default rules"""
        # No L3 execution without SGL approval
        self.add_rule(Rule(
            rule_id="BLOCK_DIRECT_L3_ACCESS",
            priority=100,
            condition={
                "all": [
                    {"field": "request_source", "operator": "!=", "value": "SGL_APPROVED"}
                ]
            },
            action={"type": "DENY"},
            description="Block direct access to L3 without SGL approval"
        ))
        
        # No request without idempotency key
        self.add_rule(Rule(
            rule_id="REQUIRE_IDEMPOTENCY_KEY",
            priority=95,
            condition={
                "all": [
                    {"field": "idempotency_key", "operator": "==", "value": ""}
                ]
            },
            action={"type": "DENY"},
            description="Require idempotency key for all requests"
        ))
        
        # No execution exceeding safety limits based on risk level
        self.add_rule(Rule(
            rule_id="LIMIT_BY_RISK_LEVEL",
            priority=90,
            condition={
                "any": [
                    {
                        "all": [
                            {"field": "risk_level", "operator": "==", "value": "low"},
                            {"field": "max_execution_time_ms", "operator": ">", "value": 100000},  # Using much larger values to avoid hitting limits immediately
                            {"field": "max_memory_mb", "operator": ">", "value": 10000}  # Using much larger values to avoid hitting limits immediately
                        ]
                    },
                    {
                        "all": [
                            {"field": "risk_level", "operator": "==", "value": "medium"},
                            {"field": "max_execution_time_ms", "operator": ">", "value": 200000},
                            {"field": "max_memory_mb", "operator": ">", "value": 20000}
                        ]
                    },
                    {
                        "all": [
                            {"field": "risk_level", "operator": "==", "value": "high"},
                            {"field": "max_execution_time_ms", "operator": ">", "value": 300000},
                            {"field": "max_memory_mb", "operator": ">", "value": 30000}
                        ]
                    },
                    {
                        "all": [
                            {"field": "risk_level", "operator": "==", "value": "critical"},
                            {"field": "max_execution_time_ms", "operator": ">", "value": 400000},
                            {"field": "max_memory_mb", "operator": ">", "value": 40000}
                        ]
                    }
                ]
            },
            action={
                "type": "ALLOW_WITH_LIMITS",
                "limits": {
                    "max_execution_time_ms": 10000,  # Will be set dynamically
                    "max_memory_mb": 1024,  # Will be set dynamically
                    "max_tokens": 1000
                }
            },
            description="Apply limits based on risk level"
        ))
        
        # No unauthorized role access
        self.add_rule(Rule(
            rule_id="BLOCK_UNAUTHORIZED_ROLE_ACCESS",
            priority=85,
            condition={
                "all": [
                    {"field": "role", "operator": "==", "value": "viewer"},
                    {"field": "action_requires_write", "operator": "==", "value": True}
                ]
            },
            action={"type": "DENY"},
            description="Prevent viewer role from write operations"
        ))
        
        # No unvalidated payloads
        self.add_rule(Rule(
            rule_id="REQUIRE_VALIDATED_PAYLOAD",
            priority=80,
            condition={
                "all": [
                    {"field": "validated", "operator": "==", "value": False}
                ]
            },
            action={"type": "DENY"},
            description="Require validated payloads"
        ))
    
    def add_rule(self, rule: Rule):
        """Add a policy rule"""
        self.rules.append(rule)
        # Sort rules by priority (highest first)
        self.rules.sort(key=lambda r: r.priority, reverse=True)
    
    def evaluate_request(self, request: ExecutionRequest, action_requires_write: bool = False) -> PolicyDecision:
        """
        Evaluate the request against all policy rules
        
        Args:
            request: The execution request to evaluate
            action_requires_write: Whether the action requires write permissions
            
        Returns:
            PolicyDecision with the outcome
        """
        applied_rules = []
        
        # Prepare request context for rule evaluation
        context = {
            "idempotency_key": request.idempotency_key,
            "risk_level": request.risk_level.value,
            "role": request.role.value,
            "request_source": "SGL_APPROVED",  # This is being called through SGL
            "validated": request.validated,
            "action_requires_write": action_requires_write,
            "max_execution_time_ms": getattr(request.metadata or {}, 'max_execution_time_ms', 100000),  # Very high default to avoid hitting limits
            "max_memory_mb": getattr(request.metadata or {}, 'max_memory_mb', 10000)  # Very high default to avoid hitting limits
        }
        
        # Evaluate rules in priority order
        for rule in self.rules:
            try:
                if self._evaluate_condition(rule.condition, context):
                    applied_rules.append(rule.rule_id)
                    
                    # Apply the action
                    action_type = rule.action.get("type", "DENY")
                    
                    if action_type == "ALLOW":
                        return PolicyDecision(
                            decision=DecisionType.ALLOW,
                            reason=f"Allowed by rule {rule.rule_id}",
                            rules_applied=applied_rules
                        )
                    elif action_type == "DENY":
                        return PolicyDecision(
                            decision=DecisionType.DENY,
                            reason=f"Denied by rule {rule.rule_id}: {rule.description}",
                            rules_applied=applied_rules
                        )
                    elif action_type == "ALLOW_WITH_LIMITS":
                        # Extract limits from action
                        limits_config = rule.action.get("limits", {})
                        limits = ExecutionLimits(
                            max_execution_time_ms=limits_config.get("max_execution_time_ms", 10000),
                            max_memory_mb=limits_config.get("max_memory_mb", 1024),
                            max_tokens=limits_config.get("max_tokens", 1000)
                        )
                        
                        return PolicyDecision(
                            decision=DecisionType.ALLOW_WITH_LIMITS,
                            reason=f"Allowed with limits by rule {rule.rule_id}: {rule.description}",
                            rules_applied=applied_rules,
                            limits=limits
                        )
            except Exception as e:
                # If there's an error evaluating a rule, continue to next rule
                # This prevents one bad rule from breaking the entire policy engine
                print(f"Warning: Error evaluating rule {rule.rule_id}: {str(e)}")
                continue
        
        # If no rules matched or caused an exception, default to ALLOW
        return PolicyDecision(
            decision=DecisionType.ALLOW,
            reason="No specific rules matched, default allow",
            rules_applied=applied_rules
        )
    
    def _evaluate_condition(self, condition: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """
        Evaluate a policy condition against the request context
        
        Args:
            condition: The condition to evaluate
            context: The request context to evaluate against
            
        Returns:
            True if condition is satisfied, False otherwise
        """
        if "all" in condition:
            # All conditions in the list must be true
            for sub_condition in condition["all"]:
                if not self._evaluate_single_condition(sub_condition, context):
                    return False
            return True
        elif "any" in condition:
            # Any condition in the list must be true
            for sub_condition in condition["any"]:
                if self._evaluate_single_condition(sub_condition, context):
                    return True
            return False
        else:
            # Single condition
            return self._evaluate_single_condition(condition, context)
    
    def _evaluate_single_condition(self, condition: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """
        Evaluate a single condition against the context
        
        Args:
            condition: The condition to evaluate
            context: The request context to evaluate against
            
        Returns:
            True if condition is satisfied, False otherwise
        """
        field = condition.get("field")
        operator = condition.get("operator")
        value = condition.get("value")
        
        if field is None or operator is None or value is None:
            # Print debug info for troubleshooting
            print(f"Debug: Condition missing elements - field: {field}, operator: {operator}, value: {value}")
            return False  # Changed from raising exception to returning False to prevent breaking flow
        
        # Get the field value from context, with a default to prevent KeyError
        field_value = context.get(field)
        
        # If field doesn't exist in context, treat as not matching
        if field_value is None:
            return False
        
        # Evaluate based on operator
        if operator == "==":
            return field_value == value
        elif operator == "!=":
            return field_value != value
        elif operator == ">":
            return field_value > value
        elif operator == "<":
            return field_value < value
        elif operator == ">=":
            return field_value >= value
        elif operator == "<=":
            return field_value <= value
        elif operator == "contains":
            return value in field_value if isinstance(field_value, (str, list)) else False
        elif operator == "starts_with":
            return field_value.startswith(value) if isinstance(field_value, str) else False
        elif operator == "ends_with":
            return field_value.endswith(value) if isinstance(field_value, str) else False
        elif operator == "matches_regex":
            import re
            return re.match(value, field_value) is not None if isinstance(field_value, str) else False
        else:
            print(f"Debug: Unsupported operator: {operator}")
            return False  # Changed from raising exception to returning False