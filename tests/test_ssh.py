import pytest
import asyncio
import asyncssh
from unittest.mock import Mock, AsyncMock
import sys
import os
import abakedserver.abaked_server
from abakedserver import aBakedServer

pytestmark = [pytest.mark.asyncio, pytest.mark.ssh]

async def test_ssh_server_start(ssh_server, echo_client_handler):
    """Тестирует запуск и остановку сервера в режиме SSH с моками."""
    async with await ssh_server.start_server(echo_client_handler):
        assert ssh_server.server is not None
        assert ssh_server.conn is not None
        assert ssh_server.tunnel is not None
        assert ssh_server._running
    assert not ssh_server._running

async def test_ssh_connection_timeout(mocker, echo_client_handler):
    """Тестирует обработку тайм-аута при SSH-подключении."""
    ssh_config = {
        'ssh_host': 'r_host', 'ssh_user': 'u', 'ssh_key_path': 'k',
        'remote_bind_host': 'h', 'remote_bind_port': 9,
        'ssh_tun_timeout': 0.1
    }
    server = aBakedServer(host='localhost', port=0, ssh_config=ssh_config)
    
    mocker.patch('os.path.isfile', return_value=True)
    mocker.patch.object(abakedserver.abaked_server, 'SSHClientConnectionOptions', return_value=mocker.MagicMock())
    mocker.patch('asyncssh.connect', side_effect=asyncio.TimeoutError)
    
    try:
        with pytest.raises(RuntimeError, match="SSH connection failed"):
            await server.start_server(echo_client_handler)
    finally:
        await server.close()


async def test_ssh_check_key_permissions_fail(mocker, echo_client_handler):
    """
    Проверяет, что сервер падает при запуске с 'check_key_permissions': True
    и небезопасными правами на файл ключа.
    """
    ssh_config = {
        'ssh_host': 'r_host', 'ssh_user': 'u', 'ssh_key_path': '/fake/key',
        'remote_bind_host': 'h', 'remote_bind_port': 9,
        'check_key_permissions': True
    }
    server = aBakedServer(host='localhost', port=0, ssh_config=ssh_config)

    # Мокаем os.path.exists для входа в блок проверки прав
    mocker.patch('os.path.exists', return_value=True) 
    mocker.patch('os.name', 'posix')
    
    insecure_perms = Mock()
    insecure_perms.st_mode = 0o644 # "Плохие" права
    mocker.patch('os.stat', return_value=insecure_perms)

    mocker.patch.object(abakedserver.abaked_server, 'SSHClientConnectionOptions', return_value=mocker.MagicMock())

    try:
        with pytest.raises(PermissionError, match="Unprotected private key file"):
            await server.start_server(echo_client_handler)
    finally:
        await server.close()


async def test_ssh_check_key_permissions_pass(mocker, echo_client_handler):
    """
    Проверяет, что проверка прав доступа успешно проходит при корректных правах.
    """
    ssh_config = {
        'ssh_host': 'r_host', 'ssh_user': 'u', 'ssh_key_path': '/fake/key',
        'remote_bind_host': 'h', 'remote_bind_port': 9,
        'check_key_permissions': True
    }
    server = aBakedServer(host='localhost', port=0, ssh_config=ssh_config)

    # --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
    # Мокаем ОБЕ проверки: и exists, и isfile
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('os.path.isfile', return_value=True)
    
    mocker.patch('os.name', 'posix')
    
    secure_perms = Mock()
    secure_perms.st_mode = 0o600 # "Хорошие" права
    mocker.patch('os.stat', return_value=secure_perms)

    mocker.patch.object(abakedserver.abaked_server, 'SSHClientConnectionOptions', return_value=mocker.MagicMock())
    mocker.patch('asyncssh.connect', new_callable=AsyncMock)

    try:
        # Проверяем, что сервер успешно стартует и НЕ выбрасывает PermissionError
        async with asyncio.timeout(0.1): 
            await server.start_server(echo_client_handler)
    except asyncio.TimeoutError:
        # Успешный выход по таймауту означает, что ошибки не было
        pass 
    finally:
        await server.close()
