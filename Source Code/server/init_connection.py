import socket
import threading
import logging
import time
import hashlib
import os
from send_screen import SendScreen
from receive_events import ReceiveEvents

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("remote_desktop_server.log"),
        logging.StreamHandler()
    ]
)

class InitConnection:
    """
    Handles server initialization, client connections, and authentication.
    Features:
    - Secure password handling
    - Connection management
    - Rate limiting to prevent brute force
    - IP filtering capabilities
    - Multi-client support
    - Clean resource management
    """
    
    def __init__(self, password, max_clients=5):
        self.logger = logging.getLogger("InitConnection")
        
        # Securely store password hash, not plain text
        self.password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        # Server socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.port = 5000
        self.running = True
        
        # Client management
        self.max_clients = max_clients
        self.active_clients = []
        self.client_threads = []
        
        # Security settings
        self.failed_attempts = {}  # IP -> [timestamp1, timestamp2, ...]
        self.max_failed_attempts = 5  # Max failed attempts before timeout
        self.lockout_time = 300  # Seconds to lock out after too many failed attempts
        self.allowed_ips = []  # Empty means allow all
        self.banned_ips = []  # IPs to never allow
        
        self.logger.info(f"InitConnection initialized with max_clients={max_clients}")
        
    def _is_ip_allowed(self, ip):
        """Check if an IP is allowed to connect."""
        # Check ban list first
        if ip in self.banned_ips:
            self.logger.warning(f"Connection attempt from banned IP: {ip}")
            return False
            
        # Check allow list if not empty
        if self.allowed_ips and ip not in self.allowed_ips:
            self.logger.warning(f"Connection attempt from non-allowed IP: {ip}")
            return False
            
        # Check for too many failed attempts
        if ip in self.failed_attempts:
            # Remove attempts older than lockout_time
            now = time.time()
            self.failed_attempts[ip] = [t for t in self.failed_attempts[ip] 
                                      if now - t < self.lockout_time]
            
            # If still too many attempts, block
            if len(self.failed_attempts[ip]) >= self.max_failed_attempts:
                self.logger.warning(f"IP {ip} locked out due to too many failed attempts")
                return False
                
        return True
    
    def _record_failed_attempt(self, ip):
        """Record a failed authentication attempt."""
        if ip not in self.failed_attempts:
            self.failed_attempts[ip] = []
            
        self.failed_attempts[ip].append(time.time())
        self.logger.warning(f"Failed authentication attempt from {ip} " +
                          f"({len(self.failed_attempts[ip])}/{self.max_failed_attempts})")
    
    def _generate_client_id(self):
        """Generate a unique client ID."""
        return os.urandom(8).hex()
    
    def _create_data_sockets(self, client_id):
        """Create and bind sockets for screen sharing and event handling."""
        # Create screen socket
        screen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        screen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Find available port for screen sharing
        screen_port = self.port + 1
        while True:
            try:
                screen_socket.bind(('', screen_port))
                break
            except OSError:
                screen_port += 2  # Skip 2 to leave room for events ports
                if screen_port > self.port + 1000:
                    raise Exception("Could not find available port for screen sharing")
        
        screen_socket.listen(1)
        
        # Create events socket
        events_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        events_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Use next port for events
        events_port = screen_port + 1
        try:
            events_socket.bind(('', events_port))
        except OSError:
            screen_socket.close()
            raise Exception("Could not bind events socket")
            
        events_socket.listen(1)
        
        return screen_socket, screen_port, events_socket, events_port
    
    def start(self):
        """Start the server and listen for connections."""
        try:
            # Bind to all interfaces
            self.server_socket.bind(('', self.port))
            self.server_socket.listen(10)
            self.logger.info(f"Server started on port {self.port}")
            
            while self.running:
                try:
                    # Wait for client connection with timeout to allow clean shutdown
                    self.server_socket.settimeout(1.0)
                    client_socket, addr = self.server_socket.accept()
                    client_ip = addr[0]
                    
                    self.logger.info(f"Connection from: {addr}")
                    
                    # Check if IP is allowed and not too many active clients
                    if not self._is_ip_allowed(client_ip):
                        client_socket.close()
                        continue
                        
                    if len(self.active_clients) >= self.max_clients:
                        self.logger.warning(f"Max clients reached, rejecting connection from {addr}")
                        try:
                            client_socket.send("Server at capacity, try again later.".encode())
                        except:
                            pass
                        client_socket.close()
                        continue
                    
                    # Handle client in a new thread
                    client_thread = threading.Thread(
                        target=self.handle_client, 
                        args=(client_socket, addr)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                    self.client_threads.append(client_thread)
                    
                except socket.timeout:
                    # This is normal, just continue the loop
                    continue
                except Exception as e:
                    self.logger.error(f"Error accepting connection: {e}")
                    
            # Clean shutdown
            self.logger.info("Server shutting down...")
            self._cleanup()
            
        except Exception as e:
            self.logger.error(f"Server error: {e}", exc_info=True)
            self._cleanup()
    
    def handle_client(self, client_socket, addr):
        """
        Handle client connection and authentication.
        
        Args:
            client_socket: Socket connected to client
            addr: Client address tuple (ip, port)
        """
        client_ip = addr[0]
        client_id = self._generate_client_id()
        
        try:
            # Set socket timeout for operations
            client_socket.settimeout(30)  # 30 seconds for authentication
            
            # Send authentication prompt
            client_socket.send("Password required:".encode())
            
            # Receive password (with timeout)
            try:
                received_password = client_socket.recv(1024).decode()
            except socket.timeout:
                self.logger.warning(f"Authentication timeout from {addr}")
                client_socket.close()
                return
            
            # Check password (use constant-time comparison for security)
            received_hash = hashlib.sha256(received_password.encode()).hexdigest()
            if self._constant_time_compare(received_hash, self.password_hash):
                # Authentication successful
                client_socket.send("Authentication successful".encode())
                self.logger.info(f"Client {addr} authenticated successfully")
                
                # Reset failed attempts for this IP
                if client_ip in self.failed_attempts:
                    del self.failed_attempts[client_ip]
                
                # Create data sockets for this client
                try:
                    screen_socket, screen_port, events_socket, events_port = self._create_data_sockets(client_id)
                except Exception as e:
                    self.logger.error(f"Failed to create data sockets: {e}")
                    client_socket.send("Server error: Failed to create data channels".encode())
                    client_socket.close()
                    return
                
                # Send ports to client
                client_socket.send(f"{screen_port},{events_port}".encode())
                
                # Track this client
                self.active_clients.append({
                    'id': client_id,
                    'ip': client_ip,
                    'connected_at': time.time(),
                    'screen_socket': screen_socket,
                    'events_socket': events_socket,
                    'control_socket': client_socket,
                    'screen_thread': None,
                    'events_thread': None,
                })
                
                # Accept connections on the new sockets (with timeout)
                screen_socket.settimeout(10)
                events_socket.settimeout(10)
                
                try:
                    screen_client, _ = screen_socket.accept()
                    events_client, _ = events_socket.accept()
                    
                    # Now set longer timeouts for data operations
                    screen_client.settimeout(60)
                    events_client.settimeout(60)
                    
                    # Start screen sharing and event handling
                    screen_thread = SendScreen(screen_client)
                    events_thread = ReceiveEvents(events_client)
                    
                    # Store threads in client info
                    for client in self.active_clients:
                        if client['id'] == client_id:
                            client['screen_thread'] = screen_thread
                            client['events_thread'] = events_thread
                            break
                    
                    screen_thread.start()
                    events_thread.start()
                    
                    # Wait for threads to complete
                    screen_thread.join()
                    events_thread.join()
                    
                except socket.timeout:
                    self.logger.error(f"Timeout waiting for data connections from {addr}")
                except Exception as e:
                    self.logger.error(f"Error in data connection: {e}")
                    
                # Clean up this client
                self._remove_client(client_id)
                
            else:
                # Authentication failed
                client_socket.send("Authentication failed".encode())
                self.logger.warning(f"Client {addr} authentication failed")
                
                # Record failed attempt
                self._record_failed_attempt(client_ip)
                
                client_socket.close()
                
        except Exception as e:
            self.logger.error(f"Error handling client {addr}: {e}")
            try:
                client_socket.close()
            except:
                pass
            
            # Remove client if it was added
            self._remove_client(client_id)
    
    def _constant_time_compare(self, a, b):
        """
        Compare two strings in constant time to prevent timing attacks.
        
        Args:
            a, b: Strings to compare
            
        Returns:
            bool: True if strings are equal
        """
        if len(a) != len(b):
            return False
            
        result = 0
        for x, y in zip(a, b):
            result |= ord(x) ^ ord(y)
            
        return result == 0
    
    def _remove_client(self, client_id):
        """Remove a client and clean up its resources."""
        for i, client in enumerate(self.active_clients):
            if client['id'] == client_id:
                # Stop threads
                if client['screen_thread'] and client['screen_thread'].is_alive():
                    client['screen_thread'].stop()
                    
                if client['events_thread'] and client['events_thread'].is_alive():
                    client['events_thread'].stop()
                
                # Close sockets
                for socket_name in ['control_socket', 'screen_socket', 'events_socket']:
                    if socket_name in client and client[socket_name]:
                        try:
                            client[socket_name].close()
                        except:
                            pass
                
                # Remove from active clients
                self.logger.info(f"Client {client['ip']} disconnected")
                self.active_clients.pop(i)
                break
    
    def _cleanup(self):
        """Clean up all resources when shutting down."""
        # Stop all client threads
        for client in self.active_clients:
            self._remove_client(client['id'])
            
        # Close server socket
        try:
            self.server_socket.close()
        except:
            pass
            
        self.active_clients = []
        self.client_threads = []
    
    def stop(self):
        """Stop the server gracefully."""
        self.logger.info("Stopping server")
        self.running = False
        
        # Cleanup will happen in the start method