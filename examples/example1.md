# Manual Testing Guide for `abakedserver` with `server1.py` and `client1.py` on macOS 15

This guide provides detailed instructions for manually testing the `abakedserver` Python module using two small programs, `server1.py` and `client1.py`, located in the `examples/` subfolder, designed for critical systems like nuclear station management. The server receives messages from the client, responds with "No!", and sends "Go to bed, it is {current time}" every 2 seconds. The client sends "Are we there yet?" every 5 seconds. Both print all sent and received messages to the console with timestamps. The server accepts a port and mode (`tcp` or `ssh`) via command-line arguments, and the client accepts a port. The guide is tailored for macOS 15 (Sequoia), addressing its networking and security specifics, and includes steps to simulate TCP and SSH connection failures using `pfctl` (macOS’s packet filter) to test failure and recovery scenarios.

## Overview

- **Purpose**: Verify `ABakedServer`’s message handling, periodic sending, connection management, and failure recovery in TCP or SSH-tunneled environments.
- **Programs**:
  - `server1.py`: Runs an `ABakedServer` instance, accepts a port (`<port>`) and mode (`tcp` or `ssh`), responds to client messages, and sends periodic messages.
  - `client1.py`: Connects to the server at the specified port, sends periodic messages, and receives responses.
- **Location**: Both programs are in the `examples/` subfolder.
- **Command-Line Arguments**:
  - `server1.py <port> <mode>`: `<port>` is the listening port (1–65535 for specific port, 0 for dynamic allocation in tests).
  - `client1.py <port>`: `<port>` matches the server’s port (for SSH, use the `remote_bind_port`).
- **Failure Testing**: Uses `pfctl` to block TCP or SSH traffic, simulating initial or mid-operation failures, and restores the firewall state.
- **Requirements**: Python 3.8+, macOS 15, local `abakedserver` module, OpenSSH for SSH mode, network access for localhost.
- **Output**: Console prints showing message exchanges, errors, and recovery, confirming correct behavior.

## Prerequisites

To ensure smooth execution on macOS 15, complete the following setup steps:

1. **Install Python**:
   - Install Python 3.8+ (preferably 3.12) via Homebrew:
     ```bash
     brew install python@3.12
     ```
   - Verify installation:
     ```bash
     python3.12 --version
     ```
     Expected output: `Python 3.12.x`.

2. **Project Setup**:
   - Ensure the `abakedserver` module is in the project root, with `server1.py` and `client1.py` in the `examples/` subfolder. The structure should be:
     ```
     project_root/
     ├── abakedserver/
     │   ├── __init__.py
     │   ├── abaked_server.py
     ├── tests/
     ├── examples/
     │   ├── server1.py
     │   ├── client1.py
     │   ├── example1.md
     ```
   - Save `server1.py` and `client1.py` in `examples/`.
   - Verify `abakedserver/__init__.py` exists to make it a Python package.
   - Ensure `sys.path.insert` in `server1.py` points to the parent directory (`project_root`).

3. **Network Permissions**:
   - macOS 15’s firewall may block localhost connections. Temporarily disable it for testing:
     ```bash
     sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off
     ```
   - Alternatively, allow Python in System Settings:
     - Navigate to System Settings > Network > Firewall > Options.
     - Add `/usr/local/bin/python3.12` (adjust path based on Homebrew installation, typically `/opt/homebrew/bin/python3.12`).
   - Re-enable after testing:
     ```bash
     sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate on
     ```
   - For failure testing, `pfctl` will be used, requiring `sudo` privileges.

4. **OpenSSH Setup (for SSH Mode)**:
   - Enable OpenSSH for SSH-tunneled testing:
     ```bash
     sudo systemsetup -setremotelogin on
     ```
   - Configure `sshd` to listen on port 2222:
     - Backup and edit `/etc/ssh/sshd_config`:
       ```bash
       sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak
       sudo nano /etc/ssh/sshd_config
       ```
       Add or modify:
       ```
       Port 2222
       ```
     - Restart `sshd`:
       ```bash
       sudo launchctl unload /System/Library/LaunchDaemons/ssh.plist
       sudo launchctl load /System/Library/LaunchDaemons/ssh.plist
       ```
     - Verify port 2222 is listening:
       ```bash
       sudo netstat -an | grep 2222
       ```
   - Generate an SSH key if not present:
     ```bash
     ssh-keygen -t rsa -f ~/.ssh/id_rsa -N ""
     ```
   - Add to `authorized_keys`:
     ```bash
     cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
     chmod 600 ~/.ssh/authorized_keys
     ```
   - Test SSH access:
     ```bash
     ssh -p 2222 $(whoami)@localhost echo "test"
     ```
     If prompted for a password, ensure `~/.ssh/authorized_keys` is correct.

## Running the Programs

Follow these steps to run `server1.py` and `client1.py` in TCP or SSH mode, observing their interaction. Programs are executed from the `examples/` subfolder.

1. **Choose a Port**:
   - Select a port between 1 and 65535 (e.g., `49152`) for manual testing. Use a specific port to ensure predictable binding in production.
   - Avoid using `port=0` for manual testing, as it requests a dynamic port (used in automated tests for conflict-free execution).
   - Avoid well-known ports (<1024) unless running with `sudo` (e.g., `sudo python3.12 examples/server1.py 49152 tcp`).
   - For SSH mode, the port is used as the `remote_bind_port`.

2. **Start the Server**:
   - Open a terminal and navigate to the `examples/` subfolder:
     ```bash
     cd project_root/examples
     ```
   - Run in TCP mode:
     ```bash
     python3.12 server1.py 49152 tcp
     ```
     Or in SSH mode:
     ```bash
     python3.12 server1.py 49152 ssh
     ```
   - Expected output (TCP mode):
     ```
     Server: Listening on localhost:49152 (mode: tcp) at 05:00:00
     ```
   - For SSH mode, ensure the SSH server is running on `localhost:2222`. Output:
     ```
     Server: Listening on localhost:49152 (mode: ssh) at 05:00:00
     ```
   - If the server fails to start (e.g., port in use, SSH error), it prints an error and exits:
     ```
     Server: Failed to start: [error message] at 05:00:00
     ```
   - Keep the terminal open; the server runs until stopped with `Ctrl+C`.

3. **Start the Client**:
   - Open a new terminal and navigate to `examples/`:
     ```bash
     cd project_root/examples
     ```
   - Run the client with the same port:
     - For TCP mode:
       ```bash
       python3.12 client1.py 49152
       ```
     - For SSH mode, use the same port (the `remote_bind_port`):
       ```bash
       python3.12 client1.py 49152
       ```
   - Expected output:
     ```
     Client: Connected to localhost:49152 at 05:00:01
     ```
   - If connection fails (e.g., wrong port, server not running), it prints:
     ```
     Client: Connection failed: [error message] at 05:00:01
     ```

4. **Expected Output**:
   - **Server Console** (example, times vary):
     ```
     Server: Listening on localhost:49152 (mode: tcp) at 05:00:00
     Server: Client ('127.0.0.1', 49153) connected at 05:00:01
     Server: Sending to ('127.0.0.1', 49153): Go to bed, it is 05:00:01
     Server: Received from ('127.0.0.1', 49153): Are we there yet?
     Server: Sending to ('127.0.0.1', 49153): No!
     Server: Sending to ('127.0.0.1', 49153): Go to bed, it is 05:00:03
     Server: Received from ('127.0.0.1', 49153): Are we there yet?
     Server: Sending to ('127.0.0.1', 49153): No!
     ...
     ```
   - **Client Console** (example, times vary):
     ```
     Client: Connected to localhost:49152 at 05:00:01
     Client: Received: Go to bed, it is 05:00:01
     Client: Sending: Are we there yet?
     Client: Received: No!
     Client: Received: Go to bed, it is 05:00:03
     Client: Sending: Are we there yet?
     Client: Received: No!
     ...
     ```
   - **Behavior**:
     - Client sends "Are we there yet?" every ~5 seconds (slight async delays normal).
     - Server responds with "No!" immediately.
     - Server sends "Go to bed, it is {time}" every ~2 seconds.
     - All messages are printed with `print`, including timestamps and client address (server-side).

5. **Stopping the Programs**:
   - **Client**: Press `Ctrl+C` in the client terminal. Expected output:
     ```
     Client: Server disconnected at 05:00:10
     Client: Connection closed at 05:00:10
     ```
   - **Server**: Press `Ctrl+C`