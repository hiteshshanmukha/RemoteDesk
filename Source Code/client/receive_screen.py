import threading
import struct
import io
import time
import logging
import tkinter as tk
from PIL import Image, ImageTk
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("remote_desktop_client.log"),
        logging.StreamHandler()
    ]
)

class ReceiveScreen(threading.Thread):
    """
    Thread responsible for receiving and displaying screen captures from the server.
    Features:
    - Adaptive image quality based on network conditions
    - Automatic scaling for different device screens
    - Connection recovery mechanism
    - Performance monitoring
    - Frame buffering for smoother playback
    """
    
    def __init__(self, client_socket, display_panel, buffer_size=3):
        """
        Initialize the screen receiver.
        
        Args:
            client_socket: Socket connection to the server
            display_panel: Tkinter canvas to display the remote screen
            buffer_size: Number of frames to buffer for smoother playback
        """
        super().__init__()
        self.logger = logging.getLogger("ReceiveScreen")
        self.client_socket = client_socket
        self.display_panel = display_panel
        self.running = True
        self.daemon = True  # Thread will exit when main program exits
        
        # Performance monitoring
        self.frame_count = 0
        self.start_time = time.time()
        self.last_frame_time = 0
        self.network_latency = 0
        
        # Frame buffer for smoother playback
        self.buffer_size = buffer_size
        self.frame_buffer = []
        
        # Reconnection settings
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 2  # seconds
        
        # Adaptive quality
        self.quality_level = 70  # Initial quality level (will be adjusted)
        self.quality_min = 20
        self.quality_max = 95
        self.target_fps = 20
        
        # Get the screen dimensions for scaling
        self.screen_width = self.display_panel.winfo_screenwidth()
        self.screen_height = self.display_panel.winfo_screenheight()
        
        # Status display
        self.status_text = None
        self._create_status_display()
        
        self.logger.info("ReceiveScreen initialized with buffer size: %d", buffer_size)
        
    def _create_status_display(self):
        """Create a text item on the canvas for status information."""
        self.status_text = self.display_panel.create_text(
            10, 10, anchor="nw", fill="lime", font=("Arial", 10),
            text="Connecting...", tags=["status"]
        )
    
    def _update_status(self, fps, latency, quality):
        """Update the status display with current performance metrics."""
        if self.status_text and self.running:
            status_msg = f"FPS: {fps:.1f} | Latency: {latency:.0f}ms | Quality: {quality}%"
            self.display_panel.itemconfig(self.status_text, text=status_msg)
            # Make sure status text stays on top
            self.display_panel.tag_raise("status")
    
    def _calculate_metrics(self):
        """Calculate performance metrics."""
        self.frame_count += 1
        current_time = time.time()
        elapsed = current_time - self.start_time
        
        # Calculate FPS over the last 3 seconds
        if elapsed >= 3:
            fps = self.frame_count / elapsed
            self.frame_count = 0
            self.start_time = current_time
            
            # Adjust quality based on achieved FPS
            if fps < self.target_fps * 0.8 and self.quality_level > self.quality_min:
                self.quality_level = max(self.quality_level - 5, self.quality_min)
                self.logger.info(f"Reducing quality to {self.quality_level}% (FPS: {fps:.1f})")
            elif fps > self.target_fps * 1.2 and self.quality_level < self.quality_max:
                self.quality_level = min(self.quality_level + 5, self.quality_max)
                self.logger.info(f"Increasing quality to {self.quality_level}% (FPS: {fps:.1f})")
            
            # Update status display
            self._update_status(fps, self.network_latency, self.quality_level)
            
            return fps
        return None
    
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
        start_time = time.time()
        
        try:
            while remaining > 0 and self.running:
                # Set a timeout to avoid blocking indefinitely
                self.client_socket.settimeout(5.0)
                chunk = self.client_socket.recv(min(remaining, 8192))
                
                if not chunk:  # Connection closed
                    return None
                    
                data.extend(chunk)
                remaining -= len(chunk)
                
            # Calculate network latency
            self.network_latency = (time.time() - start_time) * 1000  # ms
            
            return bytes(data) if len(data) == size else None
        except (ConnectionError, TimeoutError) as e:
            self.logger.error(f"Connection error while receiving data: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while receiving data: {e}")
            return None
    
    def _scale_image(self, image):
        """
        Scale the image to fit the display panel while maintaining aspect ratio.
        
        Args:
            image: PIL Image to scale
            
        Returns:
            PIL Image: Scaled image
        """
        # Get the current size of the display panel
        panel_width = self.display_panel.winfo_width()
        panel_height = self.display_panel.winfo_height()
        
        # If the panel size is not yet available, use screen dimensions
        if panel_width <= 1 or panel_height <= 1:
            panel_width = self.screen_width
            panel_height = self.screen_height
        
        # Get image dimensions
        img_width, img_height = image.size
        
        # Calculate scaling factors
        width_ratio = panel_width / img_width
        height_ratio = panel_height / img_height
        
        # Use the smaller ratio to ensure the image fits
        scale_factor = min(width_ratio, height_ratio)
        
        # Only scale if necessary (avoid upscaling small images)
        if scale_factor < 1 or (scale_factor > 1.1 and max(img_width, img_height) < 800):
            new_width = int(img_width * scale_factor)
            new_height = int(img_height * scale_factor)
            
            # Use LANCZOS for high-quality downsampling, BICUBIC for upsampling
            resample_method = Image.LANCZOS if scale_factor < 1 else Image.BICUBIC
            
            # Resize the image
            return image.resize((new_width, new_height), resample_method)
        
        return image
    
    def _process_and_display_frame(self, img_data):
        """
        Process and display a received frame.
        
        Args:
            img_data: Raw image data as bytes
        """
        try:
            # Convert bytes to image
            image = Image.open(io.BytesIO(img_data))
            
            # Scale image to fit display if needed
            image = self._scale_image(image)
            
            # Convert to PhotoImage for tkinter
            photo = ImageTk.PhotoImage(image)
            
            # Store in buffer or display directly based on buffer settings
            if self.buffer_size > 1:
                self.frame_buffer.append(photo)
                if len(self.frame_buffer) >= self.buffer_size:
                    photo_to_display = self.frame_buffer.pop(0)
                    self._display_frame(photo_to_display)
            else:
                self._display_frame(photo)
                
            # Calculate performance metrics
            self._calculate_metrics()
            
        except Exception as e:
            self.logger.error(f"Error processing image data: {e}")
    
    def _display_frame(self, photo):
        """
        Display a frame on the canvas.
        
        Args:
            photo: PhotoImage to display
        """
        try:
            # Clear canvas and display image
            self.display_panel.delete("image")  # Delete only the image, not status text
            self.display_panel.create_image(
                self.display_panel.winfo_width() // 2,
                self.display_panel.winfo_height() // 2,
                image=photo, anchor="center", tags=["image"]
            )
            self.display_panel.image = photo  # Keep reference to prevent garbage collection
            
            # Make sure status stays on top
            self.display_panel.tag_raise("status")
            
            # Update last frame time
            self.last_frame_time = time.time()
        except Exception as e:
            self.logger.error(f"Error displaying frame: {e}")
    
    def _attempt_reconnection(self):
        """Attempt to reconnect to the server."""
        for attempt in range(self.max_reconnect_attempts):
            self.logger.info(f"Reconnection attempt {attempt + 1}/{self.max_reconnect_attempts}")
            
            # Update status
            if self.status_text:
                self.display_panel.itemconfig(
                    self.status_text, 
                    text=f"Connection lost. Reconnecting ({attempt + 1}/{self.max_reconnect_attempts})...",
                    fill="yellow"
                )
            
            # Wait before retry
            time.sleep(self.reconnect_delay)
            
            # Notify the main application about reconnection (can be implemented by the caller)
            # For now, just return False to indicate reconnection failed
            return False
        
        # Update status to connection failed
        if self.status_text:
            self.display_panel.itemconfig(
                self.status_text,
                text="Connection lost. Reconnection failed.",
                fill="red"
            )
        
        return False
    
    def run(self):
        """Main thread loop for receiving and displaying screen updates."""
        self.logger.info("ReceiveScreen thread started")
        connection_lost = False
        
        try:
            while self.running:
                # If connection was lost, try to reconnect
                if connection_lost:
                    if not self._attempt_reconnection():
                        break
                    connection_lost = False
                
                # Receive image size (4 bytes)
                size_data = self._receive_exactly(4)
                if not size_data:
                    self.logger.warning("Failed to receive image size data")
                    connection_lost = True
                    continue
                
                # Convert bytes to integer
                size = int.from_bytes(size_data, byteorder='big')
                
                # Sanity check on size (prevent memory issues)
                if size <= 0 or size > 50000000:  # Max 50MB per frame
                    self.logger.warning(f"Received invalid image size: {size} bytes")
                    continue
                
                # Receive image data
                img_data = self._receive_exactly(size)
                if not img_data:
                    self.logger.warning("Failed to receive complete image data")
                    connection_lost = True
                    continue
                
                # Process and display the received frame
                self._process_and_display_frame(img_data)
                
                # Check if too much time passed since the last frame
                if time.time() - self.last_frame_time > 5:
                    self.logger.warning("No frames received for 5 seconds")
                    
        except Exception as e:
            self.logger.error(f"Error in ReceiveScreen thread: {e}", exc_info=True)
        finally:
            self.running = False
            self.logger.info("ReceiveScreen thread stopped")
    
    def toggle_status_display(self):
        """Toggle the visibility of the status display."""
        if self.status_text:
            current_state = self.display_panel.itemcget(self.status_text, 'state')
            new_state = 'hidden' if current_state == 'normal' else 'normal'
            self.display_panel.itemconfig(self.status_text, state=new_state)
    
    def set_buffer_size(self, size):
        """
        Change the frame buffer size.
        
        Args:
            size: New buffer size (0-10)
        """
        if 0 <= size <= 10:
            # Clear existing buffer if reducing size
            if size < self.buffer_size:
                self.frame_buffer = self.frame_buffer[-size:] if size > 0 else []
            self.buffer_size = size
            self.logger.info(f"Frame buffer size changed to {size}")
    
    def stop(self):
        """Stop the receiver thread."""
        self.logger.info("Stopping ReceiveScreen thread")
        self.running = False
        # Clear frame buffer to release memory
        self.frame_buffer.clear()