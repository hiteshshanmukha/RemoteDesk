import tkinter as tk
from tkinter import simpledialog, messagebox, ttk
import threading
import logging
import socket
import os
import json
import time
from init_connection import InitConnection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("remote_desktop_server.log"),
        logging.StreamHandler()
    ]
)

class ServerMain:
    """
    Main server application with GUI for configuration and monitoring.
    Features:
    - Password configuration and validation
    - Server status monitoring
    - Client connection tracking
    - Configuration saving and loading
    - IP filtering options
    """
    
    def __init__(self):
        self.logger = logging.getLogger("ServerMain")
        
        # Create main window
        self.root = tk.Tk()
        self.root.title("Remote Desktop Server")
        self.root.geometry("500x400")
        self.root.minsize(500, 400)
        
        # Server state
        self.server_running = False
        self.server_thread = None
        self.server_instance = None
        self.active_clients = []
        
        # Default settings
        self.default_settings = {
            'port': 5000,
            'max_clients': 5,
            'allowed_ips': [],
            'banned_ips': [],
            'max_failed_attempts': 5,
            'lockout_time': 300
        }
        
        # Load settings
        self.settings = self.load_settings()
        
        # Create widgets
        self.create_widgets()
        
        # Start status update timer
        self.update_status()
        
        # Handle window closing
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.logger.info("Server application started")
        
    def load_settings(self):
        """Load settings from configuration file."""
        try:
            if os.path.exists('server_config.json'):
                with open('server_config.json', 'r') as f:
                    settings = json.load(f)
                
                # Ensure all keys are present
                for key, value in self.default_settings.items():
                    if key not in settings:
                        settings[key] = value
                        
                return settings
        except Exception as e:
            self.logger.error(f"Error loading settings: {e}")
            
        return self.default_settings.copy()
    
    def save_settings(self):
        """Save settings to configuration file."""
        try:
            with open('server_config.json', 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving settings: {e}")
    
    def create_widgets(self):
        """Create the GUI elements."""
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Main tab
        self.main_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.main_frame, text="Main")
        
        # Settings tab
        self.settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_frame, text="Settings")
        
        # Clients tab
        self.clients_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.clients_frame, text="Clients")
        
        # Setup main tab
        self.setup_main_tab()
        
        # Setup settings tab
        self.setup_settings_tab()
        
        # Setup clients tab
        self.setup_clients_tab()
        
    def setup_main_tab(self):
        """Setup the main server control tab."""
        # Title
        ttk.Label(self.main_frame, text="Remote Desktop Server", 
                 font=("Arial", 16)).pack(pady=10)
        
        # Password frame
        password_frame = ttk.LabelFrame(self.main_frame, text="Server Authentication")
        password_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Password entry
        ttk.Label(password_frame, text="Password:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.password_entry = ttk.Entry(password_frame, show="*", width=30)
        self.password_entry.grid(row=0, column=1, padx=5, pady=5)
        
        # Password strength meter
        ttk.Label(password_frame, text="Strength:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.strength_frame = ttk.Frame(password_frame)
        self.strength_frame.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        
        self.strength_meter = ttk.Progressbar(self.strength_frame, length=200, mode='determinate')
        self.strength_meter.pack(side=tk.LEFT, padx=5)
        
        self.strength_label = ttk.Label(self.strength_frame, text="")
        self.strength_label.pack(side=tk.LEFT, padx=5)
        
        # Bind password entry to strength checker
        self.password_entry.bind("<KeyRelease>", self.check_password_strength)
        
        # Server controls
        controls_frame = ttk.Frame(self.main_frame)
        controls_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.start_button = ttk.Button(controls_frame, text="Start Server", command=self.start_server)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(controls_frame, text="Stop Server", command=self.stop_server, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        # Status frame
        status_frame = ttk.LabelFrame(self.main_frame, text="Server Status")
        status_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Status labels
        self.status_text = tk.StringVar(value="Server not running")
        ttk.Label(status_frame, text="Status:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        ttk.Label(status_frame, textvariable=self.status_text).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        
        self.ip_text = tk.StringVar(value="N/A")
        ttk.Label(status_frame, text="Server IP:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        ttk.Label(status_frame, textvariable=self.ip_text).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        
        self.port_text = tk.StringVar(value=str(self.settings['port']))
        ttk.Label(status_frame, text="Server Port:").grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        ttk.Label(status_frame, textvariable=self.port_text).grid(row=2, column=1, padx=5, pady=5, sticky=tk.W)
        
        self.clients_text = tk.StringVar(value="0")
        ttk.Label(status_frame, text="Connected Clients:").grid(row=3, column=0, padx=5, pady=5, sticky=tk.W)
        ttk.Label(status_frame, textvariable=self.clients_text).grid(row=3, column=1, padx=5, pady=5, sticky=tk.W)
        
        # Get and display local IP
        self.update_local_ip()
    
    def setup_settings_tab(self):
        """Setup the server settings tab."""
        # Network settings frame
        network_frame = ttk.LabelFrame(self.settings_frame, text="Network Settings")
        network_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Port setting
        ttk.Label(network_frame, text="Server Port:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.port_entry = ttk.Entry(network_frame, width=10)
        self.port_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        self.port_entry.insert(0, str(self.settings['port']))
        
        # Max clients setting
        ttk.Label(network_frame, text="Max Clients:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.max_clients_entry = ttk.Entry(network_frame, width=10)
        self.max_clients_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        self.max_clients_entry.insert(0, str(self.settings['max_clients']))
        
        # Security settings frame
        security_frame = ttk.LabelFrame(self.settings_frame, text="Security Settings")
        security_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Failed attempts setting
        ttk.Label(security_frame, text="Max Failed Attempts:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.max_attempts_entry = ttk.Entry(security_frame, width=10)
        self.max_attempts_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        self.max_attempts_entry.insert(0, str(self.settings['max_failed_attempts']))
        
        # Lockout time setting
        ttk.Label(security_frame, text="Lockout Time (seconds):").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.lockout_entry = ttk.Entry(security_frame, width=10)
        self.lockout_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        self.lockout_entry.insert(0, str(self.settings['lockout_time']))
        
        # IP filtering frame
        ip_frame = ttk.LabelFrame(self.settings_frame, text="IP Filtering")
        ip_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Allowed IPs
        ttk.Label(ip_frame, text="Allowed IPs (comma separated, empty for all):").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.allowed_ips_entry = ttk.Entry(ip_frame, width=40)
        self.allowed_ips_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        self.allowed_ips_entry.insert(0, ','.join(self.settings['allowed_ips']))
        
        # Banned IPs
        ttk.Label(ip_frame, text="Banned IPs (comma separated):").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.banned_ips_entry = ttk.Entry(ip_frame, width=40)
        self.banned_ips_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        self.banned_ips_entry.insert(0, ','.join(self.settings['banned_ips']))
        
        # Save settings button
        save_button = ttk.Button(self.settings_frame, text="Save Settings", command=self.save_settings_from_gui)
        save_button.pack(pady=10)
    
    def setup_clients_tab(self):
        """Setup the clients monitoring tab."""
        # Create treeview for clients
        columns = ("ip", "connected_at", "status")
        self.clients_tree = ttk.Treeview(self.clients_frame, columns=columns, show="headings")
        
        # Define headings
        self.clients_tree.heading("ip", text="IP Address")
        self.clients_tree.heading("connected_at", text="Connected At")
        self.clients_tree.heading("status", text="Status")
        
        # Define columns
        self.clients_tree.column("ip", width=150)
        self.clients_tree.column("connected_at", width=150)
        self.clients_tree.column("status", width=100)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(self.clients_frame, orient=tk.VERTICAL, command=self.clients_tree.yview)
        self.clients_tree.configure(yscroll=scrollbar.set)
        
        # Pack elements
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.clients_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Action buttons
        actions_frame = ttk.Frame(self.clients_frame)
        actions_frame.pack(fill=tk.X, pady=5)
        
        refresh_button = ttk.Button(actions_frame, text="Refresh", command=self.refresh_clients)
        refresh_button.pack(side=tk.LEFT, padx=5)
        
        disconnect_button = ttk.Button(actions_frame, text="Disconnect Selected", command=self.disconnect_selected)
        disconnect_button.pack(side=tk.LEFT, padx=5)
        
        ban_button = ttk.Button(actions_frame, text="Ban Selected", command=self.ban_selected)
        ban_button.pack(side=tk.LEFT, padx=5)
    
    def check_password_strength(self, event=None):
        """Check and display password strength."""
        password = self.password_entry.get()
        
        # Calculate strength
        strength = 0
        feedback = ""
        
        if len(password) == 0:
            strength = 0
            feedback = "Enter password"
        elif len(password) < 8:
            strength = 20
            feedback = "Too short"
        else:
            # Start with 20 for minimum length
            strength = 20
            
            # Add points for complexity
            if any(c.islower() for c in password):
                strength += 20
            if any(c.isupper() for c in password):
                strength += 20
            if any(c.isdigit() for c in password):
                strength += 20
            if any(not c.isalnum() for c in password):
                strength += 20
                
            # Determine feedback
            if strength <= 20:
                feedback = "Very weak"
            elif strength <= 40:
                feedback = "Weak"
            elif strength <= 60:
                feedback = "Medium"
            elif strength <= 80:
                feedback = "Strong"
            else:
                feedback = "Very strong"
        
        # Update UI
        self.strength_meter['value'] = strength
        self.strength_label['text'] = feedback
        
        # Set color based on strength
        if strength < 40:
            self.strength_meter['style'] = 'red.Horizontal.TProgressbar'
        elif strength < 70:
            self.strength_meter['style'] = 'yellow.Horizontal.TProgressbar'
        else:
            self.strength_meter['style'] = 'green.Horizontal.TProgressbar'
    
    def update_local_ip(self):
        """Update the displayed local IP address."""
        try:
            # Get local IP by creating a temporary socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            
            self.ip_text.set(local_ip)
        except:
            self.ip_text.set("Could not determine IP")
    
    def start_server(self):
        """Start the server with the configured settings."""
        password = self.password_entry.get()
        
        if not password:
            messagebox.showerror("Error", "Password cannot be empty")
            return
            
        if len(password) < 8:
            result = messagebox.askquestion("Weak Password", 
                                          "Your password is weak. This could make your computer vulnerable. Continue anyway?")
            if result != 'yes':
                return
        
        # Update settings from GUI before starting
        self.save_settings_from_gui()
        
        # Update UI
        self.start_button['state'] = tk.DISABLED
        self.stop_button['state'] = tk.NORMAL
        self.status_text.set("Server starting...")
        self.root.update()
        
        # Create and start server in a separate thread
        try:
            self.server_instance = InitConnection(
                password=password,
                max_clients=self.settings['max_clients']
            )
            
            # Configure server with settings
            self.server_instance.port = self.settings['port']
            self.server_instance.max_failed_attempts = self.settings['max_failed_attempts']
            self.server_instance.lockout_time = self.settings['lockout_time']
            self.server_instance.allowed_ips = self.settings['allowed_ips']
            self.server_instance.banned_ips = self.settings['banned_ips']
            
            # Start server thread
            self.server_thread = threading.Thread(target=self.server_instance.start)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            # Update state
            self.server_running = True
            self.status_text.set("Server running")
            self.port_text.set(str(self.settings['port']))
            
            self.logger.info(f"Server started on port {self.settings['port']}")
            
        except Exception as e:
            self.logger.error(f"Failed to start server: {e}")
            messagebox.showerror("Error", f"Failed to start server: {e}")
            self.start_button['state'] = tk.NORMAL
            self.stop_button['state'] = tk.DISABLED
            self.status_text.set("Server failed to start")
    
    def stop_server(self):
        """Stop the running server."""
        if self.server_instance:
            try:
                self.server_instance.stop()
                self.server_running = False
                self.status_text.set("Server stopped")
                self.clients_text.set("0")
                
                # Update UI
                self.start_button['state'] = tk.NORMAL
                self.stop_button['state'] = tk.DISABLED
                
                # Clear clients list
                self.refresh_clients()
                
                self.logger.info("Server stopped")
                
            except Exception as e:
                self.logger.error(f"Error stopping server: {e}")
                messagebox.showerror("Error", f"Error stopping server: {e}")
        else:
            self.start_button['state'] = tk.NORMAL
            self.stop_button['state'] = tk.DISABLED
            self.status_text.set("Server not running")
    
    def save_settings_from_gui(self):
        """Save settings from GUI inputs."""
        try:
            # Validate and save port
            port = int(self.port_entry.get())
            if not (1024 <= port <= 65535):
                messagebox.showerror("Invalid Port", "Port must be between 1024 and 65535")
                return
            self.settings['port'] = port
            
            # Validate and save max clients
            max_clients = int(self.max_clients_entry.get())
            if not (1 <= max_clients <= 100):
                messagebox.showerror("Invalid Max Clients", "Max clients must be between 1 and 100")
                return
            self.settings['max_clients'] = max_clients
            
            # Validate and save security settings
            max_attempts = int(self.max_attempts_entry.get())
            if not (1 <= max_attempts <= 100):
                messagebox.showerror("Invalid Max Attempts", "Max failed attempts must be between 1 and 100")
                return
            self.settings['max_failed_attempts'] = max_attempts
            
            lockout_time = int(self.lockout_entry.get())
            if not (10 <= lockout_time <= 86400):
                messagebox.showerror("Invalid Lockout Time", "Lockout time must be between 10 and 86400 seconds")
                return
            self.settings['lockout_time'] = lockout_time
            
            # Parse and save IP lists
            allowed_ips = self.allowed_ips_entry.get().strip()
            self.settings['allowed_ips'] = [ip.strip() for ip in allowed_ips.split(',') if ip.strip()]
            
            banned_ips = self.banned_ips_entry.get().strip()
            self.settings['banned_ips'] = [ip.strip() for ip in banned_ips.split(',') if ip.strip()]
            
            # Save to file
            self.save_settings()
            
            messagebox.showinfo("Settings Saved", "Settings have been saved successfully")
            
        except ValueError as e:
            messagebox.showerror("Invalid Input", f"Please enter valid numbers: {e}")
        except Exception as e:
            self.logger.error(f"Error saving settings: {e}")
            messagebox.showerror("Error", f"Failed to save settings: {e}")
    
    def refresh_clients(self):
        """Refresh the clients list display."""
        # Clear existing items
        for item in self.clients_tree.get_children():
            self.clients_tree.delete(item)
            
        # Add active clients if server is running
        if self.server_running and self.server_instance:
            for client in self.server_instance.active_clients:
                connected_time = time.strftime('%Y-%m-%d %H:%M:%S', 
                                             time.localtime(client['connected_at']))
                
                self.clients_tree.insert('', tk.END, values=(
                    client['ip'],
                    connected_time,
                    "Connected"
                ))
    
    def disconnect_selected(self):
        """Disconnect the selected client."""
        selected = self.clients_tree.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please select a client to disconnect")
            return
            
        if not self.server_running or not self.server_instance:
            messagebox.showinfo("Server Not Running", "Server is not running")
            return
            
        for item in selected:
            values = self.clients_tree.item(item, 'values')
            ip = values[0]
            
            # Find and disconnect this client
            for client in self.server_instance.active_clients[:]:
                if client['ip'] == ip:
                    self.server_instance._remove_client(client['id'])
                    break
                    
        # Refresh the list
        self.refresh_clients()
    
    def ban_selected(self):
        """Ban the selected client IP."""
        selected = self.clients_tree.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please select a client to ban")
            return
            
        for item in selected:
            values = self.clients_tree.item(item, 'values')
            ip = values[0]
            
            # Add to banned list if not already there
            if ip not in self.settings['banned_ips']:
                self.settings['banned_ips'].append(ip)
                
                # Update entry in settings tab
                self.banned_ips_entry.delete(0, tk.END)
                self.banned_ips_entry.insert(0, ','.join(self.settings['banned_ips']))
                
                # Refresh clients list
                self.refresh_clients()
                
                self.logger.info(f"IP {ip} banned")
    
    def update_status(self):
        """Update the status display at regular intervals."""
        if self.server_running and self.server_instance:
            # Update connected clients count
            self.clients_text.set(str(len(self.server_instance.active_clients)))
        
        # Repeat after 1 second
        self.root.after(1000, self.update_status)
    
    def on_close(self):
        """Handle window close event."""
        if self.server_running:
            result = messagebox.askquestion("Server Running", 
                                          "The server is currently running. Do you want to stop it and exit?")
            if result == 'yes':
                self.stop_server()
                self.root.destroy()
        else:
            self.root.destroy()

# Start the server application
if __name__ == "__main__":
    server = ServerMain()
    server.run()