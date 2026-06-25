"""
Message Queue for Event Bus in Distributed FACP System
"""
import queue
import threading
import time
import uuid
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class MessagePriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class MessageStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    DELAYED = "delayed"


class Message:
    """
    Represents a message in the distributed FACP system
    """
    def __init__(self, topic: str, data: Dict[str, Any], priority: MessagePriority = MessagePriority.NORMAL,
                 correlation_id: str = None, reply_to: str = None, headers: Dict[str, str] = None):
        self.id = str(uuid.uuid4())
        self.topic = topic
        self.data = data
        self.priority = priority
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.reply_to = reply_to
        self.headers = headers or {}
        self.created_at = time.time()
        self.processed_at = None
        self.status = MessageStatus.QUEUED
        self.attempts = 0
        self.max_attempts = 3
        self.delay_until = None  # Timestamp for delayed messages
        self.node_source = self.headers.get("source_node", "unknown")
        self.node_target = self.headers.get("target_node", "all")

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary representation"""
        return {
            "id": self.id,
            "topic": self.topic,
            "data": self.data,
            "priority": self.priority.value,
            "correlation_id": self.correlation_id,
            "reply_to": self.reply_to,
            "headers": self.headers,
            "created_at": self.created_at,
            "processed_at": self.processed_at,
            "status": self.status.value,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "delay_until": self.delay_until,
            "node_source": self.node_source,
            "node_target": self.node_target
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Create message from dictionary representation"""
        msg = cls(
            topic=data["topic"],
            data=data["data"],
            priority=MessagePriority(data["priority"]),
            correlation_id=data["correlation_id"],
            reply_to=data.get("reply_to"),
            headers=data.get("headers", {})
        )
        msg.id = data["id"]
        msg.created_at = data["created_at"]
        msg.processed_at = data.get("processed_at")
        msg.status = MessageStatus(data["status"])
        msg.attempts = data.get("attempts", 0)
        msg.max_attempts = data.get("max_attempts", 3)
        msg.delay_until = data.get("delay_until")
        return msg


class MessageQueue:
    """
    Thread-safe message queue for the distributed system
    """
    def __init__(self, name: str, max_size: int = 10000):
        self.name = name
        self.max_size = max_size
        self.queue = queue.PriorityQueue(maxsize=max_size)
        self.messages = {}  # message_id -> Message object
        self.topic_queues = {}  # topic -> queue.PriorityQueue
        self.subscribers = {}  # topic -> [callbacks]
        self.lock = threading.Lock()
        self.stats = {
            "enqueued": 0,
            "dequeued": 0,
            "processed": 0,
            "failed": 0,
            "retried": 0
        }
        self.running = True
        self.message_ttl = 3600  # 1 hour default TTL

    def enqueue(self, message: Message) -> bool:
        """
        Add a message to the queue
        """
        try:
            with self.lock:
                if self.queue.qsize() >= self.max_size:
                    return False  # Queue is full

                # Add to main queue with priority (negative for reverse priority)
                priority_value = -message.priority.value
                self.queue.put((priority_value, time.time(), message.id))

                # Add to topic-specific queue as well
                if message.topic not in self.topic_queues:
                    self.topic_queues[message.topic] = queue.PriorityQueue(maxsize=self.max_size)
                self.topic_queues[message.topic].put((priority_value, time.time(), message.id))

                # Store message reference
                self.messages[message.id] = message

                self.stats["enqueued"] += 1
                return True
        except queue.Full:
            return False

    def dequeue(self, topic_filter: str = None) -> Optional[Message]:
        """
        Remove and return a message from the queue
        """
        try:
            with self.lock:
                if topic_filter:
                    if topic_filter not in self.topic_queues:
                        return None
                    q = self.topic_queues[topic_filter]
                else:
                    q = self.queue

                if q.empty():
                    return None

                priority, timestamp, message_id = q.get_nowait()

                if message_id in self.messages:
                    message = self.messages[message_id]

                    # Update message status
                    message.status = MessageStatus.PROCESSING
                    message.processed_at = time.time()

                    self.stats["dequeued"] += 1
                    return message
                else:
                    # Message was removed from messages dict, put it back in queue
                    q.put((priority, timestamp, message_id))
                    return None
        except queue.Empty:
            return None

    def subscribe(self, topic: str, callback: Callable[[Message], None]):
        """
        Subscribe to messages on a specific topic
        """
        with self.lock:
            if topic not in self.subscribers:
                self.subscribers[topic] = []
            self.subscribers[topic].append(callback)

    def publish(self, message: Message) -> bool:
        """
        Publish a message to the appropriate topic
        """
        success = self.enqueue(message)

        # Notify subscribers if any
        if success and message.topic in self.subscribers:
            for callback in self.subscribers[message.topic]:
                try:
                    # Run callback in a separate thread to avoid blocking
                    threading.Thread(target=callback, args=(message,), daemon=True).start()
                except Exception as e:
                    print(f"Error in subscriber callback: {e}")

        return success

    def acknowledge(self, message_id: str) -> bool:
        """
        Acknowledge successful processing of a message
        """
        with self.lock:
            if message_id in self.messages:
                message = self.messages[message_id]
                message.status = MessageStatus.PROCESSED
                del self.messages[message_id]  # Remove from storage after processing
                self.stats["processed"] += 1
                return True
            return False

    def nack(self, message_id: str, retry: bool = True) -> bool:
        """
        Negative acknowledgment - message failed processing
        """
        with self.lock:
            if message_id not in self.messages:
                return False

            message = self.messages[message_id]
            message.status = MessageStatus.FAILED
            message.attempts += 1

            if retry and message.attempts < message.max_attempts:
                # Retry the message
                message.status = MessageStatus.QUEUED
                self.stats["retried"] += 1
                # Re-add to queue
                priority_value = -message.priority.value
                self.queue.put((priority_value, time.time(), message.id))
                if message.topic in self.topic_queues:
                    self.topic_queues[message.topic].put((priority_value, time.time(), message.id))
                return True
            else:
                # Max attempts reached, move to dead letter queue or discard
                del self.messages[message_id]
                self.stats["failed"] += 1
                return False

    def get_message(self, message_id: str) -> Optional[Message]:
        """
        Get a message by ID
        """
        with self.lock:
            return self.messages.get(message_id)

    def get_queue_size(self) -> int:
        """
        Get the current size of the main queue
        """
        return self.queue.qsize()

    def get_topic_size(self, topic: str) -> int:
        """
        Get the size of a specific topic queue
        """
        if topic in self.topic_queues:
            return self.topic_queues[topic].qsize()
        return 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Get queue statistics
        """
        with self.lock:
            return self.stats.copy()

    def get_messages_by_topic(self, topic: str) -> List[Message]:
        """
        Get all messages for a specific topic
        """
        with self.lock:
            return [msg for msg in self.messages.values() if msg.topic == topic]

    def cleanup_expired_messages(self):
        """
        Remove expired messages based on TTL
        """
        current_time = time.time()
        expired_messages = []

        with self.lock:
            for msg_id, message in self.messages.items():
                if current_time - message.created_at > self.message_ttl:
                    expired_messages.append(msg_id)

            for msg_id in expired_messages:
                del self.messages[msg_id]

        return len(expired_messages)

    def clear_queue(self):
        """
        Clear all messages from the queue
        """
        with self.lock:
            self.queue.queue.clear()
            for topic_queue in self.topic_queues.values():
                topic_queue.queue.clear()
            self.messages.clear()
            # Reset stats
            self.stats = dict.fromkeys(self.stats.keys(), 0)

    def pause(self):
        """
        Pause the queue (stop accepting new messages)
        """
        self.running = False

    def resume(self):
        """
        Resume the queue (start accepting new messages)
        """
        self.running = True

    def is_empty(self) -> bool:
        """
        Check if the main queue is empty
        """
        return self.queue.empty()

    def peek(self) -> Optional[Message]:
        """
        Peek at the next message without removing it (not thread-safe for modification)
        """
        with self.lock:
            if not self.queue.empty():
                # Get item without removing from queue
                items = list(self.queue.queue)
                if items:
                    _, _, message_id = items[0]  # Get highest priority item
                    return self.messages.get(message_id)
        return None


class PriorityQueue(MessageQueue):
    """
    Priority-based message queue with additional features
    """
    def __init__(self, name: str, max_size: int = 10000):
        super().__init__(name, max_size)
        self.priority_queues = {  # Separate queues for each priority level
            MessagePriority.LOW: queue.PriorityQueue(maxsize=max_size),
            MessagePriority.NORMAL: queue.PriorityQueue(maxsize=max_size),
            MessagePriority.HIGH: queue.PriorityQueue(maxsize=max_size),
            MessagePriority.CRITICAL: queue.PriorityQueue(maxsize=max_size)
        }

    def enqueue(self, message: Message) -> bool:
        """
        Add a message to the appropriate priority queue
        """
        try:
            with self.lock:
                if self.queue.qsize() >= self.max_size:
                    return False

                # Add to both main queue and priority-specific queue
                priority_value = -message.priority.value
                timestamp = time.time()

                # Add to main queue
                self.queue.put((priority_value, timestamp, message.id))

                # Add to priority-specific queue
                self.priority_queues[message.priority].put((priority_value, timestamp, message.id))

                # Add to topic queue
                if message.topic not in self.topic_queues:
                    self.topic_queues[message.topic] = queue.PriorityQueue(maxsize=self.max_size)
                self.topic_queues[message.topic].put((priority_value, timestamp, message.id))

                # Store message reference
                self.messages[message.id] = message

                self.stats["enqueued"] += 1
                return True
        except queue.Full:
            return False

    def dequeue_by_priority(self, priority: MessagePriority) -> Optional[Message]:
        """
        Dequeue a message with a specific priority
        """
        try:
            with self.lock:
                q = self.priority_queues[priority]
                if q.empty():
                    return None

                priority_val, timestamp, message_id = q.get_nowait()

                if message_id in self.messages:
                    message = self.messages[message_id]
                    message.status = MessageStatus.PROCESSING
                    message.processed_at = time.time()

                    self.stats["dequeued"] += 1
                    return message
                else:
                    q.put((priority_val, timestamp, message_id))
                    return None
        except queue.Empty:
            return None

    def get_priority_stats(self) -> Dict[str, int]:
        """
        Get statistics broken down by priority
        """
        with self.lock:
            return {
                "critical": self.priority_queues[MessagePriority.CRITICAL].qsize(),
                "high": self.priority_queues[MessagePriority.HIGH].qsize(),
                "normal": self.priority_queues[MessagePriority.NORMAL].qsize(),
                "low": self.priority_queues[MessagePriority.LOW].qsize()
            }


class DistributedMessageQueue(MessageQueue):
    """
    Distributed message queue that can synchronize with other nodes
    """
    def __init__(self, name: str, max_size: int = 10000, node_id: str = None):
        super().__init__(name, max_size)
        self.node_id = node_id or f"node_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.cluster_sync_callback = None
        self.distributed_messages = {}  # Messages from other nodes
        self.message_replication_factor = 2  # How many nodes to replicate to

    def set_cluster_sync_callback(self, callback):
        """
        Set callback for cluster synchronization
        """
        self.cluster_sync_callback = callback

    def enqueue(self, message: Message) -> bool:
        """
        Override to support distributed enqueue
        """
        success = super().enqueue(message)

        # Replicate to other nodes if callback is available
        if success and self.cluster_sync_callback:
            self.cluster_sync_callback({
                "action": "message_enqueued",
                "message": message.to_dict(),
                "node_id": self.node_id,
                "timestamp": time.time()
            })

        return success

    def sync_with_cluster(self, cluster_messages: List[Dict[str, Any]]):
        """
        Sync messages with cluster
        """
        for msg_data in cluster_messages:
            if msg_data["node_source"] != self.node_id:  # Don't process our own messages
                message = Message.from_dict(msg_data)
                # Add to our distributed messages
                self.distributed_messages[message.id] = message

    def get_local_and_distributed_messages(self, topic: str = None) -> List[Message]:
        """
        Get both local and distributed messages
        """
        local_msgs = self.get_messages_by_topic(topic) if topic else list(self.messages.values())
        distributed_msgs = [msg for msg in self.distributed_messages.values()
                           if topic is None or msg.topic == topic]
        return local_msgs + distributed_msgs
