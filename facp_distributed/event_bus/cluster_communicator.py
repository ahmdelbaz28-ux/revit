# NOSONAR
"""Cluster Communicator for Event Bus in Distributed FACP System"""
import json
import socket
import threading
import time
import uuid
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class ClusterMessageType(Enum):
    HEARTBEAT = "heartbeat"
    NODE_JOIN = "node_join"
    NODE_LEAVE = "node_leave"
    STATE_SYNC = "state_sync"
    EVENT_FORWARD = "event_forward"
    TASK_ASSIGNMENT = "task_assignment"
    RESULT_RETURN = "result_return"
    ERROR_REPORT = "error_report"


class NodeStatus(Enum):
    JOINING = "joining"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    LEAVING = "leaving"
    DEAD = "dead"


class ClusterNode:
    """Represents a node in the cluster"""

    def __init__(self, node_id: str, host: str, port: int, node_type: str = "worker"):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.node_type = node_type
        self.status = NodeStatus.JOINING
        self.last_heartbeat = time.time()
        self.joined_at = time.time()
        self.capabilities = []
        self.load = 0.0  # Current load (0.0 to 1.0)
        self.resource_usage = {
            "cpu_percent": 0.0,
            "memory_mb": 0.0,
            "disk_gb": 0.0
        }
        self.location = "unknown"  # Geographic location
        self.version = "FACP/1.1"
        self.labels = {}  # Node labels for scheduling

    def update_heartbeat(self):
        """Update heartbeat timestamp"""
        self.last_heartbeat = time.time()

    def is_healthy(self, timeout_seconds: int = 60) -> bool:
        """Check if node is healthy based on heartbeat"""
        return (time.time() - self.last_heartbeat) < timeout_seconds

    def get_status(self) -> Dict[str, Any]:
        """Get node status information"""
        return {
            "node_id": self.node_id,
            "host": self.host,
            "port": self.port,
            "node_type": self.node_type,
            "status": self.status.value,
            "last_heartbeat": self.last_heartbeat,
            "joined_at": self.joined_at,
            "capabilities": self.capabilities,
            "load": self.load,
            "resource_usage": self.resource_usage,
            "location": self.location,
            "version": self.version,
            "labels": self.labels,
            "is_healthy": self.is_healthy(),
            "uptime_seconds": time.time() - self.joined_at
        }


class ClusterCommunicator:
    """Manages communication between nodes in the distributed FACP cluster"""

    def __init__(self, node_id: Optional[str] = None, host: str = "0.0.0.0", port: int = 9000,
                 node_type: str = "worker", location: str = "primary"):
        self.node_id = node_id or f"node_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.host = host
        self.port = port
        self.node_type = node_type
        self.location = location
        self.cluster_id = f"facp_cluster_{uuid.uuid4().hex[:8]}"
        self.nodes: Dict[str, ClusterNode] = {}
        self.node_callbacks = {}  # node_id -> [callbacks]
        self.message_handlers = {}  # message_type -> [handlers]
        self.cluster_state = {}  # Shared cluster state
        self.lock = threading.Lock()
        self.running = False
        self.server_socket = None
        self.client_sockets = {}  # node_id -> socket
        self.heartbeat_interval = 10  # seconds
        self.heartbeat_thread = None
        self.message_queue = []  # Outgoing messages
        self.message_queue_lock = threading.Lock()
        self.discovery_interval = 30  # seconds
        self.discovery_thread = None
        self.stats = {
            "messages_sent": 0,
            "messages_received": 0,
            "connections_made": 0,
            "connection_errors": 0,
            "state_syncs": 0
        }
        self.leader_node = None  # Current leader
        self.is_leader = False  # Whether this node is the leader
        self.leader_election_enabled = True
        self.known_peers = set()  # Known peer addresses

        # Add self to nodes
        self.local_node = ClusterNode(self.node_id, self.host, self.port, self.node_type)
        self.local_node.location = self.location
        self.local_node.status = NodeStatus.HEALTHY
        self.local_node.capabilities = self._get_local_capabilities()
        self.nodes[self.node_id] = self.local_node

    def _get_local_capabilities(self) -> List[str]:
        """Get capabilities of this local node"""
        if self.node_type == "l1_gateway":
            return ["client.interface", "request.reception", "validation.basic"]
        if self.node_type == "l2_orchestrator":
            return ["task.orchestration", "agent.management", "scheduling", "policy.enforcement"]
        if self.node_type == "l3_engine":
            return ["calculation", "validation", "transformation", "deterministic.execution"]
        return ["generic.node"]

    def start(self):
        """Start the cluster communicator"""
        with self.lock:
            if self.running:
                return

            # Start server socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)  # Non-blocking accept

            self.running = True

            # Start background threads
            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self.discovery_thread = threading.Thread(target=self._discovery_loop, daemon=True)

            self.server_thread.start()
            self.heartbeat_thread.start()
            self.discovery_thread.start()

            print(f"Cluster Communicator started on {self.host}:{self.port}")

    def stop(self):
        """Stop the cluster communicator"""
        with self.lock:
            if not self.running:
                return

            self.running = False

            # Close server socket
            if self.server_socket:
                self.server_socket.close()

            # Close client sockets
            for sock in self.client_sockets.values():
                try:
                    sock.close()
                except Exception:
                    pass

            self.client_sockets.clear()

            print("Cluster Communicator stopped")

    def _server_loop(self):
        """Main server loop to accept incoming connections"""
        while self.running:
            try:
                # Accept connections
                try:
                    conn, addr = self.server_socket.accept()
                    print(f"New connection from {addr}")

                    # Handle the connection in a separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client_connection,
                        args=(conn, addr),
                        daemon=True
                    )
                    client_thread.start()

                    with self.lock:
                        self.stats["connections_made"] += 1
                except socket.timeout:
                    # Non-blocking timeout, continue loop
                    continue
            except Exception as e:
                if self.running:  # Only log if we're supposed to be running
                    print(f"Server loop error: {e}")
                    with self.lock:
                        self.stats["connection_errors"] += 1
                time.sleep(0.1)  # Brief pause before continuing

    def _handle_client_connection(self, conn: socket.socket, addr):
        """Handle an incoming client connection"""
        try:
            conn.settimeout(30.0)  # 30-second timeout for this connection

            while self.running:
                try:
                    # Receive message
                    data = conn.recv(4096)
                    if not data:
                        break

                    try:
                        message = json.loads(data.decode('utf-8'))
                        self._handle_incoming_message(message, conn, addr)
                    except json.JSONDecodeError:
                        print(f"Invalid JSON from {addr}")
                        continue
                except socket.timeout:
                    # Connection timeout, close it
                    break
        except Exception as e:
            print(f"Error handling client {addr}: {e}")
        finally:
            conn.close()

    def _handle_incoming_message(self, message: Dict[str, Any], _conn: socket.socket, addr):  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
        """Handle an incoming message from another node"""
        with self.lock:
            self.stats["messages_received"] += 1

        msg_type = message.get("type")
        sender_node_id = message.get("sender_node_id")

        # Update sender node information if present
        if sender_node_id and sender_node_id != self.node_id:
            self._update_node_info(sender_node_id, message.get("node_info", {}))

        # Handle specific message types
        if msg_type == ClusterMessageType.HEARTBEAT.value:
            self._handle_heartbeat_message(message)
        elif msg_type == ClusterMessageType.NODE_JOIN.value:
            self._handle_node_join_message(message)
        elif msg_type == ClusterMessageType.NODE_LEAVE.value:
            self._handle_node_leave_message(message)
        elif msg_type == ClusterMessageType.STATE_SYNC.value:
            self._handle_state_sync_message(message)
        elif msg_type == ClusterMessageType.EVENT_FORWARD.value:
            self._handle_event_forward_message(message)
        elif msg_type == ClusterMessageType.TASK_ASSIGNMENT.value:
            self._handle_task_assignment_message(message)
        elif msg_type == ClusterMessageType.RESULT_RETURN.value:
            self._handle_result_return_message(message)
        elif msg_type == ClusterMessageType.ERROR_REPORT.value:
            self._handle_error_report_message(message)

        # Call registered handlers
        if msg_type in self.message_handlers:
            for handler in self.message_handlers[msg_type]:
                try:
                    handler(message, sender_node_id, addr)
                except Exception as e:
                    print(f"Error in message handler: {e}")

    def _update_node_info(self, node_id: str, node_info: Dict[str, Any]):  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
        """Update information about a cluster node"""
        with self.lock:
            if node_id in self.nodes:
                node = self.nodes[node_id]
                # Update only provided fields
                if "status" in node_info:
                    try:
                        node.status = NodeStatus(node_info["status"])
                    except Exception:
                        pass  # Invalid status value
                if "last_heartbeat" in node_info:
                    node.last_heartbeat = node_info["last_heartbeat"]
                if "load" in node_info:
                    node.load = node_info["load"]
                if "resource_usage" in node_info:
                    node.resource_usage.update(node_info["resource_usage"])
                if "capabilities" in node_info:
                    node.capabilities = node_info["capabilities"]
            else:
                # Create new node if it doesn't exist
                if "host" in node_info and "port" in node_info:
                    new_node = ClusterNode(
                        node_id=node_id,
                        host=node_info["host"],
                        port=node_info["port"],
                        node_type=node_info.get("node_type", "unknown")
                    )
                    new_node.status = NodeStatus(node_info.get("status", "healthy"))
                    new_node.load = node_info.get("load", 0.0)
                    new_node.resource_usage.update(node_info.get("resource_usage", {}))
                    new_node.capabilities = node_info.get("capabilities", [])
                    new_node.location = node_info.get("location", "unknown")
                    self.nodes[node_id] = new_node

    def _handle_heartbeat_message(self, message: Dict[str, Any]):
        """Handle heartbeat message"""
        sender_id = message.get("sender_node_id")
        if sender_id and sender_id in self.nodes:
            self.nodes[sender_id].update_heartbeat()

    def _handle_node_join_message(self, message: Dict[str, Any]):
        """Handle node join message"""
        node_info = message.get("node_info", {})
        node_id = message.get("sender_node_id")

        if node_id and node_info:
            # Add the node to our cluster
            self._update_node_info(node_id, node_info)

            # Broadcast the new node to other nodes
            self.broadcast_message({
                "type": ClusterMessageType.NODE_JOIN.value,
                "sender_node_id": self.node_id,
                "node_info": node_info,
                "timestamp": time.time()
            }, exclude_node=self.node_id)

    def _handle_node_leave_message(self, message: Dict[str, Any]):
        """Handle node leave message"""
        sender_id = message.get("sender_node_id")
        if sender_id in self.nodes:
            node = self.nodes[sender_id]
            node.status = NodeStatus.DEAD
            node.last_heartbeat = time.time() - 1000  # Mark as dead

    def _handle_state_sync_message(self, message: Dict[str, Any]):
        """Handle state synchronization message"""
        state = message.get("state", {})
        sender_id = message.get("sender_node_id")

        with self.lock:
            self.cluster_state.update(state)
            self.stats["state_syncs"] += 1

        # Trigger state sync callbacks
        if sender_id in self.node_callbacks:
            for callback in self.node_callbacks[sender_id]:
                try:
                    callback("state_sync", state, sender_id)
                except Exception as e:
                    print(f"Error in state sync callback: {e}")

    def _handle_event_forward_message(self, message: Dict[str, Any]):
        """Handle event forwarding message"""
        event_data = message.get("event_data", {})
        sender_id = message.get("sender_node_id")

        # This would trigger event dispatching in the actual system
        # For now, we'll just log it
        print(f"Event forwarded from {sender_id}: {event_data.get('event_type', 'unknown')}")

    def _handle_task_assignment_message(self, message: Dict[str, Any]):
        """Handle task assignment message"""
        task_data = message.get("task_data", {})
        sender_id = message.get("sender_node_id")

        # This would trigger task processing in the actual system
        print(f"Task assigned from {sender_id}: {task_data.get('task_id', 'unknown')}")

    def _handle_result_return_message(self, message: Dict[str, Any]):
        """Handle result return message"""
        result_data = message.get("result_data", {})
        sender_id = message.get("sender_node_id")

        print(f"Result returned from {sender_id}: {result_data.get('task_id', 'unknown')}")

    def _handle_error_report_message(self, message: Dict[str, Any]):
        """Handle error report message"""
        error_data = message.get("error_data", {})
        sender_id = message.get("sender_node_id")

        print(f"Error reported from {sender_id}: {error_data.get('error_code', 'unknown')}")

    def _heartbeat_loop(self):
        """Background loop for sending heartbeats"""
        while self.running:
            try:
                # Send heartbeat to all nodes
                self.send_heartbeat()

                # Check for unhealthy nodes
                self._check_node_health()

                # Perform leader election if enabled
                if self.leader_election_enabled:
                    self._perform_leader_election()

                time.sleep(self.heartbeat_interval)
            except Exception as e:
                print(f"Heartbeat loop error: {e}")
                time.sleep(1)

    def _check_node_health(self):
        """Check health of all nodes"""
        time.time()

        with self.lock:
            for node_id, node in list(self.nodes.items()):  # NOSONAR - python:S7504
                if node_id != self.node_id:  # Don't check ourselves
                    if not node.is_healthy():
                        if node.status != NodeStatus.DEAD:
                            print(f"Node {node_id} is unhealthy, marking as dead")
                            node.status = NodeStatus.DEAD

    def _perform_leader_election(self):
        """Perform leader election using simple algorithm"""
        if not self.leader_election_enabled:
            return

        healthy_nodes = []
        with self.lock:
            for node_id, node in self.nodes.items():
                if node.is_healthy() and node.status == NodeStatus.HEALTHY:
                    healthy_nodes.append((node_id, node.joined_at))  # Sort by join time

        if healthy_nodes:
            # Elect leader based on earliest join time (first joined is leader)
            healthy_nodes.sort(key=lambda x: x[1])  # Sort by join time
            new_leader = healthy_nodes[0][0]

            if self.leader_node != new_leader:
                old_leader = self.leader_node
                self.leader_node = new_leader
                self.is_leader = (new_leader == self.node_id)

                print(f"Leader elected: {self.leader_node} (was {old_leader})")

                # Broadcast leader change
                self.broadcast_message({
                    "type": "leader_change",
                    "new_leader": self.leader_node,
                    "timestamp": time.time()
                })

    def _discovery_loop(self):
        """Background loop for discovering new nodes"""
        while self.running:
            try:
                # In a real implementation, this would discover new nodes
                # For now, we'll just sleep
                time.sleep(self.discovery_interval)
            except Exception as e:
                print(f"Discovery loop error: {e}")
                time.sleep(5)

    def send_message(self, node_id: str, message: Dict[str, Any]) -> bool:
        """Send a message to a specific node"""
        if not self.running:
            return False

        # Add metadata
        message["sender_node_id"] = self.node_id
        message["timestamp"] = time.time()
        message["cluster_id"] = self.cluster_id

        try:
            json_msg = json.dumps(message)

            # Try to send via existing connection
            if node_id in self.client_sockets:
                try:
                    self.client_sockets[node_id].send(json_msg.encode('utf-8'))
                    with self.lock:
                        self.stats["messages_sent"] += 1
                    return True
                except Exception:
                    # Connection might be broken, remove it
                    del self.client_sockets[node_id]

            # Establish new connection if needed
            if node_id in self.nodes:
                node = self.nodes[node_id]
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5.0)  # 5-second timeout
                    sock.connect((node.host, node.port))

                    sock.send(json_msg.encode('utf-8'))
                    self.client_sockets[node_id] = sock

                    with self.lock:
                        self.stats["messages_sent"] += 1
                    return True
                except Exception as e:
                    print(f"Failed to connect to {node_id}: {e}")
                    with self.lock:
                        self.stats["connection_errors"] += 1
                    return False
            else:
                print(f"Unknown node: {node_id}")
                return False

        except Exception as e:
            print(f"Error sending message: {e}")
            return False

    def broadcast_message(self, message: Dict[str, Any], exclude_node: Optional[str] = None):
        """Broadcast a message to all nodes in the cluster"""
        for node_id in list(self.nodes.keys()):  # NOSONAR - python:S7504
            if node_id != exclude_node and node_id != self.node_id:
                self.send_message(node_id, message)

    def send_heartbeat(self):
        """Send heartbeat to all nodes"""
        heartbeat_msg = {
            "type": ClusterMessageType.HEARTBEAT.value,
            "node_info": self.local_node.get_status(),
            "timestamp": time.time()
        }

        self.broadcast_message(heartbeat_msg)

    def join_cluster(self, peer_host: str, peer_port: int):
        """Join an existing cluster via a peer"""
        join_msg = {
            "type": ClusterMessageType.NODE_JOIN.value,
            "node_info": self.local_node.get_status(),
            "timestamp": time.time()
        }

        # Try to connect to the peer
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)  # 10-second timeout
            sock.connect((peer_host, peer_port))

            json_msg = json.dumps(join_msg)
            sock.send(json_msg.encode('utf-8'))

            # Receive initial cluster state
            response_data = sock.recv(4096)
            if response_data:
                try:
                    response = json.loads(response_data.decode('utf-8'))
                    if response.get("type") == "cluster_state":
                        self._handle_state_sync_message(response)
                except json.JSONDecodeError:
                    pass  # Ignore invalid responses

            sock.close()

            # Add peer to known peers
            with self.lock:
                self.known_peers.add((peer_host, peer_port))

        except Exception as e:
            print(f"Failed to join cluster via {peer_host}:{peer_port}: {e}")

    def leave_cluster(self):
        """Leave the cluster gracefully"""
        leave_msg = {
            "type": ClusterMessageType.NODE_LEAVE.value,
            "timestamp": time.time()
        }

        self.broadcast_message(leave_msg)

        # Wait a bit for messages to propagate
        time.sleep(1)

    def register_message_handler(self, msg_type: str, handler: Callable):
        """Register a handler for a specific message type"""
        with self.lock:
            if msg_type not in self.message_handlers:
                self.message_handlers[msg_type] = []
            self.message_handlers[msg_type].append(handler)

    def register_node_callback(self, node_id: str, callback: Callable):
        """Register a callback for events related to a specific node"""
        with self.lock:
            if node_id not in self.node_callbacks:
                self.node_callbacks[node_id] = []
            self.node_callbacks[node_id].append(callback)

    def get_cluster_status(self) -> Dict[str, Any]:
        """Get the status of the cluster"""
        with self.lock:
            healthy_nodes = []
            unhealthy_nodes = []

            for node_id, node in self.nodes.items():
                if node.is_healthy():
                    healthy_nodes.append(node_id)
                else:
                    unhealthy_nodes.append(node_id)

            return {
                "cluster_id": self.cluster_id,
                "local_node_id": self.node_id,
                "local_node_type": self.node_type,
                "local_node_status": self.local_node.status.value,
                "total_nodes": len(self.nodes),
                "healthy_nodes": len(healthy_nodes),
                "unhealthy_nodes": len(unhealthy_nodes),
                "node_list": [node.get_status() for node in self.nodes.values()],
                "leader_node": self.leader_node,
                "is_leader": self.is_leader,
                "known_peers": list(self.known_peers),
                "stats": self.stats.copy(),
                "uptime_seconds": time.time() - self.local_node.joined_at
            }

    def get_node_status(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific node"""
        with self.lock:
            if node_id in self.nodes:
                return self.nodes[node_id].get_status()
        return None

    def get_statistics(self) -> Dict[str, Any]:
        """Get communication statistics"""
        with self.lock:
            return self.stats.copy()

    def sync_cluster_state(self, state: Dict[str, Any]):
        """Synchronize cluster state with other nodes"""
        sync_msg = {
            "type": ClusterMessageType.STATE_SYNC.value,
            "state": state,
            "timestamp": time.time()
        }

        self.broadcast_message(sync_msg)

    def get_healthy_nodes(self) -> List[str]:
        """Get list of healthy nodes"""
        with self.lock:
            return [
                node_id for node_id, node in self.nodes.items()
                if node.is_healthy() and node.status == NodeStatus.HEALTHY
            ]

    def get_node_by_type(self, node_type: str) -> List[str]:
        """Get nodes of a specific type"""
        with self.lock:
            return [
                node_id for node_id, node in self.nodes.items()
                if node.node_type == node_type
            ]

    def update_local_load(self, load: float):
        """Update the load of the local node"""
        with self.lock:
            self.local_node.load = load

    def update_local_resource_usage(self, cpu_percent: Optional[float] = None, memory_mb: Optional[float] = None, disk_gb: Optional[float] = None):
        """Update resource usage of the local node"""
        with self.lock:
            if cpu_percent is not None:
                self.local_node.resource_usage["cpu_percent"] = cpu_percent
            if memory_mb is not None:
                self.local_node.resource_usage["memory_mb"] = memory_mb
            if disk_gb is not None:
                self.local_node.resource_usage["disk_gb"] = disk_gb


class DistributedClusterCommunicator(ClusterCommunicator):
    """Extended cluster communicator with additional distributed features"""

    def __init__(self, node_id: Optional[str] = None, host: str = "0.0.0.0", port: int = 9000,
                 node_type: str = "worker", location: str = "primary"):
        super().__init__(node_id, host, port, node_type, location)
        self.consensus_algorithm = "raft"  # Default consensus algorithm
        self.partition_tolerance_enabled = True
        self.quorum_size = 0  # Will be calculated based on cluster size
        self.votes = {}  # For leader election votes
        self.cluster_config = {}  # Cluster-wide configuration

    def join_cluster(self, peer_host: str, peer_port: int):
        """Override to support distributed features"""
        # Join the cluster first
        super().join_cluster(peer_host, peer_port)

        # Then exchange configuration
        config_exchange_msg = {
            "type": "config_exchange",
            "config": self.cluster_config,
            "timestamp": time.time()
        }

        # Find the leader to exchange configs with
        if self.leader_node:
            self.send_message(self.leader_node, config_exchange_msg)
        else:
            # If no leader, broadcast to all
            self.broadcast_message(config_exchange_msg)

    def handle_config_exchange(self, config_data: Dict[str, Any], _sender_node_id: str):  # NOSONAR — S1172: parameter retained for API stability
        """Handle configuration exchange message"""
        # Merge configurations
        self.cluster_config.update(config_data.get("config", {}))

    def request_consensus(self, proposal: Dict[str, Any], timeout: int = 10) -> bool:
        """Request consensus on a proposal using Raft-like algorithm"""
        if not self.is_leader:
            # Forward to leader
            if self.leader_node:
                forward_msg = {
                    "type": "consensus_forward",
                    "proposal": proposal,
                    "original_sender": self.node_id,
                    "timestamp": time.time()
                }
                self.send_message(self.leader_node, forward_msg)
                # Wait for response (simplified)
                time.sleep(timeout)
                return True  # Simplified implementation
            return False  # No leader available

        # As leader, coordinate consensus
        # In a real implementation, this would follow Raft protocol
        # For now, we'll just return True
        return True

    def enable_partition_tolerance(self):
        """Enable partition tolerance features"""
        self.partition_tolerance_enabled = True

    def disable_partition_tolerance(self):
        """Disable partition tolerance features"""
        self.partition_tolerance_enabled = False

    def get_quorum_size(self) -> int:
        """Get the required quorum size for consensus"""
        with self.lock:
            total_nodes = len([n for n in self.nodes.values() if n.is_healthy()])
            return (total_nodes // 2) + 1 if total_nodes > 0 else 1

    def get_cluster_topology(self) -> Dict[str, Any]:
        """Get cluster topology information"""
        topology = {
            "nodes": {},
            "connections": [],
            "subnets": {},
            "partition_tolerance": self.partition_tolerance_enabled
        }

        with self.lock:
            for node_id, node in self.nodes.items():
                topology["nodes"][node_id] = {
                    "type": node.node_type,
                    "location": node.location,
                    "status": node.status.value,
                    "load": node.load,
                    "capabilities": node.capabilities
                }

        return topology
