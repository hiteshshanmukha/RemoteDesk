import threading
import time
import io
import logging
import socket
import pyautogui
from PIL import Image
import mss
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("remote_desktop_server.log"),
        logging.StreamHandler()
    ]
)

class SendScreen(threading.Thread):
    """
    Thread responsible for capturing and sending screen updates to the client.
    Features:
    - High-performance screen capture using mss
    - Adaptive quality based on network conditions
    - Frame rate control
    - Region-based change detection
    - Selective updates to reduce bandwidth
    """
    
    def __init__(self, client_socket, initial_quality=70, target_fps=20):
        super().__init__()
        self.logger = logging.getLogger("SendScreen")
        self.client_socket = client_socket
        self.running = True
        self.daemon = True
        
        # Performance settings
        self.quality = initial_quality  # JPEG compression quality (0-100)
        self.min_quality = 20
        self.max_quality = 95
        self.target_fps = target_fps
        self.frame_interval = 1.0 / target_fps
        
        # Performance monitoring
        self.frame_count = 0
        self.start_time = time.time()
        self.network_stats = {'sent_bytes': 0, 'max_frame_size': 0, 'min_frame_size': float('inf')}
        
        # Screen capture will be initialized in run()
        self.sct = None
        self.use_pyautogui_fallback = False
        
        # Last frame for change detection
        self.last_frame = None
        self.change_threshold = 5  # Percentage of pixels that need to change to send update
        
        # Socket settings for better performance
        try:
            self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1048576)  # 1MB buffer
        except:
            self.logger.warning("Could not set socket options for performance")
        
        self.logger.info(f"SendScreen initialized with quality={initial_quality}, target_fps={target_fps}")
        
    def _capture_screen(self):
        """Capture the screen using MSS (faster than PyAutoGUI) or fall back to PyAutoGUI."""
        try:
            if self.use_pyautogui_fallback:
                return pyautogui.screenshot()
                
            # Capture the main monitor
            monitor = self.sct.monitors[1]  # Primary monitor
            screenshot = self.sct.grab(monitor)
            
            # Convert to PIL Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
            return img
        except Exception as e:
            self.logger.error(f"Error capturing screen: {e}")
            
            # If this is our first MSS error, switch to PyAutoGUI and try again
            if not self.use_pyautogui_fallback:
                self.logger.warning("Switching to PyAutoGUI fallback for screen capture")
                self.use_pyautogui_fallback = True
                try:
                    return pyautogui.screenshot()
                except Exception as e2:
                    self.logger.error(f"Error with fallback screen capture: {e2}")
                    # Return a simple black image as last resort
                    return Image.new('RGB', (800, 600), color='black')
            else:
                # Return a simple black image as last resort
                return Image.new('RGB', (800, 600), color='black')
    
    def _compress_image(self, image):
        """Compress the image with the current quality settings."""
        img_bytes = io.BytesIO()
        image.save(img_bytes, format="JPEG", quality=self.quality, optimize=True)
        return img_bytes.getvalue()
    
    def _detect_changes(self, current_frame):
        """
        Detect if there are significant changes between frames.
        Returns True if changes exceed threshold, False otherwise.
        """
        if self.last_frame is None:
            self.last_frame = current_frame
            return True
            
        try:
            # Convert to numpy arrays for faster comparison
            current_array = np.array(current_frame)
            last_array = np.array(self.last_frame)
            
            # Calculate difference
            if current_array.shape != last_array.shape:
                # Different sizes, consider it a change
                self.last_frame = current_frame
                return True
                
            diff = np.abs(current_array - last_array)
            changed_pixels = np.sum(diff > 30)  # Pixels with significant change
            total_pixels = current_array.size / 3  # RGB has 3 values per pixel
            
            change_percent = (changed_pixels / total_pixels) * 100
            
            # Update last frame if we're sending it
            if change_percent >= self.change_threshold:
                self.last_frame = current_frame
                return True
                
            return False
        except Exception as e:
            self.logger.error(f"Error in change detection: {e}")
            return True  # On error, assume changes
    
    def _adjust_quality(self, frame_time, frame_size):
        """
        Dynamically adjust quality based on performance metrics.
        - If frame time > target, reduce quality to increase speed
        - If frame time < target and quality is low, increase quality
        """
        target_time = self.frame_interval * 0.8  # Leave 20% margin
        
        # Only adjust every 30 frames to allow stabilization
        if self.frame_count % 30 != 0:
            return
            
        # Calculate FPS
        elapsed = time.time() - self.start_time
        if elapsed >= 3:  # Calculate every 3 seconds
            fps = self.frame_count / elapsed
            bandwidth = self.network_stats['sent_bytes'] / elapsed / 1024  # KB/s
            
            # Log performance metrics
            self.logger.info(
                f"Performance: FPS={fps:.1f}, Bandwidth={bandwidth:.1f} KB/s, "
                f"Quality={self.quality}%, Avg Frame={self.network_stats['sent_bytes']/max(1, self.frame_count)/1024:.1f} KB"
            )
            
            # Reset counters
            self.frame_count = 0
            self.start_time = time.time()
            self.network_stats['sent_bytes'] = 0
            self.network_stats['max_frame_size'] = 0
            self.network_stats['min_frame_size'] = float('inf')
        
        # Adjust quality based on frame time
        if frame_time > target_time and self.quality > self.min_quality:
            self.quality = max(self.min_quality, self.quality - 5)
            self.logger.debug(f"Reducing quality to {self.quality}% (frame_time={frame_time:.3f}s)")
        elif frame_time < target_time * 0.5 and self.quality < self.max_quality:
            self.quality = min(self.max_quality, self.quality + 5)
            self.logger.debug(f"Increasing quality to {self.quality}% (frame_time={frame_time:.3f}s)")
    
    def _send_frame(self, frame_data):
        """Send a frame to the client with proper error handling."""
        try:
            # Update statistics
            frame_size = len(frame_data)
            self.network_stats['sent_bytes'] += frame_size
            self.network_stats['max_frame_size'] = max(self.network_stats['max_frame_size'], frame_size)
            self.network_stats['min_frame_size'] = min(self.network_stats['min_frame_size'], frame_size)
            
            # Send size header
            size_bytes = len(frame_data).to_bytes(4, byteorder='big')
            self.client_socket.send(size_bytes)
            
            # Send frame data
            total_sent = 0
            while total_sent < len(frame_data):
                sent = self.client_socket.send(frame_data[total_sent:])
                if sent == 0:
                    raise ConnectionError("Socket connection broken")
                total_sent += sent
                
            return True
        except (ConnectionError, BrokenPipeError) as e:
            self.logger.error(f"Connection error while sending frame: {e}")
            self.running = False
            return False
        except Exception as e:
            self.logger.error(f"Error sending frame: {e}")
            return False
    
    def run(self):
        """Main thread loop for capturing and sending screen updates."""
        self.logger.info("SendScreen thread started")
        
        # Initialize MSS here in the thread context
        try:
            self.sct = mss.mss()
        except Exception as e:
            self.logger.error(f"Failed to initialize screen capture: {e}")
            self.use_pyautogui_fallback = True
        
        try:
            while self.running:
                start_time = time.time()
                
                # Capture screen
                screenshot = self._capture_screen()
                
                # Check if there are significant changes to send
                if self._detect_changes(screenshot):
                    # Compress image
                    img_bytes = self._compress_image(screenshot)
                    
                    # Send frame
                    if not self._send_frame(img_bytes):
                        break
                    
                    # Update frame count for FPS calculation
                    self.frame_count += 1
                    
                # Calculate frame time
                frame_time = time.time() - start_time
                
                # Adjust quality based on performance
                self._adjust_quality(frame_time, len(img_bytes) if 'img_bytes' in locals() else 0)
                
                # Sleep to maintain target frame rate if needed
                sleep_time = max(0, self.frame_interval - frame_time)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
        except Exception as e:
            self.logger.error(f"Error in screen sharing: {e}", exc_info=True)
        finally:
            self.logger.info("SendScreen thread stopped")
            self.running = False
            try:
                if self.sct:
                    self.sct.close()
                self.client_socket.close()
            except:
                pass
            
    def stop(self):
        """Stop the screen sharing thread gracefully."""
        self.logger.info("Stopping SendScreen thread")
        self.running = False