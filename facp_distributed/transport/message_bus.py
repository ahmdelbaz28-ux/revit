"""
Message Bus Transport for Distributed FACP System
"""
import asyncio
import json
import logging
import threading
import time
from abc import abstractmethod
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)

from .http_transport import TransportLayer


class MessageBusTransport(TransportLayer):
    """
    Abstract base class for message bus transports
    """
    def __init__(self, node_type: str = "l2_orchestrator"):
        super().__init__()
        self.node_type = node_type
        self.subscribers = {}  # topic -> [handlers]
        self.publisher = None
        self.consumer = None
        self.topics = set()

    @abstractmethod
    def connect(self):
        """Connect to the message bus"""
        raise NotImplementedError("Subclasses must implement connect()")

    @abstractmethod
    def disconnect(self):
        """Disconnect from the message bus"""
        raise NotImplementedError("Subclasses must implement disconnect()")

    @abstractmethod
    def publish(self, topic: str, message: Dict[str, Any]):
        """Publish a message to a topic"""
        raise NotImplementedError("Subclasses must implement publish()")

    @abstractmethod
    def subscribe(self, topic: str, handler: Callable):
        """Subscribe to a topic with a handler"""
        raise NotImplementedError("Subclasses must implement subscribe()")

    def send_request(self, request_data: Dict[str, Any], target_node: str = None) -> Dict[str, Any]:
        """
        Send request via message bus
        target_node can specify routing information
        """
        # Default to a general request topic
        topic = "facp.requests"
        if target_node:
            topic = f"facp.requests.{target_node}"

        # Add routing information
        request_data["routing"] = {
            "source_node": self.node_id,
            "source_type": self.node_type,
            "target_node": target_node,
            "timestamp": time.time()
        }

        try:
            self.publish(topic, request_data)

            # In a real implementation, we'd wait for a response
            # For now, return a success indicator
            return {
                "protocol": "FACP/1.1",
                "id": request_data.get("id", "unknown"),
                "status": "success",
                "result": {"published": True, "topic": topic},
                "trace": {
                    "node_id": self.node_id,
                    "node_type": self.node_type,
                    "execution_path": [self.node_type],
                    "latency_ms": 0
                }
            }
        except Exception as e:
            return {
                "protocol": "FACP/1.1",
                "id": request_data.get("id", "unknown"),
                "status": "error",
                "error": {
                    "code": "MESSAGE_BUS_ERROR",
                    "message": str(e)
                },
                "trace": {
                    "node_id": self.node_id,
                    "node_type": self.node_type,
                    "execution_path": [self.node_type],
                    "latency_ms": 0
                }
            }


class RedisMessageBus(MessageBusTransport):
    """
    Redis-based message bus implementation
    """
    def __init__(self, host: str = "localhost", port: int = 6379, node_type: str = "l2_orchestrator"):
        super().__init__(node_type)
        self.host = host
        self.port = port
        self.redis_client = None
        self.pubsub = None
        self.running = False

    def connect(self):
        """Connect to Redis"""
        try:
            import redis
            self.redis_client = redis.Redis(host=self.host, port=self.port, decode_responses=True)

            # Test connection
            self.redis_client.ping()
            print(f"Connected to Redis at {self.host}:{self.port}")

            # Setup pubsub
            self.pubsub = self.redis_client.pubsub()

        except ImportError:
            print("Redis library not available. Install with 'pip install redis'")
            raise
        except Exception as e:
            print(f"Failed to connect to Redis: {e}")
            raise

    def disconnect(self):
        """Disconnect from Redis"""
        if self.pubsub:
            self.pubsub.close()
        if self.redis_client:
            self.redis_client.close()
        self.running = False

    def publish(self, topic: str, message: Dict[str, Any]):
        """Publish a message to Redis channel"""
        message_str = json.dumps(message)
        self.redis_client.publish(topic, message_str)

    def subscribe(self, topic: str, handler: Callable):
        """Subscribe to a Redis channel"""
        if not self.pubsub:
            raise RuntimeError("Not connected to Redis")

        self.pubsub.subscribe(topic)

        def message_handler():
            for message in self.pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        # Call the handler with the message data
                        if asyncio.iscoroutinefunction(handler):
                            # For async handlers, we'd need to run in an event loop
                            # This is simplified for now
                            handler(data)
                        else:
                            handler(data)
                    except json.JSONDecodeError:
                        print(f"Failed to decode message from {topic}")
                    except Exception as e:
                        print(f"Error in message handler: {e}")

        # Start message handler in a thread
        handler_thread = threading.Thread(target=message_handler, daemon=True)
        handler_thread.start()

        # Add to subscribers
        if topic not in self.subscribers:
            self.subscribers[topic] = []
        self.subscribers[topic].append(handler)

    def start(self):
        """Start the Redis message bus"""
        try:
            self.connect()
            self.running = True
            self.is_running = True
            print(f"Redis Message Bus started for node {self.node_id}")
        except Exception as e:
            print(f"Failed to start Redis Message Bus: {e}")

    def stop(self):
        """Stop the Redis message bus"""
        self.disconnect()
        self.is_running = False
        self.running = False


class NATSMessageBus(MessageBusTransport):
    """
    NATS-based message bus implementation
    """
    def __init__(self, servers: list = None, node_type: str = "l2_orchestrator"):
        super().__init__(node_type)
        self.servers = servers or ["nats://localhost:4222"]
        self.nc = None  # NATS connection
        self.running = False

    def connect(self):
        """Connect to NATS"""
        try:
            import asyncio

            import nats

            async def connect_async():
                self.nc = await nats.connect(servers=self.servers)
                print(f"Connected to NATS at {self.servers}")

            # Run the async connection
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(connect_async())
            loop.close()

        except ImportError:
            print("NATS library not available. Install with 'pip install nats-py'")
            raise
        except Exception as e:
            print(f"Failed to connect to NATS: {e}")
            raise

    def disconnect(self):
        """Disconnect from NATS"""
        if self.nc:
            asyncio.run(self.nc.close())
        self.running = False

    async def async_publish(self, topic: str, message: Dict[str, Any]):
        """Async publish to NATS"""
        if not self.nc:
            raise RuntimeError("Not connected to NATS")

        message_str = json.dumps(message)
        await self.nc.publish(topic, message_str.encode())

    def publish(self, topic: str, message: Dict[str, Any]):
        """Publish a message to NATS subject"""
        # Run the async publish method
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.async_publish(topic, message))
        loop.close()

    def subscribe(self, topic: str, handler: Callable):
        """Subscribe to a NATS subject"""
        if not self.nc:
            raise RuntimeError("Not connected to NATS")

        async def message_handler(msg):
            try:
                data = json.loads(msg.data.decode())
                # Call the handler with the message data
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except json.JSONDecodeError:
                print(f"Failed to decode message from {topic}")
            except Exception as e:
                print(f"Error in message handler: {e}")

        # Subscribe to the subject
        subscription = self.nc.subscribe(topic, cb=message_handler)

        # Add to subscribers
        if topic not in self.subscribers:
            self.subscribers[topic] = []
        self.subscribers[topic].append(handler)

        return subscription

    def start(self):
        """Start the NATS message bus"""
        try:
            self.connect()
            self.running = True
            self.is_running = True
            print(f"NATS Message Bus started for node {self.node_id}")
        except Exception as e:
            print(f"Failed to start NATS Message Bus: {e}")

    def stop(self):
        """Stop the NATS message bus"""
        self.disconnect()
        self.is_running = False
        self.running = False


class InMemoryMessageBus(MessageBusTransport):
    """
    In-memory message bus for testing and development
    """
    def __init__(self, node_type: str = "l2_orchestrator"):
        super().__init__(node_type)
        self.channels = {}  # topic -> queue of messages
        self.channel_handlers = {}  # topic -> [handlers]
        self.running = False
        self.message_queues = {}  # topic -> list of messages

    def connect(self):
        """Initialize in-memory message bus"""
        print("Initialized in-memory message bus")

    def disconnect(self):
        """Cleanup in-memory message bus"""
        self.channels.clear()
        self.channel_handlers.clear()
        self.message_queues.clear()
        self.running = False

    def publish(self, topic: str, message: Dict[str, Any]):
        """Publish a message to in-memory channel"""
        if topic not in self.message_queues:
            self.message_queues[topic] = []

        self.message_queues[topic].append(message)

        # Trigger handlers if any
        if topic in self.channel_handlers:
            for handler in self.channel_handlers[topic]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        # For async handlers, we'd need an event loop
                        # This is simplified for now
                        handler(message)
                    else:
                        handler(message)
                except Exception as e:
                    print(f"Error in handler for topic {topic}: {e}")

    def subscribe(self, topic: str, handler: Callable):
        """Subscribe to a topic"""
        if topic not in self.channel_handlers:
            self.channel_handlers[topic] = []
        self.channel_handlers[topic].append(handler)

        # Process any existing messages in the queue
        if topic in self.message_queues:
            for message in self.message_queues[topic]:
                try:
                    handler(message)
                except Exception as e:
                    print(f"Error processing existing message for topic {topic}: {e}")

    def start(self):
        """Start the in-memory message bus"""
        self.connect()
        self.running = True
        self.is_running = True
        print(f"In-memory Message Bus started for node {self.node_id}")

    def stop(self):
        """Stop the in-memory message bus"""
        self.disconnect()
        self.is_running = False
        self.running = False

    def get_topic_messages(self, topic: str) -> list:
        """Get messages from a specific topic (for testing)"""
        return self.message_queues.get(topic, [])
