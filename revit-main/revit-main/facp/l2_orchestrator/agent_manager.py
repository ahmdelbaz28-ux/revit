"""
FACP Agent Manager - Manages agents for the orchestrator
"""
from typing import Dict, Any, List, Optional, Type
from abc import ABC, abstractmethod
import time
import uuid
import threading


class BaseAgent(ABC):
    """
    Base class for all agents
    """
    def __init__(self, agent_id: str, name: str, description: str = ""):
        self.id = agent_id
        self.name = name
        self.description = description
        self.created_at = time.time()
        self.last_executed = None
        self.execution_count = 0
        self.capabilities = []
        self.config = {}
        self.is_active = True

    @abstractmethod
    def execute_task(self, request_data: Dict[str, Any], execution_context) -> Dict[str, Any]:
        """
        Execute a task with this agent
        """
        pass

    def can_handle_method(self, method: str) -> bool:
        """
        Check if this agent can handle a specific method
        """
        return method in self.capabilities

    def update_config(self, new_config: Dict[str, Any]):
        """
        Update agent configuration
        """
        self.config.update(new_config)

    def get_status(self) -> Dict[str, Any]:
        """
        Get agent status information
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "last_executed": self.last_executed,
            "execution_count": self.execution_count,
            "capabilities": self.capabilities,
            "is_active": self.is_active,
            "uptime_seconds": time.time() - self.created_at
        }


class PlannerAgent(BaseAgent):
    """
    Agent for planning tasks
    """
    def __init__(self):
        super().__init__("planner_agent", "Planner Agent", "Handles planning and scheduling tasks")
        self.capabilities = ["agent.plan", "plan.create", "schedule.optimize", "task.arrange"]
        self.planning_strategies = ["greedy", "optimal", "heuristic"]

    def execute_task(self, request_data: Dict[str, Any], execution_context) -> Dict[str, Any]:
        """
        Execute planning task
        """
        self.last_executed = time.time()
        self.execution_count += 1
        
        method = request_data.get("method", "")
        params = request_data.get("params", {})
        
        if method == "plan.create":
            # Create a plan based on parameters
            plan_params = params.get("plan", {})
            plan_type = plan_params.get("type", "generic")
            
            result = {
                "plan_id": str(uuid.uuid4()),
                "type": plan_type,
                "tasks": plan_params.get("tasks", []),
                "estimated_duration": plan_params.get("duration", "unknown"),
                "resources_required": plan_params.get("resources", []),
                "created_at": time.time()
            }
            
            return {
                "status": "success",
                "result": result,
                "agent_id": self.id,
                "method": method
            }
        
        elif method == "schedule.optimize":
            # Optimize a schedule
            schedule_params = params.get("schedule", {})
            
            result = {
                "optimized_schedule": schedule_params.get("tasks", []),
                "improvement_percentage": 15.5,  # Example improvement
                "optimized_at": time.time()
            }
            
            return {
                "status": "success", 
                "result": result,
                "agent_id": self.id,
                "method": method
            }
        
        else:
            return {
                "status": "error",
                "error": f"Planner agent cannot handle method: {method}",
                "agent_id": self.id
            }


class ExecutorAgent(BaseAgent):
    """
    Agent for executing tasks
    """
    def __init__(self):
        super().__init__("executor_agent", "Executor Agent", "Handles task execution")
        self.capabilities = ["agent.execute", "task.run", "process.start", "action.perform"]

    def execute_task(self, request_data: Dict[str, Any], execution_context) -> Dict[str, Any]:
        """
        Execute a task
        """
        self.last_executed = time.time()
        self.execution_count += 1
        
        method = request_data.get("method", "")
        params = request_data.get("params", {})
        
        if method in ["agent.execute", "task.run"]:
            # Execute the requested task
            task = params.get("task", {})
            task_type = task.get("type", "generic")
            
            # Simulate task execution
            result = {
                "task_id": task.get("id", str(uuid.uuid4())),
                "type": task_type,
                "status": "completed",
                "execution_time": 0.123,  # seconds
                "output": task.get("expected_output", "Task completed successfully"),
                "executed_at": time.time()
            }
            
            return {
                "status": "success",
                "result": result,
                "agent_id": self.id,
                "method": method
            }
        
        else:
            return {
                "status": "error",
                "error": f"Executor agent cannot handle method: {method}",
                "agent_id": self.id
            }


class ValidatorAgent(BaseAgent):
    """
    Agent for validation tasks
    """
    def __init__(self):
        super().__init__("validator_agent", "Validator Agent", "Handles validation and verification tasks")
        self.capabilities = ["agent.validate", "validation.check", "verify.data", "confirm.quality"]

    def execute_task(self, request_data: Dict[str, Any], execution_context) -> Dict[str, Any]:
        """
        Execute validation task
        """
        self.last_executed = time.time()
        self.execution_count += 1
        
        method = request_data.get("method", "")
        params = request_data.get("params", {})
        
        if method in ["agent.validate", "validation.check"]:
            # Validate the provided data
            validation_target = params.get("target", {})
            validation_type = params.get("type", "generic")
            
            # Perform validation (simulated)
            is_valid = True  # In real implementation, this would perform actual validation
            validation_result = {
                "is_valid": is_valid,
                "validation_type": validation_type,
                "issues_found": 0,
                "validation_details": {"compliance": True, "accuracy": True},
                "validated_at": time.time()
            }
            
            return {
                "status": "success",
                "result": validation_result,
                "agent_id": self.id,
                "method": method
            }
        
        else:
            return {
                "status": "error",
                "error": f"Validator agent cannot handle method: {method}",
                "agent_id": self.id
            }


class OptimizerAgent(BaseAgent):
    """
    Agent for optimization tasks
    """
    def __init__(self):
        super().__init__("optimizer_agent", "Optimizer Agent", "Handles optimization tasks")
        self.capabilities = ["agent.optimize", "optimize.performance", "tune.parameters", "improve.efficiency"]

    def execute_task(self, request_data: Dict[str, Any], execution_context) -> Dict[str, Any]:
        """
        Execute optimization task
        """
        self.last_executed = time.time()
        self.execution_count += 1
        
        method = request_data.get("method", "")
        params = request_data.get("params", {})
        
        if method == "optimize.performance":
            # Optimize performance parameters
            target = params.get("target", {})
            optimization_goals = params.get("goals", [])
            
            result = {
                "optimization_applied": True,
                "improvement_metrics": {
                    "performance_gain": "15%",
                    "resource_efficiency": "20% reduction",
                    "cost_savings": "10%"
                },
                "optimized_parameters": target.get("parameters", {}),
                "optimized_at": time.time()
            }
            
            return {
                "status": "success",
                "result": result,
                "agent_id": self.id,
                "method": method
            }
        
        else:
            return {
                "status": "error",
                "error": f"Optimizer agent cannot handle method: {method}",
                "agent_id": self.id
            }


class AgentManager:
    """
    Manager for all agents in the system
    """
    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.agent_types: Dict[str, Type[BaseAgent]] = {}
        self.lock = threading.Lock()
        
        # Register default agent types
        self._register_default_agents()
    
    def _register_default_agents(self):
        """
        Register default agent types
        """
        self.register_agent_type("planner", PlannerAgent)
        self.register_agent_type("executor", ExecutorAgent)
        self.register_agent_type("validator", ValidatorAgent)
        self.register_agent_type("optimizer", OptimizerAgent)
    
    def register_agent_type(self, agent_type: str, agent_class: Type[BaseAgent]):
        """
        Register a new agent type
        """
        self.agent_types[agent_type] = agent_class
    
    def create_agent(self, agent_type: str, agent_id: str = None, **kwargs) -> Optional[BaseAgent]:
        """
        Create a new agent instance
        """
        if agent_type not in self.agent_types:
            return None
        
        agent_id = agent_id or f"{agent_type}_agent_{int(time.time())}"
        agent_class = self.agent_types[agent_type]
        
        try:
            agent = agent_class(**kwargs)
            agent.id = agent_id
            
            with self.lock:
                self.agents[agent_id] = agent
            
            return agent
        except Exception:
            return None
    
    def register_agent(self, agent: BaseAgent):
        """
        Register an existing agent instance
        """
        with self.lock:
            self.agents[agent.id] = agent
    
    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """
        Get an agent by ID
        """
        return self.agents.get(agent_id)
    
    def find_appropriate_agent(self, method: str) -> Optional[BaseAgent]:
        """
        Find an agent that can handle the specified method
        """
        with self.lock:
            for agent in self.agents.values():
                if agent.is_active and agent.can_handle_method(method):
                    return agent
        return None
    
    def find_agents_by_capability(self, capability: str) -> List[BaseAgent]:
        """
        Find all agents with a specific capability
        """
        result = []
        with self.lock:
            for agent in self.agents.values():
                if capability in agent.capabilities and agent.is_active:
                    result.append(agent)
        return result
    
    def execute_task_with_agent(self, method: str, request_data: Dict[str, Any], 
                               execution_context) -> Dict[str, Any]:
        """
        Execute a task using the appropriate agent
        """
        agent = self.find_appropriate_agent(method)
        
        if not agent:
            return {
                "status": "error",
                "error": f"No agent available to handle method: {method}",
                "available_agents": [a.id for a in self.agents.values() if a.is_active]
            }
        
        try:
            result = agent.execute_task(request_data, execution_context)
            return result
        except Exception as e:
            return {
                "status": "error",
                "error": f"Agent {agent.id} execution failed: {str(e)}",
                "agent_id": agent.id
            }
    
    def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status of a specific agent
        """
        agent = self.get_agent(agent_id)
        if agent:
            return agent.get_status()
        return None
    
    def get_all_agents_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all agents
        """
        statuses = {}
        with self.lock:
            for agent_id, agent in self.agents.items():
                statuses[agent_id] = agent.get_status()
        return statuses
    
    def deactivate_agent(self, agent_id: str) -> bool:
        """
        Deactivate an agent
        """
        agent = self.get_agent(agent_id)
        if agent:
            agent.is_active = False
            return True
        return False
    
    def activate_agent(self, agent_id: str) -> bool:
        """
        Activate an agent
        """
        agent = self.get_agent(agent_id)
        if agent:
            agent.is_active = True
            return True
        return False
    
    def remove_agent(self, agent_id: str) -> bool:
        """
        Remove an agent from the manager
        """
        with self.lock:
            if agent_id in self.agents:
                del self.agents[agent_id]
                return True
        return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get agent manager statistics
        """
        all_statuses = self.get_all_agents_status()
        
        active_agents = [status for status in all_statuses.values() if status["is_active"]]
        total_executions = sum(status["execution_count"] for status in all_statuses.values())
        
        return {
            "total_agents": len(all_statuses),
            "active_agents": len(active_agents),
            "inactive_agents": len(all_statuses) - len(active_agents),
            "total_executions": total_executions,
            "average_executions_per_agent": total_executions / len(all_statuses) if all_statuses else 0,
            "agent_types_registered": list(self.agent_types.keys())
        }
    
    def cleanup_inactive_agents(self, min_uptime_hours: float = 24):
        """
        Remove agents that have been inactive for a specified time
        """
        current_time = time.time()
        cutoff_time = current_time - (min_uptime_hours * 3600)
        
        agents_to_remove = []
        with self.lock:
            for agent_id, agent in self.agents.items():
                if not agent.is_active and agent.created_at < cutoff_time:
                    agents_to_remove.append(agent_id)
        
        for agent_id in agents_to_remove:
            self.remove_agent(agent_id)
        
        return len(agents_to_remove)


class LoadBalancingAgentManager(AgentManager):
    """
    Agent manager with load balancing capabilities
    """
    def __init__(self):
        super().__init__()
        self.agent_load = {}  # agent_id -> current_load
        self.load_threshold = 10  # Maximum tasks per agent
    
    def find_appropriate_agent(self, method: str) -> Optional[BaseAgent]:
        """
        Find an appropriate agent with the lowest load
        """
        available_agents = []
        
        with self.lock:
            for agent in self.agents.values():
                if agent.is_active and agent.can_handle_method(method):
                    current_load = self.agent_load.get(agent.id, 0)
                    if current_load < self.load_threshold:
                        available_agents.append((agent, current_load))
        
        if not available_agents:
            return None
        
        # Return agent with lowest load
        selected_agent, _ = min(available_agents, key=lambda x: x[1])
        return selected_agent
    
    def record_agent_task_start(self, agent_id: str):
        """
        Record that an agent started a task
        """
        with self.lock:
            self.agent_load[agent_id] = self.agent_load.get(agent_id, 0) + 1
    
    def record_agent_task_end(self, agent_id: str):
        """
        Record that an agent finished a task
        """
        with self.lock:
            if agent_id in self.agent_load:
                self.agent_load[agent_id] = max(0, self.agent_load[agent_id] - 1)
    
    def execute_task_with_agent(self, method: str, request_data: Dict[str, Any], 
                               execution_context) -> Dict[str, Any]:
        """
        Execute a task with load balancing
        """
        agent = self.find_appropriate_agent(method)
        
        if not agent:
            return {
                "status": "error",
                "error": f"No available agent to handle method: {method}",
                "available_agents": [a.id for a in self.agents.values() if a.is_active]
            }
        
        # Record task start
        self.record_agent_task_start(agent.id)
        
        try:
            result = agent.execute_task(request_data, execution_context)
            return result
        except Exception as e:
            return {
                "status": "error",
                "error": f"Agent {agent.id} execution failed: {str(e)}",
                "agent_id": agent.id
            }
        finally:
            # Record task end
            self.record_agent_task_end(agent.id)


class AgentRegistry:
    """
    Registry for agent discovery and management
    """
    def __init__(self):
        self.agents = {}  # name -> agent_instance
        self.tags = {}  # tag -> list_of_agent_names
        self.metadata = {}  # name -> metadata_dict
    
    def register_agent(self, name: str, agent, tags: List[str] = None, metadata: Dict[str, Any] = None):
        """
        Register an agent with tags and metadata
        """
        self.agents[name] = agent
        
        if tags:
            for tag in tags:
                if tag not in self.tags:
                    self.tags[tag] = []
                if name not in self.tags[tag]:
                    self.tags[tag].append(name)
        
        self.metadata[name] = metadata or {}
    
    def find_agents_by_tag(self, tag: str) -> List:
        """
        Find agents by tag
        """
        if tag in self.tags:
            return [self.agents[name] for name in self.tags[tag]]
        return []
    
    def find_agents_by_tags_all(self, tags: List[str]) -> List:
        """
        Find agents that have ALL specified tags
        """
        if not tags:
            return list(self.agents.values())
        
        # Get agents for the first tag
        if tags[0] not in self.tags:
            return []
        
        candidate_names = set(self.tags[tags[0]])
        
        # Intersect with agents from other tags
        for tag in tags[1:]:
            if tag in self.tags:
                candidate_names &= set(self.tags[tag])
            else:
                candidate_names.clear()
                break
        
        return [self.agents[name] for name in candidate_names]
    
    def find_agents_by_tags_any(self, tags: List[str]) -> List:
        """
        Find agents that have ANY of the specified tags
        """
        agent_names = set()
        for tag in tags:
            if tag in self.tags:
                agent_names.update(self.tags[tag])
        
        return [self.agents[name] for name in agent_names]
    
    def get_agent_metadata(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for an agent
        """
        return self.metadata.get(name)
    
    def get_all_agent_names(self) -> List[str]:
        """
        Get all registered agent names
        """
        return list(self.agents.keys())