import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
import sys
import os
import asyncssh

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from abakedserver import WrappedSSHReader, WrappedSSHWriter

pytestmark = [pytest.mark.asyncio, pytest.mark.proxy]

async def test_wrapped_ssh_reader(ssh_server):
    # Создаем мок для StreamReader
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_reader.read.return_value = b"test"
    
    # Вручную создаем мок для SSH-соединения внутри сервера
    ssh_server.conn = AsyncMock(spec=asyncssh.SSHClientConnection)
    ssh_server.conn.is_closed.return_value = False

    # Тестируем обертку в нормальном режиме
    wrapped_reader = WrappedSSHReader(mock_reader, ssh_server)
    data = await wrapped_reader.read(1024)
    assert data == b"test"

    # --- ИСПРАВЛЕНИЕ ---
    # Имитируем разрыв соединения и отключаем переподключение,
    # чтобы гарантированно проверить выбрасывание DisconnectError.
    ssh_server.ssh_config['reconnect_on_disconnect'] = False
    ssh_server.conn.is_closed.return_value = True
    
    with pytest.raises(asyncssh.DisconnectError):
        await wrapped_reader.read(1024)

async def test_wrapped_ssh_writer(ssh_server):
    # Создаем мок для StreamWriter
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    
    # Вручную создаем мок для SSH-соединения внутри сервера
    ssh_server.conn = AsyncMock(spec=asyncssh.SSHClientConnection)
    ssh_server.conn.is_closed.return_value = False

    # Тестируем обертку в нормальном режиме
    wrapped_writer = WrappedSSHWriter(mock_writer, ssh_server)
    wrapped_writer.write(b"test")
    await wrapped_writer.drain()
    mock_writer.write.assert_called_with(b"test")

    # --- ИСПРАВЛЕНИЕ ---
    # Имитируем разрыв соединения и отключаем переподключение.
    ssh_server.ssh_config['reconnect_on_disconnect'] = False
    ssh_server.conn.is_closed.return_value = True
    
    with pytest.raises(asyncssh.DisconnectError):
        wrapped_writer.write(b"test")

