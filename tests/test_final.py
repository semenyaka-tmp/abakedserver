import pytest
import asyncio
from unittest.mock import AsyncMock, Mock

from abakedserver import aBakedServer, WrappedSSHReader
import abakedserver.abaked_server
import asyncssh # Добавляем для типа исключения

pytestmark = [pytest.mark.asyncio]

# --- Существующие тесты из вашего файла ---

async def test_close_server_with_no_clients(echo_client_handler):
    """
    Проверяет, что сервер корректно закрывается, если к нему никто не подключился.
    """
    server = aBakedServer(host='localhost', port=0)
    
    async with await server.start_server(echo_client_handler):
        assert server._running

    assert not server._running


async def test_close_handles_generic_ssh_exception(ssh_server, echo_client_handler, caplog):
    """
    Проверяет обработку ОБЩЕГО исключения при закрытии SSH-соединения.
    """
    async with await ssh_server.start_server(echo_client_handler):
        ssh_server.conn.wait_closed.side_effect = ValueError("Something unexpected happened")

    assert "An error occurred while waiting for SSH connection to close" in caplog.text

async def test_reconnect_loop_final_attempt(mocker):
    """
    Проверяет последнюю итерацию цикла переподключения.
    """
    ssh_config = {'reconnect_attempts': 1, 'ssh_key_path': 'k', 'remote_bind_host': 'h', 'remote_bind_port': 9, 'ssh_user': 'u', 'ssh_host': 'h'}
    server = aBakedServer(host='localhost', port=0, ssh_config=ssh_config)
    
    mocker.patch.object(server, '_setup_tunnel', side_effect=RuntimeError("Failure"))
    mocker.patch('asyncio.sleep')

    server._running = True
    
    # Создаем обычный Mock вместо AsyncMock для conn
    server.conn = Mock()
    # is_closed() должен возвращать обычное булево значение, а не корутину
    server.conn.is_closed.return_value = True

    with pytest.raises(RuntimeError):
        await server._reconnect_tunnel()

    asyncio.sleep.assert_not_called()

async def test_check_permissions_key_does_not_exist(mocker):
    """
    Проверяет случай, когда check_key_permissions=True, но ключ не существует.
    Покрывает: abaked_server.py, ветка else для `if os.path.exists`.
    """
    ssh_config = {
        'ssh_host': 'h', 'ssh_user': 'u', 'ssh_key_path': 'k',
        'remote_bind_host': 'h', 'remote_bind_port': 9,
        'check_key_permissions': True
    }
    server = aBakedServer(host='localhost', port=0, ssh_config=ssh_config)
    
    # Имитируем, что файл НЕ существует
    mocker.patch('os.path.exists', return_value=False)
    # isfile тоже должен вернуть False, чтобы дойти до нужной ошибки
    mocker.patch('os.path.isfile', return_value=False)

    with pytest.raises(FileNotFoundError):
        await server.start_server(None)


async def test_error_metric_collection(mocker):
    """
    Проверяет, что ошибки соединения корректно записываются в метрики.
    Покрывает: metrics.py, ветка `extend(errors)`.
    """
    metrics_manager = aBakedServer(host='localhost', port=0).metrics
    mocker.patch.object(metrics_manager, '_update_metrics_periodically')

    await metrics_manager.record_connection(duration=0.1, errors=['TestError'])
    
    assert metrics_manager._pending_metrics['errors'] == ['TestError']


async def test_metrics_stop_before_start():
    """
    Проверяет вызов .stop() на менеджере метрик, который не был запущен.
    Покрывает: metrics.py, ветка `if self._metrics_task:`.
    """
    metrics_manager = aBakedServer(host='localhost', port=0).metrics
    # Вызов .stop() на незапущенном менеджере не должен вызывать ошибок
    await metrics_manager.stop()


async def test_no_reconnect_flag_raises_error(ssh_server, echo_client_handler):
    """
    Проверяет, что при reconnect_on_disconnect=False выбрасывается ошибка.
    Покрывает: stream_wrappers.py, ветка `else` для `reconnect_on_disconnect`.
    """
    async with await ssh_server.start_server(echo_client_handler):
        ssh_server.conn.is_closed.return_value = True
        ssh_server.ssh_config['reconnect_on_disconnect'] = False

        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        wrapped_reader = WrappedSSHReader(mock_reader, ssh_server)

        with pytest.raises(asyncssh.DisconnectError):
            await wrapped_reader.read(100)
