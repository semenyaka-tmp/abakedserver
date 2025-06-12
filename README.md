# aBakedServer

![PyPI version](https://img.shields.io/badge/version-0.1.0-blue)
![Python versions](https://img.shields.io/badge/python-3.8+-blue)
![License](https://img.shields.io/badge/license-MIT-License-green)

`aBakedServer` is a robust, asynchronous TCP server for Python, built on `asyncio`. It is designed for reliability and ease of use, featuring optional SSH tunneling, automatic reconnection, idle timeouts, and built-in metrics.

Its primary goal is to provide a solid foundation for network services that require stable, long-running connections, even over unreliable networks.

## Key Features

* **Dual-Mode Operation**: Runs as a standard TCP server or can automatically create and manage a reverse SSH tunnel to expose a local server to an external network.
* **Automatic SSH Reconnection**: If the SSH tunnel connection is lost, the server will automatically try to re-establish it with a configurable exponential backoff strategy.
* **Idle Timeout Handling**: Automatically disconnects clients that are idle (not sending any data) for a configurable period.
* **Graceful Shutdown**: Correctly handles system signals (`SIGINT`, `SIGTERM`) to shut down cleanly, closing all active connections.
* **Connection Management**: Can limit the maximum number of concurrent client connections.
* **Built-in Metrics**: Provides a `MetricsManager` to track uptime, connection counts, durations, errors, and SSH health.
* **Transparent Wrappers**: Network streams are wrapped to provide the above features transparently, meaning your application logic (`client_handler`) remains simple and clean.

## Requirements

* Python 3.8+
* `asyncssh>=2.13.0`

## Installation

To install the module from your local project directory, run:

```bash
pip install .
```
Or for development (editable) mode:
```bash
pip install -e .
```

## Quick Start: A Simple Echo Server

This example shows how to create a simple TCP server that echoes back any message it receives in uppercase.

**`my_echo_server.py`**
```python
import asyncio
from abakedserver import aBakedServer

# 1. Define your client handling logic
# This function will be executed for each client that connects.
async def echo_handler(reader, writer):
    """
    Reads data from the client, converts it to uppercase,
    and writes it back.
    """
    peername = writer.get_extra_info('peername')
    print(f"New connection from {peername}")

    try:
        while True:
            # Wait for a line of data from the client
            data = await reader.readuntil(b'\n')
            if not data:
                break # Client disconnected
            
            message = data.decode().strip()
            print(f"Received: {message}")

            response = message.upper() + '\n'
            writer.write(response.encode())
            await writer.drain()

    except asyncio.IncompleteReadError:
        print(f"Client {peername} disconnected.")
    finally:
        writer.close()

# 2. Define the main function to run the server
async def main():
    # Create an instance of the server
    server = aBakedServer(host='0.0.0.0', port=8888)

    # Use 'async with' for automatic startup and shutdown
    try:
        async with await server.start_server(echo_handler):
            print("Echo server is running on port 8888...")
            # Keep the server running forever (or until Ctrl+C)
            await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\nServer shutting down.")

# 3. Run the server
if __name__ == "__main__":
    asyncio.run(main())
```

**How to test it:**
1.  Run the server: `python3 my_echo_server.py`
2.  In a new terminal, connect with `netcat`: `nc localhost 8888`
3.  Type `hello world` and press Enter. The server will respond with `HELLO WORLD`.

---

## Core Concepts

### The `aBakedServer` Class
This is the main class of the module. You create an instance of it, configure it with the desired parameters, and then use its `start_server` method to begin listening for connections. It is designed to be used as an asynchronous context manager (`async with`).

### The `client_handler` Coroutine
This is the heart of your application's logic. It's an `async` function that you write and pass to `server.start_server()`.
* **Signature**: It must accept two arguments: `reader` (`asyncio.StreamReader`) and `writer` (`asyncio.StreamWriter`).
* **Execution**: A new instance of your `client_handler` is created and executed for every single client that connects to the server.
* **Streams**: The `reader` and `writer` objects are special "smart" streams. You use them just like standard `asyncio` streams, but they have the built-in ability to handle idle timeouts and survive SSH reconnects automatically.

---

## Detailed Configuration

The server's behavior is controlled by passing dictionaries to its constructor.

### `aBakedServer` Class Parameters

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `host` | `str` | *N/A* | The network interface to listen on (e.g., `'localhost'`, `'0.0.0.0'`). **Required.** |
| `port` | `int` | *N/A* | The port to listen on (e.g., `8888`). Use `0` to let the OS choose a free port. **Required.** |
| `max_concurrent_connections` | `int` or `None` | `None` | The maximum number of clients that can be connected at the same time. If `None`, the limit is disabled. |
| `ssh_config` | `dict` or `None` | `None` | A dictionary with all SSH-related settings. If provided, the server runs in SSH tunnel mode. |
| `metrics_config` | `dict` or `None` | `None` | A dictionary with settings for the metrics collection system. |
| `timing_config` | `dict` or `None` | `None` | A dictionary with various timeout settings. |
| `suppress_client_errors` | `bool` | `True` | If `True`, exceptions within your `client_handler` are logged but do not crash the server. |

### Timing Configuration (`timing_config`)

This dictionary controls all time-related behavior.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `idle_timeout` | `float` or `None` | `None` | **Idle Timeout.** The number of seconds to wait for a client to send data. If no data is received within this period, the client is disconnected. If `None`, this is disabled. |
| `close_timeout` | `float` | `1.0` | The number of seconds to wait for a standard client TCP connection to gracefully close during server shutdown before giving up. |
| `ssh_close_timeout` | `float` | `5.0` | The number of seconds to wait for the main SSH connection to gracefully close during server shutdown. |

### SSH Configuration (`ssh_config`)

To enable SSH mode, provide this dictionary.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `ssh_host` | `str` | *N/A* | The hostname or IP address of the remote SSH server to connect to. **Required to enable SSH mode.** |
| `ssh_port` | `int` | `22` | The port of the remote SSH server. |
| `ssh_user` | `str` | *N/A* | The username to use for the SSH connection. **Required.** |
| `ssh_key_path` | `str` | *N/A* | The absolute path to your private SSH key file (e.g., `$HOME/.ssh/id_rsa`). **Required.** |
| `remote_bind_host` | `str` | *N/A* | The network interface on the **remote SSH server** where the tunnel entry point will be created (e.g., `'127.0.0.1'`). **Required.** |
| `remote_bind_port` | `int` | *N/A* | The port on the **remote SSH server** where the tunnel entry point will be created. Clients will connect to this port. **Required.** |
| `reconnect_on_disconnect` | `bool` | `True` | If `True`, the server will automatically try to re-establish the SSH tunnel if it disconnects. |
| `reconnect_attempts` | `int` | `5` | The number of times to attempt reconnection before giving up. |
| `reconnect_backoff` | `float` | `1.0` | The initial delay in seconds before the first reconnection attempt. |
| `reconnect_backoff_factor` | `float` | `2.0` | The multiplier for the delay. Each subsequent attempt will wait `current_delay * factor` seconds (exponential backoff). |
| `known_hosts` | `str` or `None` | `None` | Path to a `known_hosts` file for verifying the remote server's identity. If `None`, the server's key is trusted on first use. |
| `check_key_permissions` | `bool` | `False` | If `True` on a POSIX system, the server will check that the private key file has secure permissions (e.g., `600`) before using it. |
| `ssh_tun_timeout` | `float` | `30.0` | The number of seconds to wait for the initial SSH connection to be established before timing out. |

### Metrics Configuration (`metrics_config`)

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `interval` | `float` | `1.0` | The interval in seconds at which pending metrics are aggregated into the main metrics store. |
| `max_durations` | `int` | `1000` | The maximum number of individual connection duration records to store in memory. |
| `retention_strategy` | `str` | `'recent'` | How to handle the `connection_durations` list when it exceeds `max_durations`. `'recent'` keeps the newest records, `'outliers'` keeps the longest-running records. |

---

## Advanced Usage

### Example: SSH Tunnel Mode

In this scenario, `aBakedServer` runs on your local machine but is accessible to the world via `example.com:9999`.

```python
import asyncio
from abakedserver import aBakedServer
import os

# Your client handling logic (e.g., echo_handler)
async def echo_handler(reader, writer):
    peername = writer.get_extra_info('peername')
    print(f"Connection from {peername}")
    try:
        while True:
            data = await reader.readuntil(b'\n')
            if not data: break
            writer.write(data.upper())
            await writer.drain()
    except asyncio.IncompleteReadError:
        print(f"Client {peername} disconnected.")
    finally:
        writer.close()


async def main():
    # Configure the server to create a reverse tunnel
    ssh_settings = {
        'ssh_host': 'example.com', # Your remote server
        'ssh_port': 22,
        'ssh_user': 'myuser',
        'ssh_key_path': os.path.expanduser('~/.ssh/id_rsa_server'),
        'remote_bind_host': '0.0.0.0', # Listen on all interfaces on the remote server
        'remote_bind_port': 9999,      # Clients will connect to this port on example.com
        'reconnect_on_disconnect': True
    }

    # Our local server listens on a random port; the SSH tunnel handles the rest.
    server = aBakedServer(
        host='localhost', 
        port=0, 
        ssh_config=ssh_settings
    )

    try:
        async with await server.start_server(echo_handler):
            print("SSH-tunneled server is running.")
            print("Connect clients to example.com:9999")
            await asyncio.Event().wait()
    except Exception as e:
        print(f"Server failed to start: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Accessing Metrics

You can access the `MetricsManager` instance via `server.metrics` to get real-time statistics.

```python
async def monitor_server():
    server = aBakedServer(host='0.0.0.0', port=8888)
    
    # ... (define echo_handler)
    
    async with await server.start_server(echo_handler):
        for i in range(30):
            await asyncio.sleep(2)
            metrics = await server.metrics.get_metrics()
            print(f"Active connections: {metrics['active_connections']}")
            print(f"Total connections: {metrics['connections_total']}")

# ... run monitor_server ...
```

**Available Metrics Keys:**
* `labels`: Dictionary of labels for the server instance (host, port, etc.).
* `connections_total`: Total number of connections handled since startup/reset.
* `active_connections`: Number of currently active connections.
* `rejected_connections_total`: Number of connections rejected due to `max_concurrent_connections`.
* `connection_errors`: A list of recent exception types that occurred in `client_handler`.
* `connection_durations`: A list of recent connection durations in seconds.
* `connection_stats`: A dictionary with `{'mean', 'max', 'count'}` for durations in the last metrics interval.
* `ssh_reconnects_total`: Total number of SSH reconnect attempts.
* `ssh_reconnect_successes_total`: Total successful SSH reconnects.
* `uptime_seconds`: Server uptime in seconds.

---
## Project Information

* **Author**: abakedserver
* **Homepage**: [https://github.com/yourusername/abakedserver](https://github.com/asemenyaka-tmp/abakedserver)
* **Repository**: [https://github.com/yourusername/abakedserver](https://github.com/asemenyaka-tmp/abakedserver)
* **Issue Tracker**: [https://github.com/yourusername/abakedserver/issues](https://github.com/asemenyaka-tmp/abakedserver/issues)

## License

This project is licensed under the **MIT License**. See the `LICENSE` file for details.
