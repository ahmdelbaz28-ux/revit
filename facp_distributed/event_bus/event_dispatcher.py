"""Event Dispatcher for Event Bus in Distributed FACP System"""
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from .message_queue import Message, MessagePriority, MessageQueue


class EventListener:
    """Represents an event listener in the distributed system"""

    def __init__(self, name: str, callback: Callable[[Dict[str, Any]], None],
                 event_types: Optional[List[str]] = None, node_filters: Optional[List[str]] = None):
        self.id = f"listener_{name}_{uuid.uuid4().hex[:8]}"
        self.name = name
        self.callback = callback
        self.event_types = event_types or ["*"]  # Listen to all events by default
        self.node_filters = node_filters or []  # Empty means listen to all nodes
        self.created_at = time.time()
        self.is_active = True
        self.last_invoked = None
        self.invocation_count = 0
        self.errors = 0

    def can_handle_event(self, event_data: Dict[str, Any]) -> bool:
        """Check if this listener can handle the given event"""
        if not self.is_active:
            return False

        event_type = event_data.get("event_type", "")
        source_node = event_data.get("source_node", "")

        # Check event type match
        type_match = "*" in self.event_types or event_type in self.event_types

        # Check node filter match
        node_match = not self.node_filters or source_node in self.node_filters or "*" in self.node_filters

        return type_match and node_match

    def invoke(self, event_data: Dict[str, Any]) -> bool:
        """Invoke the listener callback with event data"""
        try:
            self.callback(event_data)
            self.last_invoked = time.time()
            self.invocation_count += 1
            return True
        except Exception as e:
            print(f"Error in listener {self.name}: {e}")
            self.errors += 1
            return False


class EventDispatcher:
    """Centralized event dispatcher for the distributed FACP system"""

    def __init__(self, name: str = "main_dispatcher"):
        self.name = name
        self.dispatcher_id = f"dispatcher_{name}_{uuid.uuid4().hex[:8]}"
        self.listeners: Dict[str, EventListener] = {}
        self.event_queue = MessageQueue(f"dispatcher_{name}_queue", max_size=5000)
        self.routing_rules = {}  # event_type -> [listener_ids]
        self.lock = threading.Lock()
        self.stats = {
            "events_dispatched": 0,
            "events_filtered_out": 0,
            "listener_invocations": 0,
            "listener_errors": 0
        }
        self.running = False
        self.dispatch_thread = None
        self.max_dispatch_workers = 10
        self.dispatch_workers = []
        self.worker_queue = queue.Queue()
        self.broadcast_targets = set()  # Set of target identifiers for broadcasting

    def register_listener(self, name: str, callback: Callable[[Dict[str, Any]], None],
                         event_types: Optional[List[str]] = None, node_filters: Optional[List[str]] = None) -> str:
        """Register a new event listener"""
        with self.lock:
            listener = EventListener(name, callback, event_types, node_filters)
            self.listeners[listener.id] = listener

            # Update routing rules
            for event_type in listener.event_types:
                if event_type not in self.routing_rules:
                    self.routing_rules[event_type] = []
                if listener.id not in self.routing_rules[event_type]:
                    self.routing_rules[event_type].append(listener.id)

            return listener.id

    def unregister_listener(self, listener_id: str) -> bool:
        """Unregister an event listener"""
        with self.lock:
            if listener_id in self.listeners:
                self.listeners[listener_id]

                # Remove from routing rules
                for _event_type, listener_ids in self.routing_rules.items():
                    if listener_id in listener_ids:
                        listener_ids.remove(listener_id)

                del self.listeners[listener_id]
                return True
            return False

    def dispatch_event(self, event_data: Dict[str, Any]) -> List[str]:
        """Dispatch an event to interested listeners"""
        event_type = event_data.get("event_type", "unknown")
        _ = event_data.get("source_node", "unknown")  # NOSONAR: S2201 return value intentionally unused

        matched_listeners = []

        with self.lock:
            # Find matching listeners
            possible_listeners = set()

            # Add listeners for specific event type
            if event_type in self.routing_rules:
                possible_listeners.update(self.routing_rules[event_type])

            # Add listeners for wildcard event type
            if "*" in self.routing_rules:
                possible_listeners.update(self.routing_rules["*"])

            # Filter by actual capability to handle event
            for listener_id in possible_listeners:
                if listener_id in self.listeners:
                    listener = self.listeners[listener_id]
                    if listener.can_handle_event(event_data):
                        matched_listeners.append(listener_id)

        # Invoke matching listeners
        invoked_listeners = []
        for listener_id in matched_listeners:
            if listener_id in self.listeners:
                listener = self.listeners[listener_id]
                if listener.invoke(event_data):
                    invoked_listeners.append(listener_id)
                    with self.lock:
                        self.stats["listener_invocations"] += 1
                else:
                    with self.lock:
                        self.stats["listener_errors"] += 1

        with self.lock:
            self.stats["events_dispatched"] += 1

        return invoked_listeners

    def dispatch_fcep_message(self, facp_message: Dict[str, Any]) -> List[str]:
        """Dispatch a FACP message as an event"""
        # Convert FACP message to event format
        event_data = {
            "event_type": "facp_message",
            "source_node": facp_message.get("source", "unknown"),
            "target_node": facp_message.get("target", "unknown"),
            "method": facp_message.get("method", "unknown"),
            "protocol": facp_message.get("protocol", "unknown"),
            "facp_message": facp_message,
            "dispatched_at": time.time()
        }

        return self.dispatch_event(event_data)

    def broadcast_event(self, event_data: Dict[str, Any], targets: Optional[List[str]] = None) -> Dict[str, List[str]]:
        """Broadcast an event to multiple targets (simulated for distributed system)"""
        if targets is None:
            targets = list(self.broadcast_targets)

        results = {}
        for target in targets:
            # Simulate sending to different targets/nodes
            event_copy = event_data.copy()
            event_copy["broadcast_target"] = target
            event_copy["broadcast_id"] = str(uuid.uuid4())

            # In a real distributed system, this would send to other nodes
            # For simulation, we'll just dispatch locally with target info
            results[target] = self.dispatch_event(event_copy)

        return results

    def queue_event(self, event_data: Dict[str, Any], priority: MessagePriority = MessagePriority.NORMAL) -> bool:
        """Queue an event for later processing"""
        message = Message(
            topic="events",
            data=event_data,
            priority=priority,
            headers={"event_type": event_data.get("event_type", "unknown")}
        )

        return self.event_queue.publish(message)

    def start_processing_queue(self):
        """Start processing events from the queue"""
        if self.running:
            return

        self.running = True
        self.dispatch_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.dispatch_thread.start()

        # Start worker threads
        for _i in range(min(self.max_dispatch_workers, 3)):  # Start with fewer workers
            worker_thread = threading.Thread(target=self._dispatch_worker, daemon=True)
            worker_thread.start()
            self.dispatch_workers.append(worker_thread)

    def stop_processing_queue(self):
        """Stop processing events from the queue"""
        self.running = False
        if self.dispatch_thread:
            self.dispatch_thread.join(timeout=2.0)  # Wait up to 2 seconds

    def _process_queue(self):
        """Internal method to process queued events"""
        while self.running:
            try:
                message = self.event_queue.dequeue()
                if message:
                    # Dispatch the event
                    self.dispatch_event(message.data)

                    # Acknowledge the message
                    self.event_queue.acknowledge(message.id)
                else:
                    # No messages, sleep briefly
                    time.sleep(0.01)
            except Exception as e:
                print(f"Error processing queue: {e}")
                time.sleep(0.1)

    def _dispatch_worker(self):
        """Internal worker method for dispatching events"""
        while self.running:
            try:
                message = self.event_queue.dequeue()
                if message:
                    # Process the event
                    self.dispatch_event(message.data)
                    self.event_queue.acknowledge(message.id)
                else:
                    # No messages, sleep briefly
                    time.sleep(0.01)
            except Exception as e:
                print(f"Error in dispatch worker: {e}")
                time.sleep(0.1)

    def add_broadcast_target(self, target: str):
        """Add a target for event broadcasting"""
        with self.lock:
            self.broadcast_targets.add(target)

    def remove_broadcast_target(self, target: str):
        """Remove a target from event broadcasting"""
        with self.lock:
            self.broadcast_targets.discard(target)

    def get_listener_status(self, listener_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific listener"""
        with self.lock:
            if listener_id in self.listeners:
                listener = self.listeners[listener_id]
                return {
                    "id": listener.id,
                    "name": listener.name,
                    "event_types": listener.event_types,
                    "node_filters": listener.node_filters,
                    "created_at": listener.created_at,
                    "is_active": listener.is_active,
                    "last_invoked": listener.last_invoked,
                    "invocation_count": listener.invocation_count,
                    "errors": listener.errors
                }
        return None

    def get_all_listeners_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all listeners"""
        with self.lock:
            return {lid: self.get_listener_status(lid) for lid in self.listeners}

    def get_dispatcher_status(self) -> Dict[str, Any]:
        """Get status of the event dispatcher"""
        with self.lock:
            return {
                "dispatcher_id": self.dispatcher_id,
                "name": self.name,
                "listener_count": len(self.listeners),
                "routing_rules_count": len(self.routing_rules),
                "stats": self.stats.copy(),
                "queue_size": self.event_queue.get_queue_size(),
                "broadcast_targets_count": len(self.broadcast_targets),
                "running": self.running,
                "uptime_seconds": time.time() - getattr(self, 'start_time', time.time())
            }

    def get_statistics(self) -> Dict[str, Any]:
        """Get detailed statistics for the dispatcher"""
        with self.lock:
            listener_stats = {}
            for lid, listener in self.listeners.items():
                listener_stats[lid] = {
                    "invocation_count": listener.invocation_count,
                    "errors": listener.errors,
                    "success_rate": listener.invocation_count / (listener.invocation_count + listener.errors)
                                    if (listener.invocation_count + listener.errors) > 0 else 0
                }

            return {
                "dispatcher_id": self.dispatcher_id,
                "total_events_dispatched": self.stats["events_dispatched"],
                "total_listener_invocations": self.stats["listener_invocations"],
                "total_listener_errors": self.stats["listener_errors"],
                "average_listeners_per_event": self.stats["listener_invocations"] / self.stats["events_dispatched"]
                                               if self.stats["events_dispatched"] > 0 else 0,
                "listener_statistics": listener_stats,
                "queue_statistics": {
                    "size": self.event_queue.get_queue_size(),
                    "stats": self.event_queue.get_stats()
                }
            }

    def filter_event(self, event_data: Dict[str, Any]) -> bool:
        """Determine if an event should be filtered out"""
        # In a real system, this could implement complex filtering logic
        # For now, implement basic filtering based on event properties
        event_type = event_data.get("event_type", "")

        # Filter out certain event types if needed
        filtered_types = []  # Add event types to filter out
        if event_type in filtered_types:
            with self.lock:
                self.stats["events_filtered_out"] += 1
            return True

        return False

    def enable_listener(self, listener_id: str) -> bool:
        """Enable a listener"""
        with self.lock:
            if listener_id in self.listeners:
                self.listeners[listener_id].is_active = True
                return True
        return False

    def disable_listener(self, listener_id: str) -> bool:
        """Disable a listener"""
        with self.lock:
            if listener_id in self.listeners:
                self.listeners[listener_id].is_active = False
                return True
        return False

    def update_listener_filters(self, listener_id: str, event_types: Optional[List[str]] = None,
                               node_filters: Optional[List[str]] = None) -> bool:
        """Update filters for a listener"""
        with self.lock:
            if listener_id in self.listeners:
                listener = self.listeners[listener_id]

                if event_types is not None:
                    listener.event_types = event_types
                    # Update routing rules
                    for old_type in self.routing_rules:
                        if listener_id in self.routing_rules[old_type]:
                            self.routing_rules[old_type].remove(listener_id)

                    for event_type in event_types:
                        if event_type not in self.routing_rules:
                            self.routing_rules[event_type] = []
                        if listener_id not in self.routing_rules[event_type]:
                            self.routing_rules[event_type].append(listener_id)

                if node_filters is not None:
                    listener.node_filters = node_filters

                return True
        return False

    def cleanup_inactive_listeners(self, min_uptime_minutes: int = 60):
        """Remove inactive listeners"""
        current_time = time.time()
        cutoff_time = current_time - (min_uptime_minutes * 60)

        listeners_to_remove = []
        with self.lock:
            for lid, listener in self.listeners.items():
                if listener.created_at < cutoff_time and listener.invocation_count == 0:
                    listeners_to_remove.append(lid)

        for lid in listeners_to_remove:
            self.unregister_listener(lid)


class DistributedEventDispatcher(EventDispatcher):
    """Distributed event dispatcher with cluster awareness"""

    def __init__(self, name: str = "distributed_dispatcher", node_id: Optional[str] = None):
        super().__init__(name)
        self.node_id = node_id or f"node_{uuid.uuid4().hex[:8]}"
        self.cluster_sync_callback = None
        self.cluster_listeners = {}  # Remote listeners from other nodes
        self.cluster_events_queue = []  # Events from other nodes
        self.federation_enabled = True
        self.local_only_events = set()  # Events that should not be federated

    def set_cluster_sync_callback(self, callback):
        """Set callback for cluster synchronization"""
        self.cluster_sync_callback = callback

    def dispatch_event(self, event_data: Dict[str, Any]) -> List[str]:
        """Override to support distributed event dispatching"""
        # Check if this event should be federated
        event_type = event_data.get("event_type", "")
        if self.federation_enabled and event_type not in self.local_only_events:
            # Notify cluster about this event
            if self.cluster_sync_callback:
                try:
                    self.cluster_sync_callback({
                        "action": "event_dispatched",
                        "event_data": event_data,
                        "node_id": self.node_id,
                        "timestamp": time.time(),
                        "dispatcher_id": self.dispatcher_id
                    })
                except Exception as e:
                    print(f"Error notifying cluster: {e}")

        # Process locally as usual
        return super().dispatch_event(event_data)

    def receive_cluster_event(self, event_data: Dict[str, Any], source_node: str):
        """Receive an event from another cluster node"""
        # Add source node information
        event_data["source_cluster_node"] = source_node
        event_data["received_at"] = time.time()

        # Add to cluster events queue for processing
        self.cluster_events_queue.append(event_data)

        # Process the event locally
        return self.dispatch_event(event_data)

    def sync_with_cluster(self, cluster_state: Dict[str, Any]):
        """Sync dispatcher state with cluster"""
        # Update cluster listeners
        cluster_listeners = cluster_state.get("listeners", {})
        self.cluster_listeners.update(cluster_listeners)

        # Process any queued cluster events
        while self.cluster_events_queue:
            event = self.cluster_events_queue.pop(0)
            self.dispatch_event(event)

    def add_local_only_event(self, event_type: str):
        """Add an event type that should not be federated to other nodes"""
        self.local_only_events.add(event_type)

    def remove_local_only_event(self, event_type: str):
        """Remove an event type from the local-only list"""
        self.local_only_events.discard(event_type)

    def get_cluster_aware_status(self) -> Dict[str, Any]:
        """Get status including cluster information"""
        base_status = self.get_dispatcher_status()
        base_status.update({
            "node_id": self.node_id,
            "cluster_listeners_count": len(self.cluster_listeners),
            "cluster_events_queue_size": len(self.cluster_events_queue),
            "federation_enabled": self.federation_enabled,
            "local_only_events": list(self.local_only_events)
        })
        return base_status


# Import queue module to avoid circular import issues
import queue
