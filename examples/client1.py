#!/usr/bin/env python3.12

import asyncio
from datetime import datetime
import sys

async def main():
    """Connect to server, send periodic messages, and receive responses."""
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <port>")
        sys.exit(1)

    try:
        port = int(sys.argv[1])
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        print("Error: Port must be an integer between 1 and 65535")
        sys.exit(1)

    try:
        reader, writer = await asyncio.open_connection('localhost', port)
        print(f"Client: Connected to localhost:{port} at {datetime.now().strftime('%H:%M:%S')}")
    except (ConnectionRefusedError, OSError) as e:
        print(f"Client: Connection failed: {e} at {datetime.now().strftime('%H:%M:%S')}")
        sys.exit(1)

    async def send_periodic_messages():
        while True:
            try:
                message = "Are we there yet?"
                print(f"Client: Sending: {message}")
                writer.write(message.encode() + b'\n')
                await writer.drain()
                await asyncio.sleep(5)  # Every 5 seconds
            except ConnectionError as e:
                print(f"Client: Server disconnected during send: {e} at {datetime.now().strftime('%H:%M:%S')}")
                break

    periodic_task = asyncio.create_task(send_periodic_messages())

    try:
        while True:
            data = await reader.readuntil(b'\n')
            message = data.decode().strip()
            print(f"Client: Received: {message}")
    except asyncio.IncompleteReadError:
        print(f"Client: Server disconnected (EOF) at {datetime.now().strftime('%H:%M:%S')}")
    except ConnectionError as e:
        print(f"Client: Server disconnected: {e} at {datetime.now().strftime('%H:%M:%S')}")
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
        print(f"Client: Connection closed at {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    asyncio.run(main())
