import tkinter as tk
from tkinter import simpledialog
from authenticate import Authenticate

class ClientMain:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Remote Desktop Client")
        self.root.withdraw()  # Hide the root window
        
        # Ask for server IP
        self.server_ip = simpledialog.askstring("Server IP", 
                                               "Enter the server IP address:",
                                               parent=self.root)
        
        if self.server_ip:
            # Start authentication process
            self.authenticate = Authenticate(self.server_ip, self.root)
        else:
            self.root.destroy()
            
    def run(self):
        if self.server_ip:
            self.root.mainloop()

if __name__ == "__main__":
    client = ClientMain()
    client.run()