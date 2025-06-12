import pytest
import asyncio
import asyncssh
from unittest.mock import AsyncMock

from abakedserver import WrappedSSHReader, WrappedSSHWriter

pytestmark = [pytest.mark.asyncio, pytest.mark.proxy]


async def test_idle_timeout_on_read(ssh_server):
    """
    Проверяет, что обертка ридера корректно обрабатывает таймаут бездействия.
    """
    # 1. Настройка
    server = ssh_server
    server.timing_config['idle_timeout'] = 0.01

    mock_reader = AsyncMock(spec=asyncio.StreamReader)

    # --- ИСПРАВЛЕНИЕ: Заменяем lambda на полноценную async-функцию ---
    # Эта функция действительно "ждет", имитируя медленного клиента.
    async def slow_read(*args, **kwargs):
        await asyncio.sleep(0.1)
        return b"this data should never be returned"
    
    mock_reader.read.side_effect = slow_read

    # Создаем экземпляр нашей обертки
    wrapped_reader = WrappedSSHReader(mock_reader, server)

    # 2. Действие и Проверка
    data = await wrapped_reader.read(1024)

    # Теперь `wait_for` внутри обертки сработает по таймауту,
    # и вернется ожидаемое значение b''
    assert data == b''


async def test_sync_method_on_disconnected_ssh(ssh_server, echo_client_handler):
    """
    Проверяет вызов СИНХРОННОГО метода на обертке после разрыва SSH-соединения.
    """
    server = ssh_server

    async with await server.start_server(echo_client_handler):
        assert server.conn is not None

        server.conn.is_closed.return_value = True
        server.ssh_config['reconnect_on_disconnect'] = False
        
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        wrapped_writer = WrappedSSHWriter(mock_writer, server)

        with pytest.raises(asyncssh.DisconnectError, match="SSH connection is closed"):
            wrapped_writer.get_extra_info('peername')

async def test_async_method_on_no_reconnect_raises_error(ssh_server, echo_client_handler):
    """
    Проверяет, что вызов АСИНХРОННОГО метода при разрыве и reconnect=False
    также вызывает DisconnectError.
    """
    server = ssh_server
    async with await server.start_server(echo_client_handler):
        server.conn.is_closed.return_value = True
        server.ssh_config['reconnect_on_disconnect'] = False

        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        wrapped_reader = WrappedSSHReader(mock_reader, server)

        with pytest.raises(asyncssh.DisconnectError):
            await wrapped_reader.read(100) # Вызываем async метод

async def test_sync_method_on_healthy_connection(ssh_server, echo_client_handler):
    """
    Проверяет, что вызов синхронного метода на здоровом соединении
    просто работает и не вызывает ошибок.
    """
    server = ssh_server
    async with await server.start_server(echo_client_handler):
        server.conn.is_closed.return_value = False # Соединение активно

        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        # Настраиваем мок, чтобы он что-то возвращал
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        
        wrapped_writer = WrappedSSHWriter(mock_writer, server)
        
        # Проверяем, что вызов проходит до оригинального объекта
        peername = wrapped_writer.get_extra_info('peername')
        assert peername == ('127.0.0.1', 12345)

