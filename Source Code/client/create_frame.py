import tkinter as tk
from tkinter import messagebox
import socket
import threading
from receive_screen import ReceiveScreen
from send_events import SendEvents

class CreateFrame:
    def __init__(self, server_ip, screen_port, events_port, root):
        self.server_ip = server_ip
        self.screen_port = screen_port
        self.events_port = events_port
        self.main_root = root
        
        # Create main window
        self.window = tk.Toplevel(root)
        self.window.title(f"Remote Desktop - {server_ip}")
        self.window.state('zoomed')  # Maximize window
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Create display panel
        self.display_panel = tk.Canvas(self.window, bg="black")
        self.display_panel.pack(fill=tk.BOTH, expand=True)
        
        # Connect to server
        try:
            # Connect to screen socket
            self.screen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.screen_socket.connect((self.server_ip, self.screen_port))
            
            # Connect to events socket
            self.events_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.events_socket.connect((self.server_ip, self.events_port))
            
            # Start screen receiving thread
            self.receive_screen = ReceiveScreen(self.screen_socket, self.display_panel)
            self.receive_screen.start()
            
            # Start event sending
            self.send_events = SendEvents(self.events_socket, self.display_panel)
            
        except Exception as e:
            messagebox.showerror("Connection Error", 
                                f"Failed to connect to server streams: {e}")
            self.on_close()
            
    def on_close(self):
        try:
            if hasattr(self, 'receive_screen'):
                self.receive_screen.stop()
            
            if hasattr(self, 'send_events'):
                self.send_events.stop()
                
            if hasattr(self, 'screen_socket'):
                self.screen_socket.close()
                
            if hasattr(self, 'events_socket'):
                self.events_socket.close()
                
        except Exception as e:
            print(f"Error during cleanup: {e}")
            
        finally:
            self.window.destroy()
            self.main_root.destroy()