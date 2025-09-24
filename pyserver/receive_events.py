import threading
import struct
import time
import logging
import pyautogui
from collections import deque

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("remote_desktop_server.log"),
        logging.StreamHandler()
    ]
)

class ReceiveEvents(threading.Thread):
    """
    Thread responsible for receiving user input events from clients and executing them.
    Features:
    - Comprehensive event handling including mouse wheel
    - Input validation and sanitization
    - Security restrictions
    - Event rate limiting
    - Robust error handling
    """
    
    def __init__(self, client_socket):
        super().__init__()
        self.logger = logging.getLogger("ReceiveEvents")
        self.client_socket = client_socket
        # Remove or increase the timeout to prevent frequent timeouts
        self.client_socket.settimeout(None)  # No timeout
        self.running = True
        self.daemon = True
        
        # Constants for event types
        self.MOUSE_MOVE = 1
        self.MOUSE_PRESS = 2
        self.MOUSE_RELEASE = 3
        self.KEY_PRESS = 4
        self.KEY_RELEASE = 5
        self.MOUSE_WHEEL = 6
        
        # Security and rate limiting
        self.last_event_time = 0
        self.min_event_interval = 0.001  # 1ms minimum between events
        self.recent_events = deque(maxlen=50)  # Track recent events for pattern detection
        
        # Current state for duplicate prevention
        self.current_mouse_pos = pyautogui.position()
        self.current_keys_down = set()
        self.current_mouse_buttons = set()
        
        # Get screen dimensions for bounds checking
        self.screen_width, self.screen_height = pyautogui.size()
        
        # Keyboard mapping for special keys
        self.key_map = self._initialize_key_map()
        
        # Security settings
        self.enable_security = True  # Set to False to disable security checks
        self.blocked_key_combos = [
            # Potentially dangerous combinations
            frozenset(['ctrl', 'alt', 'del']),
            frozenset(['win', 'r']),
            frozenset(['ctrl', 'shift', 'esc']),
            frozenset(['alt', 'f4']),
        ]
        
        self.logger.info("ReceiveEvents initialized")
        
    def _initialize_key_map(self):
        """Create a comprehensive mapping of key codes to PyAutoGUI keys."""
        key_map = {
            8: 'backspace',
            9: 'tab',
            13: 'enter',
            16: 'shift',
            17: 'ctrl',
            18: 'alt',
            20: 'capslock',
            27: 'esc',
            32: 'space',
            33: 'pageup',
            34: 'pagedown',
            35: 'end',
            36: 'home',
            37: 'left',
            38: 'up',
            39: 'right',
            40: 'down',
            44: 'printscreen',
            45: 'insert',
            46: 'delete',
            91: 'win',
            93: 'menu',
            144: 'numlock',
            145: 'scrolllock',
            186: ';',
            187: '=',
            188: ',',
            189: '-',
            190: '.',
            191: '/',
            192: '`',
            219: '[',
            220: '\\',
            221: ']',
            222: "'",
        }
        
        # Add function keys (F1-F12)
        for i in range(1, 13):
            key_map[111 + i] = f'f{i}'
            
        # Add number keys (0-9)
        for i in range(10):
            key_map[48 + i] = str(i)
            
        # Add letter keys (A-Z)
        for i in range(26):
            key_map[65 + i] = chr(97 + i)  # a-z (lowercase for pyautogui)
            
        # Add numpad keys
        for i in range(10):
            key_map[96 + i] = f'num{i}'
            
        return key_map
    
    def _is_valid_coordinate(self, x, y):
        """Check if coordinates are within screen bounds."""
        return (0 <= x < self.screen_width and 0 <= y < self.screen_height)
    
    def _check_rate_limiting(self):
        """
        Implement rate limiting to prevent event flooding.
        Returns True if event should be processed, False if it should be dropped.
        """
        current_time = time.time()
        time_since_last = current_time - self.last_event_time
        
        # Update last event time
        self.last_event_time = current_time
        
        # Simple rate limiting
        return time_since_last >= self.min_event_interval
    
    def _is_dangerous_key_combo(self):
        """Check if current key combination is potentially dangerous."""
        if not self.enable_security:
            return False
            
        current_combo = frozenset(self.current_keys_down)
        
        # Check if current combo contains any blocked combo
        for blocked_combo in self.blocked_key_combos:
            if blocked_combo.issubset(current_combo):
                self.logger.warning(f"Blocked dangerous key combination: {current_combo}")
                return True
                
        return False
    
    def _receive_exactly(self, size):
        """
        Receive exactly the specified number of bytes from the socket.
        
        Args:
            size: Number of bytes to receive
            
        Returns:
            bytes: The received data or None if connection was lost
        """
        data = bytearray()
        remaining = size
        
        try:
            while remaining > 0 and self.running:
                # Set a timeout to avoid blocking indefinitely
                self.client_socket.settimeout(5.0)
                chunk = self.client_socket.recv(min(remaining, 8192))
                
                if not chunk:  # Connection closed
                    return None
                    
                data.extend(chunk)
                remaining -= len(chunk)
            
            return bytes(data) if len(data) == size else None
        except Exception as e:
            self.logger.error(f"Error receiving data: {e}")
            return None
    
    def convert_key_code(self, key_code, key_sym=None):
        """
        Convert key code to PyAutoGUI key.
        
        Args:
            key_code: The key code from the client
            key_sym: Optional key symbol for better cross-platform support
            
        Returns:
            str: The key name for PyAutoGUI or None if not mappable
        """
        # First try the key map
        key = self.key_map.get(key_code)
        
        if key:
            return key
            
        # For unmapped keys, try direct character conversion
        try:
            if 32 <= key_code <= 126:  # Printable ASCII
                return chr(key_code).lower()
        except:
            pass
            
        self.logger.debug(f"Unmapped key code: {key_code}")
        return None
    
    def run(self):
        """Main thread loop for receiving and executing user input events."""
        self.logger.info("ReceiveEvents thread started")
        
        try:
            while self.running:
                # Receive event type
                event_type_bytes = self._receive_exactly(4)
                if not event_type_bytes:
                    self.logger.warning("Connection closed by client (event type)")
                    break
                    
                event_type = struct.unpack('>i', event_type_bytes)[0]
                
                # Rate limiting - skip processing if too many events
                if not self._check_rate_limiting():
                    # Still need to receive the data to keep protocol in sync
                    if event_type == self.MOUSE_MOVE:
                        self._receive_exactly(8)
                    elif event_type in (self.MOUSE_PRESS, self.MOUSE_RELEASE, self.MOUSE_WHEEL):
                        self._receive_exactly(4)
                    elif event_type in (self.KEY_PRESS, self.KEY_RELEASE):
                        self._receive_exactly(8)  # Now receiving keysym too
                    continue
                
                # Add to recent events for pattern detection
                self.recent_events.append(event_type)
                
                # Process events
                if event_type == self.MOUSE_MOVE:
                    # Receive x, y coordinates
                    coords = self._receive_exactly(8)
                    if not coords:
                        break
                        
                    x, y = struct.unpack('>ii', coords)
                    
                    # Validate coordinates
                    if self._is_valid_coordinate(x, y):
                        # Skip if no movement
                        if (x, y) != self.current_mouse_pos:
                            self.current_mouse_pos = (x, y)
                            try:
                                pyautogui.moveTo(x, y)
                            except Exception as e:
                                self.logger.error(f"Error moving mouse: {e}")
                    else:
                        self.logger.warning(f"Invalid coordinates: ({x}, {y})")
                    
                elif event_type == self.MOUSE_PRESS:
                    # Receive button information
                    button_data = self._receive_exactly(4)
                    if not button_data:
                        break
                        
                    button = struct.unpack('>i', button_data)[0]
                    
                    # Convert button number to string
                    button_map = {1: 'left', 2: 'middle', 3: 'right'}
                    button_str = button_map.get(button)
                    
                    if button_str:
                        if button_str not in self.current_mouse_buttons:
                            self.current_mouse_buttons.add(button_str)
                            try:
                                pyautogui.mouseDown(button=button_str)
                            except Exception as e:
                                self.logger.error(f"Error pressing mouse button: {e}")
                    else:
                        self.logger.warning(f"Unknown mouse button: {button}")
                        
                elif event_type == self.MOUSE_RELEASE:
                    # Receive button information
                    button_data = self._receive_exactly(4)
                    if not button_data:
                        break
                        
                    button = struct.unpack('>i', button_data)[0]
                    
                    # Convert button number to string
                    button_map = {1: 'left', 2: 'middle', 3: 'right'}
                    button_str = button_map.get(button)
                    
                    if button_str:
                        if button_str in self.current_mouse_buttons:
                            self.current_mouse_buttons.remove(button_str)
                        try:
                            pyautogui.mouseUp(button=button_str)
                        except Exception as e:
                            self.logger.error(f"Error releasing mouse button: {e}")
                    else:
                        self.logger.warning(f"Unknown mouse button: {button}")
                        
                elif event_type == self.MOUSE_WHEEL:
                    # Receive wheel direction
                    wheel_data = self._receive_exactly(4)
                    if not wheel_data:
                        break
                        
                    direction = struct.unpack('>i', wheel_data)[0]
                    
                    try:
                        # PyAutoGUI uses clicks, where positive is up and negative is down
                        pyautogui.scroll(direction * 3)  # Multiply for more noticeable scrolling
                    except Exception as e:
                        self.logger.error(f"Error scrolling: {e}")
                        
                elif event_type == self.KEY_PRESS:
                    # Receive key code and keysym
                    key_data = self._receive_exactly(8)
                    if not key_data:
                        break
                        
                    key_code, key_sym = struct.unpack('>ii', key_data)
                    
                    # Convert key code to PyAutoGUI key
                    key = self.convert_key_code(key_code, key_sym)
                    
                    if key:
                        # Track key state
                        self.current_keys_down.add(key)
                        
                        # Check for dangerous key combinations
                        if self._is_dangerous_key_combo():
                            self.logger.warning(f"Blocked dangerous key combination with: {key}")
                            continue
                            
                        try:
                            pyautogui.keyDown(key)
                        except Exception as e:
                            self.logger.error(f"Error pressing key '{key}': {e}")
                    else:
                        self.logger.debug(f"Unmapped key press: {key_code}")
                        
                elif event_type == self.KEY_RELEASE:
                    # Receive key code and keysym
                    key_data = self._receive_exactly(8)
                    if not key_data:
                        break
                        
                    key_code, key_sym = struct.unpack('>ii', key_data)
                    
                    # Convert key code to PyAutoGUI key
                    key = self.convert_key_code(key_code, key_sym)
                    
                    if key:
                        # Track key state
                        if key in self.current_keys_down:
                            self.current_keys_down.remove(key)
                            
                        try:
                            pyautogui.keyUp(key)
                        except Exception as e:
                            self.logger.error(f"Error releasing key '{key}': {e}")
                    else:
                        self.logger.debug(f"Unmapped key release: {key_code}")
                        
        except Exception as e:
            self.logger.error(f"Error in event handling: {e}", exc_info=True)
        finally:
            self.running = False
            
            # Release any pressed keys or buttons
            self._release_all_inputs()
            
            try:
                self.client_socket.close()
            except:
                pass
                
            self.logger.info("ReceiveEvents thread stopped")
    
    def _release_all_inputs(self):
        """Release all pressed keys and mouse buttons to avoid them getting stuck."""
        self.logger.info("Releasing all pressed inputs")
        
        # Release all keys
        for key in self.current_keys_down:
            try:
                pyautogui.keyUp(key)
            except:
                pass
        self.current_keys_down.clear()
        
        # Release all mouse buttons
        for button in self.current_mouse_buttons:
            try:
                pyautogui.mouseUp(button=button)
            except:
                pass
        self.current_mouse_buttons.clear()
    
    def stop(self):
        """Stop the event receiving thread gracefully."""
        self.logger.info("Stopping ReceiveEvents thread")
        self.running = False
        self._release_all_inputs()