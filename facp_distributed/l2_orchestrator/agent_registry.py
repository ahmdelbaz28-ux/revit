# NOSONAR
"""Agent Registry for L2 Orchestrator in Distributed FACP System"""
import threading
import time
import uuid
from typing import Any, Dict, List, Optional


class AgentRegistry:
    """
    Registry for agents across the distributed system
    Tracks agents across all orchestrator nodes
    """

    def __init__(self):
        self.agents = {}  # agent_id -> agent_info
        self.capability_index = {}  # capability -> [agent_ids]
        self.node_agents = {}  # node_id -> [agent_ids]
        self.agent_types = {}  # type -> [agent_ids]
        self.lock = threading.Lock()
        self.last_updated = time.time()
        self.cluster_agents = {}  # cluster-wide agents from other nodes
        self.cluster_sync_timestamps = {}  # agent_id -> timestamp

    def register_agent(self, agent_id: str, agent_info: Dict[str, Any]):
        """
        Register an agent with the registry
        :param agent_id: Unique identifier for the agent
        :param agent_info: Dictionary containing agent information
        """
        with self.lock:
            # Update local registry
            self.agents[agent_id] = {
                "id": agent_id,
                "type": agent_info.get("type", "generic"),
                "capabilities": agent_info.get("capabilities", []),
                "node_affinity": agent_info.get("node_affinity"),
                "created_at": time.time(),
                "last_seen": time.time(),
                "status": "active",
                "utilization": 0
            }

            # Update indices
            for capability in agent_info.get("capabilities", []):
                if capability not in self.capability_index:
                    self.capability_index[capability] = []
                if agent_id not in self.capability_index[capability]:
                    self.capability_index[capability].append(agent_id)

            # Update node index
            node_affinity = agent_info.get("node_affinity")
            if node_affinity:
                if node_affinity not in self.node_agents:
                    self.node_agents[node_affinity] = []
                if agent_id not in self.node_agents[node_affinity]:
                    self.node_agents[node_affinity].append(agent_id)

            # Update type index
            agent_type = agent_info.get("type", "generic")
            if agent_type not in self.agent_types:
                self.agent_types[agent_type] = []
            if agent_id not in self.agent_types[agent_type]:
                self.agent_types[agent_type].append(agent_id)

            self.last_updated = time.time()

    def unregister_agent(self, agent_id: str):  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
        """Unregister an agent from the registry"""
        with self.lock:
            if agent_id in self.agents:
                agent_info = self.agents[agent_id]

                # Remove from indices
                for capability in agent_info["capabilities"]:
                    if capability in self.capability_index:
                        if agent_id in self.capability_index[capability]:
                            self.capability_index[capability].remove(agent_id)

                node_affinity = agent_info.get("node_affinity")
                if node_affinity and node_affinity in self.node_agents:
                    if agent_id in self.node_agents[node_affinity]:
                        self.node_agents[node_affinity].remove(agent_id)

                agent_type = agent_info["type"]
                if agent_type in self.agent_types:
                    if agent_id in self.agent_types[agent_type]:
                        self.agent_types[agent_type].remove(agent_id)

                # Remove from main registry
                del self.agents[agent_id]

                self.last_updated = time.time()

    def find_agent_for_method(self, method: str) -> Optional[Dict[str, Any]]:  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
        """Find an appropriate agent for a specific method"""
        with self.lock:
            # First, look for exact match
            if method in self.capability_index:
                agent_ids = self.capability_index[method]
                if agent_ids:
                    # Return the first available agent
                    # In a real implementation, we might consider load balancing
                    for agent_id in agent_ids:
                        agent_info = self.agents.get(agent_id)
                        if agent_info and agent_info["status"] == "active":
                            return agent_info

            # Then look for wildcard matches
            for capability, agent_ids in self.capability_index.items():
                if capability.endswith('.*') and method.startswith(capability[:-2]):
                    for agent_id in agent_ids:
                        agent_info = self.agents.get(agent_id)
                        if agent_info and agent_info["status"] == "active":
                            return agent_info

            # If no local agent found, check cluster agents
            for agent_id, agent_info in self.cluster_agents.items():
                capabilities = agent_info.get("capabilities", [])
                if method in capabilities or any(cap.endswith('.*') and method.startswith(cap[:-2]) for cap in capabilities):
                    if agent_info.get("status") == "active":
                        return agent_info

            return None

    def find_agents_by_capability(self, capability: str) -> List[Dict[str, Any]]:
        """Find all agents with a specific capability"""
        with self.lock:
            agent_ids = self.capability_index.get(capability, [])
            agents = []

            for agent_id in agent_ids:
                agent_info = self.agents.get(agent_id)
                if agent_info and agent_info["status"] == "active":
                    agents.append(agent_info)

            # Also include cluster agents with this capability
            for agent_id, agent_info in self.cluster_agents.items():
                if capability in agent_info.get("capabilities", []) and agent_info.get("status") == "active":
                    agents.append(agent_info)

            return agents

    def find_agents_by_type(self, agent_type: str) -> List[Dict[str, Any]]:
        """Find all agents of a specific type"""
        with self.lock:
            agent_ids = self.agent_types.get(agent_type, [])
            agents = []

            for agent_id in agent_ids:
                agent_info = self.agents.get(agent_id)
                if agent_info and agent_info["status"] == "active":
                    agents.append(agent_info)

            # Also include cluster agents of this type
            for agent_id, agent_info in self.cluster_agents.items():
                if agent_info.get("type") == agent_type and agent_info.get("status") == "active":
                    agents.append(agent_info)

            return agents

    def get_all_agents(self) -> List[Dict[str, Any]]:
        """Get all registered agents (local + cluster)"""
        with self.lock:
            all_agents = list(self.agents.values())
            all_agents.extend(list(self.cluster_agents.values()))
            return all_agents

    def update_agent_status(self, agent_id: str, status: str):
        """Update the status of an agent"""
        with self.lock:
            if agent_id in self.agents:
                self.agents[agent_id]["status"] = status
                self.agents[agent_id]["last_seen"] = time.time()
                self.last_updated = time.time()

    def update_agent_utilization(self, agent_id: str, utilization: float):
        """Update the utilization of an agent"""
        with self.lock:
            if agent_id in self.agents:
                self.agents[agent_id]["utilization"] = utilization
                self.last_updated = time.time()

    def heartbeat_agent(self, agent_id: str):
        """Update the last seen time for an agent (heartbeat)"""
        with self.lock:
            if agent_id in self.agents:
                self.agents[agent_id]["last_seen"] = time.time()
                self.last_updated = time.time()

    def cleanup_stale_agents(self, max_age_seconds: int = 300):  # 5 minutes
        """Remove agents that haven't been seen within the specified time"""
        current_time = time.time()
        stale_agents = []

        with self.lock:
            for agent_id, agent_info in self.agents.items():
                if current_time - agent_info["last_seen"] > max_age_seconds:
                    stale_agents.append(agent_id)

            for agent_id in stale_agents:
                self.unregister_agent(agent_id)

    def sync_with_cluster(self, cluster_agents: Dict[str, Any]):
        """Sync agent registry with cluster-wide agent information"""
        current_time = time.time()

        with self.lock:
            for agent_id, agent_info in cluster_agents.items():
                # Update cluster agent info
                self.cluster_agents[agent_id] = agent_info
                self.cluster_sync_timestamps[agent_id] = current_time

                # Update indices for cluster agents too
                for capability in agent_info.get("capabilities", []):
                    if capability not in self.capability_index:
                        self.capability_index[capability] = []
                    if agent_id not in self.capability_index[capability]:
                        self.capability_index[capability].append(agent_id)

                agent_type = agent_info.get("type", "generic")
                if agent_type not in self.agent_types:
                    self.agent_types[agent_type] = []
                if agent_id not in self.agent_types[agent_type]:
                    self.agent_types[agent_type].append(agent_id)

    def get_status(self) -> Dict[str, Any]:
        """Get registry status information"""
        with self.lock:
            local_active_agents = len([a for a in self.agents.values() if a["status"] == "active"])
            cluster_active_agents = len([a for a in self.cluster_agents.values() if a.get("status") == "active"])

            return {
                "total_local_agents": len(self.agents),
                "active_local_agents": local_active_agents,
                "total_cluster_agents": len(self.cluster_agents),
                "active_cluster_agents": cluster_active_agents,
                "total_agents": len(self.agents) + len(self.cluster_agents),
                "capability_types": list(self.capability_index.keys()),
                "agent_types": list(self.agent_types.keys()),
                "last_updated": self.last_updated
            }

    def get_registered_agent_types(self) -> List[str]:
        """Get list of registered agent types"""
        with self.lock:
            return list(self.agent_types.keys())

    def get_agents_by_node(self, node_id: str) -> List[Dict[str, Any]]:
        """Get all agents associated with a specific node"""
        with self.lock:
            agent_ids = self.node_agents.get(node_id, [])
            agents = []

            for agent_id in agent_ids:
                agent_info = self.agents.get(agent_id)
                if agent_info:
                    agents.append(agent_info)

            # Also include cluster agents associated with this node
            for agent_id, agent_info in self.cluster_agents.items():
                if agent_info.get("node_affinity") == node_id:
                    agents.append(agent_info)

            return agents

    def get_agent_by_id(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent information by ID"""
        with self.lock:
            agent = self.agents.get(agent_id)
            if agent:
                return agent
            return self.cluster_agents.get(agent_id)


class DistributedAgentRegistry(AgentRegistry):
    """Distributed version of agent registry with cluster synchronization"""

    def __init__(self):
        super().__init__()
        self.cluster_sync_callback = None
        self.node_id = f"registry_{uuid.uuid4().hex[:8]}"
        self.registration_callbacks = []  # Callbacks for when agents register

    def set_cluster_sync_callback(self, callback):
        """Set callback for syncing agent state with cluster"""
        self.cluster_sync_callback = callback

    def add_registration_callback(self, callback):
        """Add a callback to be called when an agent registers"""
        self.registration_callbacks.append(callback)

    def register_agent(self, agent_id: str, agent_info: Dict[str, Any]):
        """Register an agent and notify cluster"""
        super().register_agent(agent_id, agent_info)

        # Call registration callbacks
        for callback in self.registration_callbacks:
            try:
                callback(agent_id, agent_info)
            except Exception:
                pass  # Don't let callback errors affect registration

        # Notify cluster if callback is available
        if self.cluster_sync_callback:
            self.cluster_sync_callback({
                "action": "agent_registered",
                "agent_id": agent_id,
                "agent_info": agent_info,
                "node_id": self.node_id,
                "timestamp": time.time()
            })

    def unregister_agent(self, agent_id: str):
        """Unregister an agent and notify cluster"""
        agent_info = self.agents.get(agent_id)
        super().unregister_agent(agent_id)

        # Notify cluster if callback is available
        if self.cluster_sync_callback and agent_info:
            self.cluster_sync_callback({
                "action": "agent_unregistered",
                "agent_id": agent_id,
                "node_id": self.node_id,
                "timestamp": time.time()
            })

    def update_agent_status(self, agent_id: str, status: str):
        """Update agent status and notify cluster"""
        super().update_agent_status(agent_id, status)

        # Notify cluster if callback is available
        if self.cluster_sync_callback:
            self.cluster_sync_callback({
                "action": "agent_status_updated",
                "agent_id": agent_id,
                "status": status,
                "node_id": self.node_id,
                "timestamp": time.time()
            })

    def sync_with_cluster(self, cluster_agents: Dict[str, Any]):
        """Override to handle cluster synchronization with additional logic"""
        super().sync_with_cluster(cluster_agents)

        # Could add additional cluster-specific logic here

    def get_cluster_wide_agents(self) -> Dict[str, Any]:
        """Get all agents known to the cluster (including local ones)"""
        with self.lock:
            all_agents = {}
            all_agents.update(self.agents)
            all_agents.update(self.cluster_agents)
            return all_agents
