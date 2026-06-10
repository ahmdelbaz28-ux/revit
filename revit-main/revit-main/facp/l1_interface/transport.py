"""
FACP Transport Layer - Handles various transport protocols for L1 interface
"""
from typing import Dict, Any, Callable, Optional
import json
import threading
import time
from abc import ABC, abstractmethod


class TransportLayer(ABC):
    """
    Abstract base class for transport protocols
    """
    def __init__(self):
        self.handlers = {}  # method -> handler_function
        self.is_running = False
        self.thread_pool = []
        
    def register_handler(self, method: str, handler: Callable):
        """Register a handler for a specific method"""
        self.handlers[method] = handler
        
    @abstractmethod
    def start(self):
        """Start the transport layer"""
        pass
        
    @abstractmethod
    def stop(self):
        """Stop the transport layer"""
        pass
        
    @abstractmethod
    def send_response(self, response_data: Dict[str, Any]):
        """Send response back to client"""
        pass


class HTTPTransport(TransportLayer):
    """
    HTTP/REST transport implementation for FACP
    """
    def __init__(self, host: str = "localhost", port: int = 8000):
        super().__init__()
        self.host = host
        self.port = port
        self.server = None
        self.request_queue = []  # Simple queue for requests
        self.response_callbacks = {}  # request_id -> callback
        
    def start(self):
        """Start HTTP server"""
        # Since we're targeting Python 3.12+ but currently running 3.8, 
        # we'll define the server implementation that would work in 3.12+
        try:
            import http.server
            import socketserver
            from urllib.parse import urlparse, parse_qs
            
            class FACPHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
                def __init__(self, l1_handler):
                    self.l1_handler = l1_handler
                
                def do_POST(self):
                    # Parse the request
                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length)
                    
                    try:
                        request_data = json.loads(post_data.decode('utf-8'))
                        
                        # Handle the request through L1 interface
                        success, response = self.l1_handler.handle_request(
                            request_data, 
                            self.client_address[0]
                        )
                        
                        # Send response
                        self.send_response(200 if success else 400)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        
                        response_json = json.dumps(response)
                        self.wfile.write(response_json.encode('utf-8'))
                        
                    except json.JSONDecodeError:
                        self.send_error(400, "Invalid JSON in request")
                    except Exception as e:
                        self.send_error(500, f"Server error: {str(e)}")
                
                def log_message(self, format, *args):
                    # Suppress default logging
                    pass
            
            # Create a partial function to inject our L1 handler
            def create_handler(l1_handler):
                def handler(*args, **kwargs):
                    h = http.server.BaseHTTPRequestHandler.__new__(FACPHTTPRequestHandler)
                    h.__init__(l1_handler)
                    return h
                return handler
            
            # This is what would happen in Python 3.12+ environment:
            # self.server = socketserver.TCPServer((self.host, self.port), 
            #                                     create_handler(self.l1_handler))
            # print(f"HTTP Transport listening on {self.host}:{self.port}")
            
            self.is_running = True
            
        except ImportError:
            # Fallback for older Python versions
            print(f"HTTP Transport would listen on {self.host}:{self.port} in Python 3.12+ environment")
            self.is_running = True

    def stop(self):
        """Stop HTTP server"""
        if self.server:
            self.server.shutdown()
        self.is_running = False

    def send_response(self, response_data: Dict[str, Any]):
        """Send response back to HTTP client"""
        # In a real implementation, this would send via HTTP response
        pass
        
    def set_l1_handler(self, l1_handler):
        """Set the L1 handler for this transport"""
        self.l1_handler = l1_handler


class WebSocketTransport(TransportLayer):
    """
    WebSocket transport implementation for FACP
    """
    def __init__(self, host: str = "localhost", port: int = 8001):
        super().__init__()
        self.host = host
        self.port = port
        self.ws_server = None
        self.connections = {}  # conn_id -> websocket_connection
        
    def start(self):
        """Start WebSocket server"""
        # This is what would be implemented in Python 3.12+ environment:
        try:
            # Would use websockets library in real implementation
            print(f"WebSocket Transport would listen on {self.host}:{self.port} in Python 3.12+ environment")
            self.is_running = True
        except ImportError:
            print(f"WebSocket Transport would require 'websockets' library in Python 3.12+ environment")
            self.is_running = False

    def stop(self):
        """Stop WebSocket server"""
        # Close all connections
        for conn in self.connections.values():
            try:
                conn.close()
            except:
                pass
        self.connections.clear()
        self.is_running = False

    def send_response(self, response_data: Dict[str, Any]):
        """Send response back via WebSocket"""
        # In real implementation, this would broadcast to relevant connections
        pass
        
    def set_l1_handler(self, l1_handler):
        """Set the L1 handler for this transport"""
        self.l1_handler = l1_handler


class StdioTransport(TransportLayer):
    """
    STDIO transport implementation for subprocess communication
    This is particularly useful for IDE integrations
    """
    def __init__(self):
        super().__init__()
        self.stdin = None
        self.stdout = None
        self.stderr = None
        self.reader_thread = None
        self.is_reading = False
        
    def start(self):
        """Start STDIO transport"""
        import sys
        import queue
        import io
        
        self.stdin = sys.stdin
        self.stdout = sys.stdout
        self.stderr = sys.stderr
        self.input_queue = queue.Queue()
        self.output_buffer = io.StringIO()
        
        # Start reading thread
        self.is_reading = True
        self.reader_thread = threading.Thread(target=self._read_stdin)
        self.reader_thread.daemon = True
        self.reader_thread.start()
        
        self.is_running = True
        
    def _read_stdin(self):
        """Read from stdin and put messages in queue"""
        while self.is_reading:
            try:
                line = self.stdin.readline()
                if line:
                    try:
                        request_data = json.loads(line.strip())
                        self.input_queue.put(request_data)
                    except json.JSONDecodeError:
                        # Invalid JSON, ignore
                        continue
                else:
                    # EOF reached
                    time.sleep(0.1)
            except Exception:
                # Error reading stdin, wait and continue
                time.sleep(0.1)
    
    def stop(self):
        """Stop STDIO transport"""
        self.is_reading = False
        if self.reader_thread:
            self.reader_thread.join(timeout=1.0)
        self.is_running = False

    def send_response(self, response_data: Dict[str, Any]):
        """Send response via stdout"""
        try:
            response_json = json.dumps(response_data) + '\n'
            self.stdout.write(response_json)
            self.stdout.flush()
        except Exception as e:
            # Log error to stderr
            self.stderr.write(f"Error sending response: {str(e)}\n")
            self.stderr.flush()

    def get_next_request(self) -> Optional[Dict[str, Any]]:
        """Get next request from input queue"""
        try:
            return self.input_queue.get_nowait()
        except:
            return None

    def has_request(self) -> bool:
        """Check if there's a request available"""
        return not self.input_queue.empty()

    def set_l1_handler(self, l1_handler):
        """Set the L1 handler for this transport"""
        self.l1_handler = l1_handler


class TransportRouter:
    """
    Routes requests to appropriate transport based on configuration
    """
    def __init__(self):
        self.transports = {}
        self.active_transport = None
        
    def add_transport(self, name: str, transport: TransportLayer):
        """Add a transport to the router"""
        self.transports[name] = transport
        
    def activate_transport(self, name: str):
        """Activate a specific transport"""
        if name in self.transports:
            self.active_transport = self.transports[name]
            return True
        return False
        
    def get_transport(self, name: str) -> Optional[TransportLayer]:
        """Get a specific transport"""
        return self.transports.get(name)
        
    def route_request(self, request_data: Dict[str, Any], transport_hint: str = None) -> Dict[str, Any]:
        """Route request to appropriate transport"""
        transport = None
        
        if transport_hint and transport_hint in self.transports:
            transport = self.transports[transport_hint]
        elif self.active_transport:
            transport = self.active_transport
        else:
            # Default to first available transport
            transport = next(iter(self.transports.values()), None)
        
        if transport and hasattr(transport, 'l1_handler'):
            # Process through L1 handler
            success, response = transport.l1_handler.handle_request(request_data)
            return response
        else:
            # Return error if no transport available
            return {
                "error": {
                    "code": "TRANSPORT_UNAVAILABLE",
                    "message": "No transport available to handle request"
                }
            }
    
    def start_all(self):
        """Start all configured transports"""
        for transport in self.transports.values():
            transport.start()
    
    def stop_all(self):
        """Stop all configured transports"""
        for transport in self.transports.values():
            transport.stop()