import struct
import time
import logging
import queue
import threading
from collections import deque

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("remote_desktop_client.log"),
        logging.StreamHandler()
    ]
)

class SendEvents:
    """
    Handles capturing user input events from the client and sending them to the server.
    Features:
    - Event throttling to prevent network congestion
    - Keyboard mapping for cross-platform compatibility
    - Event queuing for reliable delivery
    - Connection recovery
    - Comprehensive event support (mouse, keyboard, scroll)
    """
    
    def __init__(self, client_socket, display_panel):
        self.logger = logging.getLogger("SendEvents")
        self.client_socket = client_socket
        self.display_panel = display_panel
        
        # Constants for event types
        self.MOUSE_MOVE = 1
        self.MOUSE_PRESS = 2
        self.MOUSE_RELEASE = 3
        self.KEY_PRESS = 4
        self.KEY_RELEASE = 5
        self.MOUSE_WHEEL = 6
        
        # Event throttling
        self.mouse_move_throttle = 0.01  # seconds (limit to 100 events/sec)
        self.last_mouse_move_time = 0
        self.last_mouse_position = (0, 0)
        self.mouse_move_threshold = 2  # minimum pixel change to send a move event
        
        # Event queue for reliable delivery
        self.event_queue = queue.Queue(maxsize=100)
        self.running = True
        
        # Connection status
        self.connected = True
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        
        # Mouse button state tracking (to handle edge cases)
        self.mouse_buttons_state = {1: False, 2: False, 3: False}
        
        # For handling modifier keys (Shift, Ctrl, Alt)
        self.modifier_keys = {16: False, 17: False, 18: False}  # Shift, Ctrl, Alt
        
        # Track last few events for deduplication
        self.last_events = deque(maxlen=10)
        
        # Start event processing thread
        self.event_thread = threading.Thread(target=self._process_events)
        self.event_thread.daemon = True
        self.event_thread.start()
        
        # Bind events
        self.bind_events()
        
        self.logger.info("SendEvents initialized")
        
    def bind_events(self):
        """Bind all input events to the display panel."""
        # Mouse events
        self.display_panel.bind("<Motion>", self.on_mouse_move)
        self.display_panel.bind("<ButtonPress-1>", lambda e: self.on_mouse_press(e, 1))
        self.display_panel.bind("<ButtonPress-2>", lambda e: self.on_mouse_press(e, 2))
        self.display_panel.bind("<ButtonPress-3>", lambda e: self.on_mouse_press(e, 3))
        self.display_panel.bind("<ButtonRelease-1>", lambda e: self.on_mouse_release(e, 1))
        self.display_panel.bind("<ButtonRelease-2>", lambda e: self.on_mouse_release(e, 2))
        self.display_panel.bind("<ButtonRelease-3>", lambda e: self.on_mouse_release(e, 3))
        
        # Mouse wheel
        self.display_panel.bind("<MouseWheel>", self.on_mouse_wheel)  # Windows
        self.display_panel.bind("<Button-4>", lambda e: self.on_mouse_wheel(e, 1))  # Linux scroll up
        self.display_panel.bind("<Button-5>", lambda e: self.on_mouse_wheel(e, -1))  # Linux scroll down
        
        # Keyboard events
        self.display_panel.bind("<KeyPress>", self.on_key_press)
        self.display_panel.bind("<KeyRelease>", self.on_key_release)
        
        # Window focus events
        self.display_panel.bind("<FocusIn>", self.on_focus_in)
        self.display_panel.bind("<FocusOut>", self.on_focus_out)
        
        # Make canvas focusable
        self.display_panel.config(takefocus=True)
        self.display_panel.focus_set()
        
    def _queue_event(self, event_type, data):
        """
        Add an event to the queue for processing.
        
        Args:
            event_type: Type of event (int)
            data: Event data as bytes
        """
        try:
            # Create a tuple of event type and data
            event = (event_type, data)
            
            # Check for duplicate events (especially for mouse moves)
            if event_type == self.MOUSE_MOVE and event in self.last_events:
                return
                
            # Add to deduplication list
            self.last_events.append(event)
            
            # Add to processing queue
            if not self.event_queue.full():
                self.event_queue.put((event_type, data), block=False)
            else:
                # If queue is full, prioritize important events (not mouse moves)
                if event_type != self.MOUSE_MOVE:
                    # Remove a mouse move event if possible to make room
                    try:
                        temp_queue = list(self.event_queue.queue)
                        for i, (queued_type, _) in enumerate(temp_queue):
                            if queued_type == self.MOUSE_MOVE:
                                self.event_queue.queue.remove((queued_type, _))
                                self.event_queue.put((event_type, data), block=False)
                                break
                    except:
                        # If something goes wrong, just ignore this event
                        pass
        except Exception as e:
            self.logger.error(f"Error queueing event: {e}")
    
    def _send_event(self, event_type, data):
        """
        Send an event to the server.
        
        Args:
            event_type: Type of event (int)
            data: Event data as bytes
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Send event type
            event_type_bytes = struct.pack('>i', event_type)
            self.client_socket.send(event_type_bytes)
            
            # Send event data
            self.client_socket.send(data)
            return True
        except (ConnectionError, TimeoutError) as e:
            self.logger.error(f"Connection error while sending event: {e}")
            self.connected = False
            return False
        except Exception as e:
            self.logger.error(f"Error sending event: {e}")
            return False
    
    def _attempt_reconnection(self):
        """
        Attempt to reconnect to the server.
        
        Returns:
            bool: True if reconnection was successful
        """
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            return False
            
        self.reconnect_attempts += 1
        self.logger.info(f"Attempting to reconnect ({self.reconnect_attempts}/{self.max_reconnect_attempts})...")
        
        # Wait before retrying
        time.sleep(2)
        
        # Reconnection would need to be coordinated with the main application
        # For now, just return False to indicate failure
        return False
    
    def _process_events(self):
        """Process events from the queue and send them to the server."""
        while self.running:
            try:
                # Get event from queue with timeout
                try:
                    event_type, data = self.event_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                    
                # If not connected, try to reconnect
                if not self.connected:
                    if self._attempt_reconnection():
                        self.connected = True
                        self.reconnect_attempts = 0
                    else:
                        # Skip this event if still not connected
                        self.event_queue.task_done()
                        time.sleep(0.5)  # Avoid tight loop
                        continue
                
                # Send the event
                success = self._send_event(event_type, data)
                
                if success:
                    # Mark as done
                    self.event_queue.task_done()
                else:
                    # If sending failed, put it back in the queue (except mouse moves)
                    if event_type != self.MOUSE_MOVE and self.connected:
                        self.event_queue.put((event_type, data))
                    else:
                        # Mark as done even if failed for mouse moves
                        self.event_queue.task_done()
                
                # Small delay to avoid overwhelming the network
                time.sleep(0.001)
                
            except Exception as e:
                self.logger.error(f"Error in event processing thread: {e}")
                time.sleep(0.1)  # Avoid tight loop in case of persistent errors
    
    def on_mouse_move(self, event):
        """Handle mouse move events with throttling."""
        current_time = time.time()
        current_pos = (event.x, event.y)
        
        # Calculate distance moved since last sent position
        dx = abs(current_pos[0] - self.last_mouse_position[0])
        dy = abs(current_pos[1] - self.last_mouse_position[1])
        distance_moved = (dx**2 + dy**2) ** 0.5  # Euclidean distance
        
        # Check if we should throttle this event
        if (current_time - self.last_mouse_move_time < self.mouse_move_throttle and 
            distance_moved < self.mouse_move_threshold):
            return
            
        # Update time and position tracking
        self.last_mouse_move_time = current_time
        self.last_mouse_position = current_pos
        
        try:
            # Queue event type and coordinates
            coords = struct.pack('>ii', event.x, event.y)
            self._queue_event(self.MOUSE_MOVE, coords)
        except Exception as e:
            self.logger.error(f"Error handling mouse move event: {e}")
            
    def on_mouse_press(self, event, button):
        """Handle mouse button press events."""
        try:
            # Update button state
            self.mouse_buttons_state[button] = True
            
            # Queue event
            button_data = struct.pack('>i', button)
            self._queue_event(self.MOUSE_PRESS, button_data)
        except Exception as e:
            self.logger.error(f"Error handling mouse press event: {e}")
            
    def on_mouse_release(self, event, button):
        """Handle mouse button release events."""
        try:
            # Update button state
            self.mouse_buttons_state[button] = False
            
            # Queue event
            button_data = struct.pack('>i', button)
            self._queue_event(self.MOUSE_RELEASE, button_data)
        except Exception as e:
            self.logger.error(f"Error handling mouse release event: {e}")
    
    def on_mouse_wheel(self, event, direction=None):
        """
        Handle mouse wheel events.
        
        Args:
            event: The event object
            direction: Optional direction override for Linux compatibility
        """
        try:
            # Get scroll direction
            if direction is None:
                # Windows provides event.delta
                direction = 1 if event.delta > 0 else -1
                
            # Queue event
            wheel_data = struct.pack('>i', direction)
            self._queue_event(self.MOUSE_WHEEL, wheel_data)
        except Exception as e:
            self.logger.error(f"Error handling mouse wheel event: {e}")
            
    def on_key_press(self, event):
        """Handle key press events with special key mapping."""
        try:
            # Update modifier key state
            if event.keycode in self.modifier_keys:
                self.modifier_keys[event.keycode] = True
                
            # Queue event with both keycode and keysym for better cross-platform support
            key_data = struct.pack('>ii', event.keycode, hash(event.keysym) % 2147483647)
            self._queue_event(self.KEY_PRESS, key_data)
        except Exception as e:
            self.logger.error(f"Error handling key press event: {e}")
            
    def on_key_release(self, event):
        """Handle key release events with special key mapping."""
        try:
            # Update modifier key state
            if event.keycode in self.modifier_keys:
                self.modifier_keys[event.keycode] = False
                
            # Queue event with both keycode and keysym
            key_data = struct.pack('>ii', event.keycode, hash(event.keysym) % 2147483647)
            self._queue_event(self.KEY_RELEASE, key_data)
        except Exception as e:
            self.logger.error(f"Error handling key release event: {e}")
    
    def on_focus_in(self, event):
        """Handle window focus events."""
        self.logger.info("Display panel gained focus")
        self.display_panel.focus_set()
    
    def on_focus_out(self, event):
        """Handle window focus loss events."""
        self.logger.info("Display panel lost focus")
        # Release any pressed keys/buttons to avoid them getting "stuck"
        self._release_stuck_inputs()
    
    def _release_stuck_inputs(self):
        """
        Release any keys or mouse buttons that might be stuck in pressed state.
        This prevents issues when focus is lost while keys are pressed.
        """
        try:
            # Release any pressed mouse buttons
            for button, is_pressed in self.mouse_buttons_state.items():
                if is_pressed:
                    self.logger.info(f"Releasing stuck mouse button {button}")
                    self.mouse_buttons_state[button] = False
                    button_data = struct.pack('>i', button)
                    self._queue_event(self.MOUSE_RELEASE, button_data)
            
            # Release any pressed modifier keys
            for key, is_pressed in self.modifier_keys.items():
                if is_pressed:
                    self.logger.info(f"Releasing stuck modifier key {key}")
                    self.modifier_keys[key] = False
                    key_data = struct.pack('>ii', key, 0)
                    self._queue_event(self.KEY_RELEASE, key_data)
        except Exception as e:
            self.logger.error(f"Error releasing stuck inputs: {e}")
    
    def stop(self):
        """Stop the event sending thread and clean up resources."""
        self.logger.info("Stopping SendEvents")
        self.running = False
        
        # Release any pressed keys to avoid them getting "stuck" on the server
        self._release_stuck_inputs()
        
        # Wait for event queue to be processed
        if hasattr(self, 'event_queue'):
            try:
                self.event_queue.join(timeout=1.0)
            except:
                pass
        
        # Unbind all events
        self.display_panel.unbind("<Motion>")
        self.display_panel.unbind("<ButtonPress-1>")
        self.display_panel.unbind("<ButtonPress-2>")
        self.display_panel.unbind("<ButtonPress-3>")
        self.display_panel.unbind("<ButtonRelease-1>")
        self.display_panel.unbind("<ButtonRelease-2>")
        self.display_panel.unbind("<ButtonRelease-3>")
        self.display_panel.unbind("<MouseWheel>")
        self.display_panel.unbind("<Button-4>")
        self.display_panel.unbind("<Button-5>")
        self.display_panel.unbind("<KeyPress>")
        self.display_panel.unbind("<KeyRelease>")
        self.display_panel.unbind("<FocusIn>")
        self.display_panel.unbind("<FocusOut>")