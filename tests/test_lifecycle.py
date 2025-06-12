import pytest
import asyncio
from unittest.mock import AsyncMock

from abakedserver import aBakedServer
import abakedserver.abaked_server

pytestmark = [pytest.mark.asyncio]


async def test_startup_fails_on_missing_key(mocker):
    """
    Проверяет, что запуск падает, если файл SSH-ключа не найден.
    Покрывает ветку `if not os.path.isfile(key_path):` в _setup_tunnel.
    """
    ssh_config = {'ssh_host': 'h', 'ssh_user': 'u', 'ssh_key_path': 'k', 'remote_bind_host': 'h', 'remote_bind_port': 9}
    server = aBakedServer(host='localhost', port=0, ssh_config=ssh_config)
    
    # Имитируем отсутствие файла
    mocker.patch('os.path.isfile', return_value=False)
    
    with pytest.raises(FileNotFoundError):
        await server.start_server(None)


async def test_close_handles_ssh_timeout(ssh_server, echo_client_handler):
    """
    Проверяет обработку таймаута при закрытии SSH-соединения.
    Покрывает ветку `except asyncio.TimeoutError` в методе close().
    """
    async with await ssh_server.start_server(echo_client_handler):
        # Имитируем, что ожидание закрытия соединения "зависает"
        ssh_server.conn.wait_closed.side_effect = asyncio.TimeoutError

    # Тест должен успешно завершиться, не упав с ошибкой,
    # так как исключение должно быть поймано и залогировано.
    assert not ssh_server._running

async def test_close_on_failed_startup(mocker):
    """
    Проверяет, что .close() работает, даже если сервер не смог полностью запуститься.
    """
    ssh_config = {
        'ssh_host': 'host',
        'ssh_user': 'user',
        'ssh_key_path': 'key',
        'remote_bind_host': 'remote_host',
        'remote_bind_port': 9999
    }
    server = aBakedServer(host='localhost', port=0, ssh_config=ssh_config)

    # Имитируем падение при настройке туннеля
    mocker.patch.object(server, '_setup_tunnel', side_effect=RuntimeError("Tunnel failed"))

    try:
        # Проверяем, что start_server падает с ошибкой
        with pytest.raises(RuntimeError, match="Tunnel failed"):
            await server.start_server(None)

        # --- ИСПРАВЛЕНИЕ АССЕРТОВ ---
        # Проверяем состояние сервера ПОСЛЕ сбоя
        assert server.conn is None     # SSH-соединение не было установлено
        assert server.tunnel is None   # Туннель не был создан
        assert server.server is not None # А вот TCP-сервер УСПЕЛ запуститься!

    finally:
        # Проверяем, что вызов close() на частично запущенном сервере не вызывает ошибок
        await server.close()
