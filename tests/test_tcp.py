import pytest
import asyncio
import sys
import os
import logging
from abakedserver import aBakedServer

logger = logging.getLogger('abakedserver.test')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

pytestmark = [pytest.mark.asyncio, pytest.mark.tcp]

async def test_tcp_server_start_stop(tcp_server, echo_client_handler):
    async with await tcp_server.start_server(echo_client_handler):
        assert tcp_server.server is not None
        assert tcp_server._running

async def test_tcp_client_interaction(tcp_server, echo_client_handler):
    async with await tcp_server.start_server(echo_client_handler):
        port = tcp_server.server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection('localhost', port)
        writer.write(b"hello")
        await writer.drain()
        data = await reader.read(1024)
        assert data == b"HELLO"
        writer.close()
        await writer.wait_closed()

async def test_tcp_max_concurrent_connections(controlled_client_handler_factory):
    server = aBakedServer(host='localhost', port=0, max_concurrent_connections=2)
    client_handler, handler_control = controlled_client_handler_factory()
    connections = []
    
    async with await server.start_server(client_handler):
        port = server.server.sockets[0].getsockname()[1]
        try:
            for _ in range(2):
                r, w = await asyncio.open_connection('localhost', port)
                connections.append((r, w))
            
            await asyncio.sleep(0.1)
            assert server._conn_num == 2

            r_rej, w_rej = await asyncio.open_connection('localhost', port)
            assert await r_rej.read(100) == b''
            w_rej.close()
            await w_rej.wait_closed()

            assert server._conn_num == 2
        finally:
            handler_control.release_all()
            for r, w in connections:
                if not w.is_closing():
                    w.close()
                    await w.wait_closed()

async def test_tcp_multiple_rejections(controlled_client_handler_factory):
    server = aBakedServer(host='localhost', port=0, max_concurrent_connections=1)
    client_handler, handler_control = controlled_client_handler_factory()
    
    async with await server.start_server(client_handler):
        port = server.server.sockets[0].getsockname()[1]
        r_main, w_main = await asyncio.open_connection('localhost', port)
        try:
            await asyncio.sleep(0.1)
            assert server._conn_num == 1

            for _ in range(2):
                r_rej, w_rej = await asyncio.open_connection('localhost', port)
                assert await r_rej.read(100) == b''
                w_rej.close()
                await w_rej.wait_closed()
            
            await asyncio.sleep(server.metrics._metrics_interval + 0.1)
            metrics = await server.metrics.get_metrics()
            assert metrics['rejected_connections_total'] == 2
        finally:
            handler_control.release_all()
            if not w_main.is_closing():
                w_main.close()
                await w_main.wait_closed()

