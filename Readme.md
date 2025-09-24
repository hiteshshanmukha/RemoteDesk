# Remote Desktop Application

This document provides instructions for executing the Python Remote Desktop Application on both Windows and Unix-based operating systems.

## Prerequisites

- **Python Installation:**
  - Ensure you have Python 3.6+ installed on your system.
  - You can download Python from the [official website](https://www.python.org/downloads/).

- **Required Python Libraries:**
  - Install the necessary dependencies using pip:
    ```
    pip install pillow numpy opencv-python pyautogui keyboard mss socket
    ```

- **Operating System Compatibility:**
  - The application is compatible with Windows, macOS, Linux, and other Unix-based operating systems.
  - Ensure that your system meets the minimum requirements for running Python applications.

- **Network Connectivity:**
  - Both the client and server machines should be connected to the same network.
  - Ensure that there are no firewall restrictions preventing communication between the client and server.

## Steps to Execute

### Server Setup:

1. **Navigate to the Server Directory:**
   - Open a terminal or command prompt.
   - Change the directory to where the server script is located.

2. **Run the Server Script:**
   - Execute the following command:
     ```
     python server.py
     ```
   - The server will start, and you will see a message indicating the server is running.

### Client Setup:

1. **Navigate to the Client Directory:**
   - Open another terminal or command prompt.
   - Change the directory to where the client script is located.

2. **Run the Client Script:**
   - Execute the following command:
     ```
     python client.py
     ```

3. **Enter Server IP and Password:**
   - When prompted, enter the server's IP address and the password set on the server-side for authentication.

4. **Access Remote Desktop:**
   - Once authenticated, the client will display the server's desktop, and you can start controlling it remotely.

## Dependencies

- None. The application requires Python and the listed libraries to be installed.

## Contributing

Contributions are welcome! If you find any issues or have suggestions for improvements, feel free to open an issue or create a pull request.
