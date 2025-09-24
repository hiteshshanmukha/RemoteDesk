import tkinter as tk
import socket
import logging
from tkinter import messagebox
from create_frame import CreateFrame

class Authenticate:
    def __init__(self, server_ip, root):
        self.logger = logging.getLogger("Authenticate")
        self.server_ip = server_ip
        self.main_root = root
        self.port = 5000
        self.client_socket = None
        
        # Create authentication window
        self.auth_window = tk.Toplevel(root)
        self.auth_window.title("Authentication")
        self.auth_window.geometry("300x150")
        self.auth_window.resizable(False, False)
        self.auth_window.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.create_widgets()
        
    def create_widgets(self):
        tk.Label(self.auth_window, text="Remote Desktop Authentication", 
                font=("Arial", 12)).pack(pady=10)
        
        password_frame = tk.Frame(self.auth_window)
        password_frame.pack(pady=10)
        
        tk.Label(password_frame, text="Password:").grid(row=0, column=0, padx=5)
        self.password_entry = tk.Entry(password_frame, show="*")
        self.password_entry.grid(row=0, column=1, padx=5)
        self.password_entry.bind("<Return>", lambda event: self.authenticate())
        
        login_button = tk.Button(self.auth_window, text="Login", command=self.authenticate)
        login_button.pack(pady=10)
        
    def authenticate(self):
        password = self.password_entry.get()
        if not password:
            messagebox.showerror("Error", "Password cannot be empty")
            return
            
        try:
            # Connect to server
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.settimeout(10)  # 10 second timeout
            
            self.logger.info(f"Attempting to connect to {self.server_ip}:{self.port}")
            self.client_socket.connect((self.server_ip, self.port))
            
            # Wait for prompt
            prompt = self.client_socket.recv(1024).decode()
            self.logger.info(f"Received: {prompt}")
            
            # Send password
            self.client_socket.send(password.encode())
            
            # Get response
            response = self.client_socket.recv(1024).decode()
            self.logger.info(f"Authentication response: {response}")
            
            if "successful" in response:
                # Successful authentication
                ports_data = self.client_socket.recv(1024).decode()
                screen_port, events_port = map(int, ports_data.split(','))
                
                self.logger.info(f"Received ports: screen={screen_port}, events={events_port}")
                
                # Close authentication window
                self.auth_window.destroy()
                
                # Start main application
                CreateFrame(self.server_ip, screen_port, events_port, self.main_root)
            else:
                # Failed authentication
                messagebox.showerror("Authentication Failed", "Invalid password")
                self.password_entry.delete(0, tk.END)
                self.client_socket.close()
                self.client_socket = None
                
        except socket.gaierror as e:
            error_msg = f"Could not resolve the hostname or IP address: {self.server_ip}"
            self.logger.error(f"DNS resolution error: {e}")
            messagebox.showerror("Connection Error", error_msg)
            if self.client_socket:
                self.client_socket.close()
                self.client_socket = None
                
        except socket.timeout:
            messagebox.showerror("Connection Timeout", "Server did not respond in time")
            self.logger.error("Connection timeout during authentication")
            if self.client_socket:
                self.client_socket.close()
                self.client_socket = None
                
        except ConnectionRefusedError:
            messagebox.showerror("Connection Failed", "Could not connect to server")
            self.logger.error(f"Connection refused to {self.server_ip}:{self.port}")
            if self.client_socket:
                self.client_socket.close()
                self.client_socket = None
                
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {e}")
            self.logger.error(f"Authentication error: {e}", exc_info=True)
            if self.client_socket:
                self.client_socket.close()
                self.client_socket = None
            
    def on_close(self):
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
        self.auth_window.destroy()
        self.main_root.destroy()