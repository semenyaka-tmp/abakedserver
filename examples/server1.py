#!/usr/bin/env python3.12

import os
import sys
import json
import string
import asyncio
from datetime import datetime
import signal
import logging 

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from abakedserver import aBakedServer
from abakedserver.logging import configure_logger

logger = configure_logger('abakedserver')


async def client_handler(reader, writer):
    peername = writer.get_extra_info('peername')
    print(f"Server: Client {peername} connected at {datetime.now().strftime('%H:%M:%S')}")

    async def send_periodic_messages():
        while True:
            try:
                current_time = datetime.now().strftime("%H:%M:%S")
                message = f"Go to bed, it is {current_time}"
                print(f"Server: Sending to {peername}: {message}")
                writer.write(message.encode() + b'\n')
                await writer.drain()
                await asyncio.sleep(2)
            except (ConnectionError, asyncio.CancelledError):
                print(f"Server: Periodic message task stopped for {peername}")
                break

    periodic_task = asyncio.create_task(send_periodic_messages())

    try:
        while True:
            data = await reader.readuntil(b'\n')
            message = data.decode().strip()
            print(f"Server: Received from {peername}: {message}")
            response = "No!"
            print(f"Server: Sending to {peername}: {response}")
            writer.write(response.encode() + b'\n')
            await writer.drain()
    except asyncio.IncompleteReadError:
        print(f"Server: Client {peername} disconnected (EOF) at {datetime.now().strftime('%H:%M:%S')}")
    except ConnectionError as e:
        print(f"Server: Client {peername} disconnected due to error: {e} at {datetime.now().strftime('%H:%M:%S')}")
    finally:
        periodic_task.cancel()
        try:
            await periodic_task
        except asyncio.CancelledError:
            pass
        writer.close()
        try:
            await writer.wait_closed()
        except ConnectionError:
            pass
        print(f"Server: Connection closed for {peername} at {datetime.now().strftime('%H:%M:%S')}")


async def main(port: int, mode: str):
    """Start the server with specified port and mode (tcp or ssh)."""

    def shutdown_handler(sig: signal.Signals):
        logger.info(f"Received shutdown signal: {sig.name}. Starting graceful shutdown...")
        shutdown_event.set()

    def ignore_handler(sig: signal.Signals):
        logger.info(f"Received signal: {sig.name}. Ignoring.")

    # here we will manage signal catching

    shutdown_signals = (signal.SIGABRT, signal.SIGINT, signal.SIGQUIT, signal.SIGTERM)
    ignore_signals   = (signal.SIGHUP,signal.SIGTSTP)

    shutdown_event   = asyncio.Event()
    
    loop             = asyncio.get_running_loop()

    for sig in shutdown_signals:
        loop.add_signal_handler(sig, shutdown_handler, sig)
    for sig in ignore_signals:
        loop.add_signal_handler(sig, ignore_handler, sig)

    ssh_config = None
    if mode == 'ssh':
        ssh_config = {
            'ssh_host': 'localhost',
            'ssh_port': 2222,
            'ssh_user': os.getlogin(),
            'ssh_key_path': os.path.expanduser('~/.ssh/id_rsa'),
            'remote_bind_host': '127.0.0.1',
            'remote_bind_port': port,
            'known_hosts': None,
            'host_key_checking': 'auto-add'
        }

    timing_config = {
        'idle_timeout': 3600
    }

    server = aBakedServer(
        host='localhost',
        port=port,
        ssh_config=ssh_config,
        timing_config=timing_config
    )
    
    try:
        async with await server.start_server(client_handler):
            print(f"Server: Listening on localhost:{port} (mode: {mode}) at {datetime.now().strftime('%H:%M:%S')}")
            await shutdown_event.wait()
    except (OSError, asyncssh.Error, RuntimeError) as e:
        print(f"Server: Failed to start: {e} at {datetime.now().strftime('%H:%M:%S')}")
        sys.exit(1)
    finally:
        print("Server has been shut down.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <port> <mode> (mode: tcp or ssh)")
        sys.exit(1)
    try:
        parsed_port = int(sys.argv[1])
        if not 1 <= parsed_port <= 65535:
            raise ValueError
    except ValueError:
        print("Error: Port must be an integer between 1 and 65535")
        sys.exit(1)
    parsed_mode = sys.argv[2].lower()
    if parsed_mode not in ['tcp', 'ssh']:
        print("Error: Mode must be 'tcp' or 'ssh'")
        sys.exit(1)
    
    # This is SIGINT which is caught, but will leave it as a precaution
    try:
        asyncio.run(main(port=parsed_port, mode=parsed_mode))
    except KeyboardInterrupt:
        print("\nServer shut down forcefully.")
