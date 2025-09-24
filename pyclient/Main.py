import tkinter as tk
from tkinter import simpledialog, messagebox
from authenticate import Authenticate
import logging
import socket
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("remote_desktop_client.log"),
        logging.StreamHandler()
    ]
)

class ClientMain:
    def __init__(self):
        self.logger = logging.getLogger("ClientMain")
        self.root = tk.Tk()
        self.root.title("Remote Desktop Client")
        self.root.withdraw()  # Hide the root window
        
        # Ask for server IP
        self.server_ip = simpledialog.askstring("Server IP", 
                                               "Enter the server IP address:",
                                               parent=self.root)
        
        if self.server_ip:
            # Clean up the IP address - remove any whitespace
            self.server_ip = self.server_ip.strip()
            
            # Validate IP address format
            if self.is_valid_ip(self.server_ip):
                self.logger.info(f"Connecting to server: {self.server_ip}")
                # Start authentication process
                self.authenticate = Authenticate(self.server_ip, self.root)
            else:
                self.logger.error(f"Invalid IP address format: {self.server_ip}")
                messagebox.showerror("Invalid IP", 
                                    f"'{self.server_ip}' is not a valid IP address.\n\nPlease enter a valid IPv4 address (e.g., 192.168.1.100)")
                self.root.destroy()
        else:
            self.logger.info("No server IP provided, exiting")
            self.root.destroy()
    
    def is_valid_ip(self, ip):
        """Validate the format of an IPv4 address"""
        # Simple regex pattern for IPv4 validation
        pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        if not re.match(pattern, ip):
            return False
            
        # Check that each octet is between 0 and 255
        octets = ip.split('.')
        for octet in octets:
            try:
                num = int(octet)
                if num < 0 or num > 255:
                    return False
            except ValueError:
                return False
                
        return True
            
    def run(self):
        if hasattr(self, 'authenticate'):
            self.root.mainloop()

if __name__ == "__main__":
    client = ClientMain()
    client.run()