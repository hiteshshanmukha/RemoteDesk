import tkinter as tk
from tkinter import messagebox
import socket
from create_frame import CreateFrame

class Authenticate:
    def __init__(self, server_ip, root):
        self.server_ip = server_ip
        self.main_root = root
        self.port = 5000
        
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
            self.client_socket.connect((self.server_ip, self.port))
            
            # Receive authentication prompt
            prompt = self.client_socket.recv(1024).decode()
            
            # Send password
            self.client_socket.send(password.encode())
            
            # Get authentication result
            result = self.client_socket.recv(1024).decode()
            
            if "successful" in result:
                # Get screen and events ports
                ports_data = self.client_socket.recv(1024).decode()
                screen_port, events_port = map(int, ports_data.split(','))
                
                # Close authentication window
                self.auth_window.destroy()
                
                # Create remote desktop frame
                self.create_frame = CreateFrame(self.server_ip, screen_port, events_port, self.main_root)
            else:
                messagebox.showerror("Authentication Failed", 
                                     "Incorrect password. Please try again.")
                self.client_socket.close()
                
        except Exception as e:
            messagebox.showerror("Connection Error", 
                                f"Failed to connect to server: {e}")
            
    def on_close(self):
        self.auth_window.destroy()
        self.main_root.destroy()