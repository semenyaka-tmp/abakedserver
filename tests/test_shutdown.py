import pytest
import asyncio
from unittest.mock import AsyncMock

from abakedserver import aBakedServer
import abakedserver.abaked_server

pytestmark = [pytest.mark.asyncio]


async def test_close_on_tcp_server(tcp_server, echo_client_handler):
    """
    Проверяет, что .close() на обычном TCP-сервере не вызывает ошибок.
    Покрывает ветки `if self.tunnel:` и `if self.conn...`
    """
    async with await tcp_server.start_server(echo_client_handler):
        assert tcp_server.tunnel is None
        assert tcp_server.conn is None
    
    # Главная проверка - что после выхода из блока не возникло ошибок
    assert not tcp_server._running


async def test_close_with_ssh_wait_timeout(ssh_server, echo_client_handler, caplog):
    """
    Проверяет обработку таймаута при закрытии SSH-соединения.
    Покрывает ветку `except asyncio.TimeoutError` в методе close().
    """
    async with await ssh_server.start_server(echo_client_handler):
        # Имитируем, что ожидание закрытия соединения "зависает"
        ssh_server.conn.wait_closed.side_effect = asyncio.TimeoutError

    # Тест должен успешно завершиться, не упав с ошибкой.
    # Мы также можем проверить, что в лог было записано предупреждение.
    assert "SSH connection wait_closed timed out" in caplog.text
    assert not ssh_server._running
