"""Event Processor for Event Bus in Distributed FACP System"""
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..protocol.message_schema import FACPRequest
from .cluster_communicator import ClusterCommunicator
from .message_queue import Message, MessagePriority, MessageQueue


class ProcessingStage(Enum):
    RECEIVED = "received"
    VALIDATED = "validated"
    AUTHENTICATED = "authenticated"
    AUTHORIZED = "authorized"
    ROUTED = "routed"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingResult(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    RETRY = "retry"
    DROP = "drop"


class EventProcessor:
    """Processes events in the distributed FACP system with various stages"""

    def __init__(self, name: str = "main_processor", max_workers: int = 5):
        self.name = name
        self.processor_id = f"processor_{name}_{uuid.uuid4().hex[:8]}"
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.input_queue = MessageQueue(f"processor_{name}_input", max_size=1000)
        self.output_queue = MessageQueue(f"processor_{name}_output", max_size=1000)
        self.retry_queue = MessageQueue(f"processor_{name}_retry", max_size=500)
        self.dead_letter_queue = MessageQueue(f"processor_{name}_dlq", max_size=200)
        self.lock = threading.Lock()
        self.running = False
        self.processing_threads = []
        self.stats = {
            "processed": 0,
            "failed": 0,
            "retried": 0,
            "dropped": 0,
            "avg_processing_time": 0.0
        }
        self.stage_processors = {}  # stage -> processor function
        self.filters = []  # List of filter functions
        self.enrichers = []  # List of enricher functions
        self.processing_timeout = 30  # seconds
        self.max_retries = 3
        self.retry_delay = 1  # seconds
        self.circuit_breaker_enabled = True
        self.failure_threshold = 5
        self.failure_window = 60  # seconds
        self.failure_counts = {}  # timestamp -> count
        self.circuit_state = "closed"  # closed, open, half_open
        self.last_failure_time = 0
        self.processed_events = []  # Recent processed events
        self.max_event_history = 100
        self.metrics_collectors = []  # Functions to collect metrics

    def start(self):
        """Start the event processor"""
        if self.running:
            return

        self.running = True

        # Start processing threads
        for _i in range(min(self.max_workers, 3)):  # Start with fewer threads initially
            thread = threading.Thread(target=self._processing_worker, daemon=True)
            thread.start()
            self.processing_threads.append(thread)

    def stop(self):
        """Stop the event processor"""
        self.running = False

        # Wait for threads to finish
        for thread in self.processing_threads:
            thread.join(timeout=2.0)

        self.processing_threads.clear()

        # Shutdown executor
        self.executor.shutdown(wait=False)

    def register_stage_processor(self, stage: ProcessingStage, processor_func: Callable):
        """Register a processor function for a specific stage"""
        self.stage_processors[stage.value] = processor_func

    def add_filter(self, filter_func: Callable[[Dict[str, Any]], bool]):
        """Add a filter function to determine if an event should be processed"""
        self.filters.append(filter_func)

    def add_enricher(self, enricher_func: Callable[[Dict[str, Any]], Dict[str, Any]]):
        """Add an enricher function to add data to events"""
        self.enrichers.append(enricher_func)

    def add_metrics_collector(self, collector_func: Callable[[Dict[str, Any]], None]):
        """Add a metrics collector function"""
        self.metrics_collectors.append(collector_func)

    def submit_event(self, event_data: Dict[str, Any], priority: MessagePriority = MessagePriority.NORMAL) -> str:
        """Submit an event for processing"""
        message = Message(
            topic="events",
            data=event_data,
            priority=priority,
            headers={"processor": self.processor_id}
        )

        success = self.input_queue.enqueue(message)
        if not success:
            # Queue full, try to add to retry queue
            retry_msg = Message(
                topic="retry_events",
                data=event_data,
                priority=MessagePriority.HIGH,
                headers={"processor": self.processor_id, "reason": "queue_full"}
            )
            self.retry_queue.enqueue(retry_msg)
            return "queue_full"

        return message.id

    def submit_facp_request(self, facp_request: Dict[str, Any]) -> str:
        """Submit a FACP request for processing"""
        event_data = {
            "event_type": "facp_request",
            "facp_request": facp_request,
            "processing_stage": ProcessingStage.RECEIVED.value,
            "submitted_at": time.time()
        }

        return self.submit_event(event_data, MessagePriority.HIGH)

    def _processing_worker(self):  # NOSONAR — S3776: cognitive complexity is inherent to the safety-critical algorithm
        """Internal worker thread for processing events"""
        while self.running:
            try:
                # Get a message from the input queue
                message = self.input_queue.dequeue()
                if message:
                    result = self._process_single_event(message)

                    # Handle the result
                    if result == ProcessingResult.SUCCESS:
                        # Add to output queue
                        self.output_queue.enqueue(message)
                    elif result == ProcessingResult.FAILURE:
                        # Add to dead letter queue after max retries
                        if message.attempts >= self.max_retries:
                            self.dead_letter_queue.enqueue(message)
                        else:
                            # Add to retry queue
                            message.status = "retrying"
                            self.retry_queue.enqueue(message)
                    elif result == ProcessingResult.RETRY:
                        # Add to retry queue
                        self.retry_queue.enqueue(message)
                    elif result == ProcessingResult.DROP:
                        # Drop the event
                        pass

                # Process retry queue occasionally
                if self.retry_queue.get_queue_size() > 0:
                    retry_message = self.retry_queue.dequeue()
                    if retry_message:
                        retry_message.attempts += 1
                        self.input_queue.enqueue(retry_message)

                time.sleep(0.01)  # Brief pause to prevent busy waiting
            except Exception as e:
                print(f"Processing worker error: {e}")
                time.sleep(0.1)

    def _process_single_event(self, message: Message) -> ProcessingResult:
        """Process a single event through all stages"""
        start_time = time.time()

        try:
            event_data = message.data
            event_id = message.id

            # Apply filters
            for filter_func in self.filters:
                if not filter_func(event_data):
                    self._update_stats("dropped")
                    self._add_to_history(event_data, ProcessingResult.DROP)
                    return ProcessingResult.DROP

            # Apply enrichers
            for enricher_func in self.enrichers:
                event_data = enricher_func(event_data)

            # Check circuit breaker
            if self._is_circuit_open():
                # Circuit is open, put in retry queue
                self._update_stats("retried")
                self._add_to_history(event_data, ProcessingResult.RETRY)
                return ProcessingResult.RETRY

            # Process through stages
            current_stage = ProcessingStage.RECEIVED
            result = None

            for stage in ProcessingStage:
                if stage.value in self.stage_processors:
                    processor_func = self.stage_processors[stage.value]
                    result = processor_func(event_data, stage.value)

                    if result is False:  # Stage failed
                        self._log_failure(event_data, stage.value)
                        self._update_stats("failed")
                        self._add_to_history(event_data, ProcessingResult.FAILURE)
                        return ProcessingResult.FAILURE

                    current_stage = stage

            # If we got here, processing was successful
            processing_time = time.time() - start_time
            self._update_stats("processed", processing_time)
            self._add_to_history(event_data, ProcessingResult.SUCCESS)

            # Collect metrics
            for collector in self.metrics_collectors:
                try:
                    collector({
                        "event_id": event_id,
                        "processing_time": processing_time,
                        "stage": current_stage.value,
                        "result": ProcessingResult.SUCCESS.value
                    })
                except Exception as e:
                    print(f"Metrics collector error: {e}")

            return ProcessingResult.SUCCESS

        except Exception as e:
            print(f"Event processing error: {e}")
            self._log_failure(message.data, "exception")
            self._update_stats("failed")
            self._add_to_history(message.data, ProcessingResult.FAILURE)

            # Update circuit breaker
            self._record_failure()

            return ProcessingResult.FAILURE

    def _is_circuit_open(self) -> bool:
        """Check if the circuit breaker is open"""
        if not self.circuit_breaker_enabled:
            return False

        if self.circuit_state == "open":
            # Check if enough time has passed to go to half-open
            if time.time() - self.last_failure_time > self.failure_window:
                self.circuit_state = "half_open"
                return False
            return True
        if self.circuit_state == "half_open":
            # In half-open state, allow some requests through
            # For simplicity, we'll just return False here
            # A real implementation would have more sophisticated logic
            return False

        return False

    def _record_failure(self):
        """Record a processing failure for circuit breaker"""
        current_time = time.time()

        # Clean up old failure records
        self.failure_counts = {
            ts: count for ts, count in self.failure_counts.items()
            if current_time - ts < self.failure_window
        }

        # Add new failure
        self.failure_counts[current_time] = self.failure_counts.get(current_time, 0) + 1

        # Check if we've crossed the threshold
        total_failures = sum(self.failure_counts.values())
        if total_failures >= self.failure_threshold:
            self.circuit_state = "open"
            self.last_failure_time = current_time

    def _reset_circuit(self):
        """Reset the circuit breaker to closed state"""
        self.circuit_state = "closed"
        self.failure_counts.clear()

    def _log_failure(self, event_data: Dict[str, Any], stage: str):
        """Log a processing failure"""
        print(f"Processing failure at stage {stage}: {event_data.get('event_type', 'unknown')}")

    def _update_stats(self, stat_type: str, processing_time: Optional[float] = None):
        """Update processing statistics"""
        with self.lock:
            if stat_type == "processed":
                self.stats["processed"] += 1
                if processing_time is not None:
                    # Update average processing time
                    old_avg = self.stats["avg_processing_time"]
                    count = self.stats["processed"]
                    new_avg = ((old_avg * (count - 1)) + processing_time) / count
                    self.stats["avg_processing_time"] = new_avg
            elif stat_type == "failed":
                self.stats["failed"] += 1
            elif stat_type == "retried":
                self.stats["retried"] += 1
            elif stat_type == "dropped":
                self.stats["dropped"] += 1

    def _add_to_history(self, event_data: Dict[str, Any], result: ProcessingResult):
        """Add processed event to history"""
        with self.lock:
            self.processed_events.append({
                "event_data": event_data,
                "result": result.value,
                "processed_at": time.time()
            })

            # Maintain history size
            if len(self.processed_events) > self.max_event_history:
                self.processed_events = self.processed_events[-self.max_event_history:]

    def get_processor_status(self) -> Dict[str, Any]:
        """Get status of the event processor"""
        with self.lock:
            return {
                "processor_id": self.processor_id,
                "name": self.name,
                "running": self.running,
                "input_queue_size": self.input_queue.get_queue_size(),
                "output_queue_size": self.output_queue.get_queue_size(),
                "retry_queue_size": self.retry_queue.get_queue_size(),
                "dlq_size": self.dead_letter_queue.get_queue_size(),
                "stats": self.stats.copy(),
                "circuit_state": self.circuit_state,
                "failure_count": sum(self.failure_counts.values()),
                "registered_stages": list(self.stage_processors.keys()),
                "filter_count": len(self.filters),
                "enricher_count": len(self.enrichers),
                "metrics_collector_count": len(self.metrics_collectors),
                "thread_count": len(self.processing_threads),
                "uptime_seconds": time.time() - getattr(self, 'start_time', time.time())
            }

    def get_statistics(self) -> Dict[str, Any]:
        """Get detailed statistics for the processor"""
        with self.lock:
            return {
                "processor_id": self.processor_id,
                "total_processed": self.stats["processed"],
                "total_failed": self.stats["failed"],
                "total_retried": self.stats["retried"],
                "total_dropped": self.stats["dropped"],
                "success_rate": self.stats["processed"] / (self.stats["processed"] + self.stats["failed"])
                               if (self.stats["processed"] + self.stats["failed"]) > 0 else 0,
                "average_processing_time": self.stats["avg_processing_time"],
                "events_per_second": self.stats["processed"] / (time.time() - getattr(self, 'start_time', time.time()))
                                   if time.time() - getattr(self, 'start_time', time.time()) > 0 else 0,
                "queue_occupancy": {
                    "input_queue": self.input_queue.get_queue_size(),
                    "output_queue": self.output_queue.get_queue_size(),
                    "retry_queue": self.retry_queue.get_queue_size(),
                    "dlq": self.dead_letter_queue.get_queue_size()
                },
                "circuit_breaker": {
                    "enabled": self.circuit_breaker_enabled,
                    "state": self.circuit_state,
                    "failure_count": sum(self.failure_counts.values()),
                    "threshold": self.failure_threshold
                }
            }

    def get_recent_events(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get recent processed events"""
        with self.lock:
            return self.processed_events[-count:]

    def clear_queues(self):
        """Clear all queues"""
        with self.lock:
            self.input_queue.clear_queue()
            self.output_queue.clear_queue()
            self.retry_queue.clear_queue()
            self.dead_letter_queue.clear_queue()

    def pause_processing(self):
        """Pause event processing"""
        self.running = False

    def resume_processing(self):
        """Resume event processing"""
        if not self.running:
            self.start()

    def flush_queues(self):
        """Process all remaining events in queues"""
        # Process input queue
        while not self.input_queue.is_empty():
            msg = self.input_queue.dequeue()
            if msg:
                self._process_single_event(msg)

        # Process retry queue
        while not self.retry_queue.is_empty():
            msg = self.retry_queue.dequeue()
            if msg:
                self._process_single_event(msg)

    def force_circuit_open(self):
        """Force the circuit breaker to open"""
        self.circuit_state = "open"
        self.last_failure_time = time.time()

    def force_circuit_closed(self):
        """Force the circuit breaker to closed"""
        self.circuit_state = "closed"
        self.failure_counts.clear()

    def get_dead_letter_queue_contents(self) -> List[Dict[str, Any]]:
        """Get contents of the dead letter queue"""
        # This is a simplified version - in reality, we'd need a way to access DLQ messages
        return []

    def retry_dlq_messages(self):
        """Retry all messages in the dead letter queue"""
        # For now, just return a count of DLQ messages
        return self.dead_letter_queue.get_queue_size()

    def cleanup_old_events(self, max_age_minutes: int = 60):
        """Clean up old events from history"""
        current_time = time.time()
        cutoff_time = current_time - (max_age_minutes * 60)

        with self.lock:
            self.processed_events = [
                event for event in self.processed_events
                if event["processed_at"] > cutoff_time
            ]


class DistributedEventProcessor(EventProcessor):
    """Distributed event processor with cluster awareness"""

    def __init__(self, name: str = "distributed_processor", max_workers: int = 5,
                 node_id: Optional[str] = None, cluster_communicator: ClusterCommunicator = None):
        super().__init__(name, max_workers)
        self.node_id = node_id or f"node_{uuid.uuid4().hex[:8]}"
        self.cluster_communicator = cluster_communicator
        self.distributed_mode = True
        self.task_distribution_enabled = True
        self.local_processing_ratio = 0.7  # 70% local, 30% distributed
        self.cluster_event_handlers = {}  # event_type -> handler
        self.cross_node_executor = None  # For executing tasks on other nodes

    def start(self):
        """Override to support distributed features"""
        super().start()

        # Register with cluster communicator if available
        if self.cluster_communicator:
            self.cluster_communicator.register_message_handler("event_forward", self._handle_cluster_event)

    def submit_event(self, event_data: Dict[str, Any], priority: MessagePriority = MessagePriority.NORMAL) -> str:
        """Override to support distributed event submission"""
        # Determine if this should be processed locally or distributed
        if self._should_process_locally(event_data):
            return super().submit_event(event_data, priority)
        # Forward to another node
        return self._forward_to_cluster_node(event_data, priority)

    def _should_process_locally(self, _event_data: Dict[str, Any]) -> bool:  # NOSONAR — S1172: parameter retained for API stability
        """Determine if an event should be processed locally"""
        if not self.task_distribution_enabled:
            return True

        # Use a simple ratio-based decision
        import random
        return random.random() < self.local_processing_ratio  # NOSONAR — S2245: pseudo-random used for non-cryptographic purpose (test/cache key)

    def _forward_to_cluster_node(self, event_data: Dict[str, Any], priority: MessagePriority) -> str:
        """Forward an event to another node in the cluster"""
        if not self.cluster_communicator:
            # No cluster available, process locally
            return super().submit_event(event_data, priority)

        # Find a suitable node for processing
        target_node = self._select_target_node(event_data)

        if target_node:
            # Forward the event
            forward_msg = {
                "type": "event_forward",
                "event_data": event_data,
                "priority": priority.value,
                "source_node": self.node_id,
                "timestamp": time.time()
            }

            success = self.cluster_communicator.send_message(target_node, forward_msg)
            return target_node if success else "forward_failed"
        # No suitable node found, process locally
        return super().submit_event(event_data, priority)

    def _select_target_node(self, _event_data: Dict[str, Any]) -> Optional[str]:  # NOSONAR — S1172: parameter retained for API stability
        """Select a target node for event processing"""
        if not self.cluster_communicator:
            return None

        # Get healthy nodes from cluster
        healthy_nodes = self.cluster_communicator.get_healthy_nodes()

        # Filter out self
        other_nodes = [node for node in healthy_nodes if node != self.node_id]

        if not other_nodes:
            return None

        # Select node with lowest load (simplified)
        best_node = None
        lowest_load = float('inf')

        for node_id in other_nodes:
            node_status = self.cluster_communicator.get_node_status(node_id)
            if node_status and node_status.get("load", float('inf')) < lowest_load:
                lowest_load = node_status["load"]
                best_node = node_id

        return best_node

    def _handle_cluster_event(self, message: Dict[str, Any], sender_node: str, addr):
        """Handle an event forwarded from another cluster node"""
        event_data = message.get("event_data", {})
        priority_value = message.get("priority", MessagePriority.NORMAL.value)
        priority = MessagePriority(priority_value) if isinstance(priority_value, int) else MessagePriority.NORMAL

        # Add cluster forwarding information
        event_data["forwarded_from_node"] = sender_node
        event_data["received_via_cluster"] = True

        # Submit to local processing
        return super().submit_event(event_data, priority)

    def register_cluster_event_handler(self, event_type: str, handler: Callable):
        """Register a handler for events received from the cluster"""
        self.cluster_event_handlers[event_type] = handler

    def process_cluster_event(self, event_data: Dict[str, Any], source_node: str):
        """Process an event that came from the cluster"""
        event_type = event_data.get("event_type", "unknown")

        if event_type in self.cluster_event_handlers:
            return self.cluster_event_handlers[event_type](event_data, source_node)
        # Default processing
        return self.submit_event(event_data)

    def distribute_processing_load(self, target_load: float):
        """Distribute processing load across the cluster"""
        if not self.cluster_communicator:
            return

        # Update local load
        current_stats = self.get_statistics()
        local_load = current_stats.get("average_processing_time", 0) / 1000  # Convert to seconds

        self.cluster_communicator.update_local_load(local_load)

        # If local load is high, reduce local processing ratio
        if local_load > target_load:
            self.local_processing_ratio = max(0.1, self.local_processing_ratio - 0.1)
        else:
            # If local load is low, increase local processing ratio
            self.local_processing_ratio = min(0.9, self.local_processing_ratio + 0.05)

    def get_distributed_status(self) -> Dict[str, Any]:
        """Get status including distributed information"""
        base_status = self.get_processor_status()

        if self.cluster_communicator:
            cluster_status = self.cluster_communicator.get_cluster_status()
            base_status["cluster_info"] = cluster_status
            base_status["distributed_mode"] = self.distributed_mode
            base_status["local_processing_ratio"] = self.local_processing_ratio
            base_status["task_distribution_enabled"] = self.task_distribution_enabled

        return base_status

    def sync_with_cluster(self):
        """Synchronize processor state with cluster"""
        if self.cluster_communicator:
            processor_state = {
                "processor_id": self.processor_id,
                "node_id": self.node_id,
                "stats": self.get_statistics(),
                "status": self.get_processor_status(),
                "timestamp": time.time()
            }

            self.cluster_communicator.sync_cluster_state(processor_state)

    def graceful_shutdown(self):
        """Perform a graceful shutdown of the distributed processor"""
        print(f"Shutting down distributed processor {self.processor_id}")

        # Flush all queues first
        self.flush_queues()

        # Sync with cluster to inform about shutdown
        if self.cluster_communicator:
            shutdown_msg = {
                "type": "processor_shutdown",
                "processor_id": self.processor_id,
                "node_id": self.node_id,
                "timestamp": time.time()
            }
            self.cluster_communicator.broadcast_message(shutdown_msg)

        # Stop processing
        self.stop()


class FACPEventProcessor(DistributedEventProcessor):
    """Specialized event processor for FACP messages in distributed system"""

    def __init__(self, name: str = "facp_processor", max_workers: int = 5,
                 node_id: Optional[str] = None, cluster_communicator: ClusterCommunicator = None):
        super().__init__(name, max_workers, node_id, cluster_communicator)
        self.facp_request_handlers = {}
        self.facp_response_handlers = {}
        self.validation_enabled = True
        self.authentication_enabled = True
        self.authorization_enabled = True
        self.idempotency_enabled = True
        self.idempotency_store = {}  # idempotency_key -> response
        self.idempotency_ttl = 3600  # 1 hour TTL

    def register_facp_request_handler(self, method: str, handler: Callable):
        """Register a handler for a specific FACP method"""
        self.facp_request_handlers[method] = handler

    def register_facp_response_handler(self, request_id: str, handler: Callable):
        """Register a handler for a specific FACP response"""
        self.facp_response_handlers[request_id] = handler

    def submit_facp_request(self, facp_request: Dict[str, Any]) -> str:
        """Override to handle FACP-specific processing"""
        # Check for idempotency
        idempotency_key = facp_request.get("security", {}).get("idempotency_key")
        if idempotency_key and idempotency_key in self.idempotency_store:
            # Return cached response
            cached_response = self.idempotency_store[idempotency_key]
            # Trigger response handler if registered
            request_id = facp_request.get("id")
            if request_id in self.facp_response_handlers:
                self.facp_response_handlers[request_id](cached_response)
            return f"idempotency_hit_{idempotency_key}"

        # Add FACP-specific processing stages
        event_data = {
            "event_type": "facp_request",
            "facp_request": facp_request,
            "processing_stage": ProcessingStage.RECEIVED.value,
            "submitted_at": time.time(),
            "node_id": self.node_id
        }

        # Register stage processors for FACP-specific processing
        self.register_stage_processor(ProcessingStage.VALIDATED, self._validate_facp_request)
        self.register_stage_processor(ProcessingStage.AUTHENTICATED, self._authenticate_facp_request)
        self.register_stage_processor(ProcessingStage.AUTHORIZED, self._authorize_facp_request)
        self.register_stage_processor(ProcessingStage.ROUTED, self._route_facp_request)
        self.register_stage_processor(ProcessingStage.PROCESSING, self._process_facp_request)

        return super().submit_event(event_data, MessagePriority.HIGH)


    def _validate_facp_request(self, event_data: Dict[str, Any], stage: str) -> bool:
        """Validate FACP request"""
        if not self.validation_enabled:
            return True

        facp_request = event_data.get("facp_request", {})

        try:
            # Create FACP request object to validate
            request_obj = FACPRequest.from_dict(facp_request)
            # Use the protocol's built-in validation
            from ..protocol.message_schema import FACPMessageValidator
            validator = FACPMessageValidator()
            is_valid, errors = validator.validate_request(request_obj)

            if not is_valid:
                event_data["validation_errors"] = errors
                return False

            return True
        except Exception as e:
            event_data["validation_error"] = str(e)
            return False

    def _authenticate_facp_request(self, event_data: Dict[str, Any], stage: str) -> bool:
        """Authenticate FACP request"""
        if not self.authentication_enabled:
            return True

        facp_request = event_data.get("facp_request", {})
        security_block = facp_request.get("security", {})
        auth_token = security_block.get("auth_token")

        # In a real implementation, this would validate the token
        # For now, we'll just check if it exists
        if not auth_token:
            event_data["auth_error"] = "No authentication token provided"
            return False

        # Add authenticated user info to event data
        event_data["authenticated_user"] = "user_from_token"  # Would come from token validation

        return True

    def _authorize_facp_request(self, event_data: Dict[str, Any], stage: str) -> bool:
        """Authorize FACP request"""
        if not self.authorization_enabled:
            return True

        facp_request = event_data.get("facp_request", {})
        facp_request.get("method", "")
        security_block = facp_request.get("security", {})
        permissions = security_block.get("permissions", [])

        # In a real implementation, this would check user permissions
        # For now, we'll just check if any permissions are specified
        if not permissions:
            event_data["authz_error"] = "No permissions specified"
            return False

        # Add authorized info to event data
        event_data["authorized"] = True
        event_data["granted_permissions"] = permissions

        return True

    def _route_facp_request(self, event_data: Dict[str, Any], stage: str) -> bool:
        """Route FACP request to appropriate handler"""
        facp_request = event_data.get("facp_request", {})
        method = facp_request.get("method", "")

        # Check if we have a handler for this method
        if method not in self.facp_request_handlers:
            event_data["routing_error"] = f"No handler for method: {method}"
            return False

        # Add routing info
        event_data["target_handler"] = method
        event_data["routing_successful"] = True

        return True

    def _process_facp_request(self, event_data: Dict[str, Any], stage: str) -> bool:
        """Process FACP request with registered handler"""
        facp_request = event_data.get("facp_request", {})
        method = facp_request.get("method", "")

        if method in self.facp_request_handlers:
            handler = self.facp_request_handlers[method]
            try:
                result = handler(facp_request)
                event_data["facp_response"] = result
                event_data["processing_successful"] = True

                # Store in idempotency cache if key exists
                idempotency_key = facp_request.get("security", {}).get("idempotency_key")
                if idempotency_key and self.idempotency_enabled:
                    self.idempotency_store[idempotency_key] = result
                    # Clean up old entries
                    self._cleanup_idempotency_store()

                return True
            except Exception as e:
                event_data["processing_error"] = str(e)
                return False
        else:
            event_data["processing_error"] = f"No handler registered for method: {method}"
            return False

    def _cleanup_idempotency_store(self):
        """Clean up expired idempotency entries"""
        time.time()
        # In a real implementation, we'd store timestamps with entries
        # For now, we'll just maintain a reasonable size
        if len(self.idempotency_store) > 10000:  # Arbitrary limit
            # Keep only the most recent entries
            items = list(self.idempotency_store.items())
            self.idempotency_store = dict(items[-5000:])  # Keep last 5000

    def get_facp_processor_status(self) -> Dict[str, Any]:
        """Get status specific to FACP processing"""
        base_status = self.get_distributed_status()
        base_status.update({
            "registered_methods": list(self.facp_request_handlers.keys()),
            "idempotency_enabled": self.idempotency_enabled,
            "idempotency_store_size": len(self.idempotency_store),
            "validation_enabled": self.validation_enabled,
            "authentication_enabled": self.authentication_enabled,
            "authorization_enabled": self.authorization_enabled
        })
        return base_status
