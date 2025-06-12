import pytest
import asyncio
from unittest.mock import AsyncMock, Mock
import os
import sys
import logging
import asyncssh # Импортируем для указания spec

logger = logging.getLogger('abakedserver.test')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from abakedserver import aBakedServer

@pytest.fixture
def tcp_server():
    """Фикстура для TCP-сервера."""
    return aBakedServer(host='localhost', port=0)

@pytest.fixture
def ssh_server(mocker):
    """Фикстура для SSH-сервера с полностью замоканным процессом установки туннеля."""
    
    mock_conn = AsyncMock(spec=asyncssh.SSHClientConnection)
    mock_conn.close = Mock()
    mock_conn.is_closed.return_value = False
    
    mock_tunnel = Mock(spec=asyncssh.SSHListener)
    mock_tunnel.close = Mock()

    mock_conn.forward_remote_port = AsyncMock(return_value=mock_tunnel)

    ssh_config = {
        'ssh_host': 'remote_server', 'ssh_port': 22, 'ssh_user': 'user',
        'ssh_key_path': '/path/to/key', 
        'remote_bind_host': '127.0.0.1',
        'remote_bind_port': 9999
    }
    server = aBakedServer(host='localhost', port=0, ssh_config=ssh_config)

    async def fake_setup_tunnel():
        server.conn = mock_conn
        server.tunnel = mock_tunnel
        logger.info("Faked _setup_tunnel completed.")

    mocker.patch.object(server, '_setup_tunnel', new=fake_setup_tunnel)
    
    return server

@pytest.fixture
def echo_client_handler():
    """Простой обработчик-эхо."""
    async def handler(reader, writer):
        try:
            data = await reader.read(100)
            if data:
                writer.write(data.upper())
                await writer.drain()
        finally:
            writer.close()
    return handler

@pytest.fixture
def controlled_client_handler_factory():
    def _factory():
        connection_events = {}
        async def handler(reader, writer):
            conn_id = id(writer)
            event = asyncio.Event()
            connection_events[conn_id] = event
            try:
                await event.wait()
            finally:
                if not writer.is_closing(): writer.close()
        class HandlerControl:
            def release_all(self):
                for event in connection_events.values(): event.set()
        return handler, HandlerControl()
    return _factory

@pytest.fixture
def variable_sleep_client_handler_factory():
    def _factory(sleep_duration=0.1):
        async def handler(reader, writer):
            await asyncio.sleep(sleep_duration)
            if not writer.is_closing(): writer.close()
        return handler
    return _factory

