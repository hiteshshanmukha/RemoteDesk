import tkinter as tk
import socket
import logging
from tkinter import messagebox
from receive_screen import ReceiveScreen
from send_events import SendEvents

class CreateFrame:
    def __init__(self, server_ip, screen_port, events_port, root):
        self.logger = logging.getLogger("CreateFrame")
        self.server_ip = server_ip
        self.screen_port = screen_port
        self.events_port = events_port
        self.main_root = root
        self.screen_socket = None
        self.events_socket = None
        self.receive_screen = None
        self.send_events = None
        
        # Create main window
        self.window = tk.Toplevel(root)
        self.window.title(f"Remote Desktop - {server_ip}")
        self.window.state('zoomed')  # Maximize window
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Create menu bar with options
        self.create_menu()
        
        # Create display panel
        self.display_panel = tk.Canvas(self.window, bg="black")
        self.display_panel.pack(fill=tk.BOTH, expand=True)
        
        # Connect to server
        try:
            # Connect to screen socket
            self.screen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.screen_socket.settimeout(10)  # 10 second timeout
            self.screen_socket.connect((self.server_ip, self.screen_port))
            
            # Connect to events socket
            self.events_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.events_socket.settimeout(10)  # 10 second timeout
            self.events_socket.connect((self.server_ip, self.events_port))
            
            # Reset timeout to None for continuous operation
            self.screen_socket.settimeout(None)
            self.events_socket.settimeout(None)
            
            # Start screen receiving thread
            self.receive_screen = ReceiveScreen(self.screen_socket, self.display_panel)
            self.receive_screen.start()
            
            # Start event sending
            self.send_events = SendEvents(self.events_socket, self.display_panel)
            self.send_events.bind_events()
            
            self.logger.info(f"Connected to {server_ip} (screen:{screen_port}, events:{events_port})")
            
        except Exception as e:
            self.logger.error(f"Error connecting to server: {e}", exc_info=True)
            messagebox.showerror("Connection Error", f"Failed to connect to server: {e}")
            self.on_close()
            
    def create_menu(self):
        """Create application menu bar"""
        menubar = tk.Menu(self.window)
        self.window.config(menu=menubar)
        
        # Connection menu
        connection_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Connection", menu=connection_menu)
        connection_menu.add_command(label="Disconnect", command=self.on_close)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Toggle Status Display", 
                             command=lambda: self.receive_screen.toggle_status_display() if self.receive_screen else None)
        
        # Performance menu
        perf_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Performance", menu=perf_menu)
        buffer_menu = tk.Menu(perf_menu, tearoff=0)
        perf_menu.add_cascade(label="Frame Buffer", menu=buffer_menu)
        
        # Buffer size options
        for size in [0, 1, 2, 3, 5, 10]:
            buffer_menu.add_command(
                label=f"{size} {'(No buffering)' if size == 0 else ''}",
                command=lambda s=size: self.receive_screen.set_buffer_size(s) if self.receive_screen else None
            )
            
    def on_close(self):
        """Clean up resources and close the window"""
        try:
            if self.receive_screen:
                self.receive_screen.stop()
                
            if self.send_events:
                self.send_events.stop()
                
            if self.screen_socket:
                self.screen_socket.close()
                
            if self.events_socket:
                self.events_socket.close()
                
            self.logger.info("Disconnected from server")
            
        except Exception as e:
            self.logger.error(f"Error while closing: {e}", exc_info=True)
            
        finally:
            try:
                self.window.destroy()
                # Don't destroy the main root as it's hidden
            except:
                pass