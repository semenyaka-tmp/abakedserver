import asyncio
import pytest
import asyncssh
from unittest.mock import AsyncMock, Mock

# Импортируем сам модуль, чтобы использовать patch.object - это самый надежный способ
import abakedserver.abaked_server
from abakedserver.abaked_server import aBakedServer

@pytest.fixture
def echo_client_handler():
    """Простой обработчик-эхо, который ничего не делает, просто существует."""
    async def handler(reader, writer):
        pass
    return handler


@pytest.mark.asyncio
async def test_ssh_reconnect(echo_client_handler, mocker):
    """
    Тест УСПЕШНОГО переподключения. Проверяет, что объект соединения меняется.
    """
    mocker.patch('os.path.isfile', return_value=True)
    mocker.patch.object(abakedserver.abaked_server, 'SSHClientConnectionOptions', return_value=mocker.MagicMock())

    # Настраиваем два разных мока для "старого" и "нового" соединения
    initial_conn = AsyncMock(spec=asyncssh.SSHClientConnection)
    initial_conn.is_closed = Mock(return_value=False)
    initial_conn.close = Mock()
    # ВАЖНО: У ПЕРВОГО соединения тоже должен быть этот метод, чтобы он не упал при первом запуске
    initial_conn.forward_remote_port = AsyncMock(return_value=Mock(spec=asyncssh.SSHListener))

    reconnected_conn = AsyncMock(spec=asyncssh.SSHClientConnection)
    reconnected_conn.is_closed = Mock(return_value=False)
    reconnected_conn.close = Mock()
    reconnected_conn.forward_remote_port = AsyncMock(return_value=Mock(spec=asyncssh.SSHListener))

    # Настраиваем `connect`, чтобы он по очереди возвращал наши моки
    mocker.patch('asyncssh.connect', new=AsyncMock(side_effect=[initial_conn, reconnected_conn]))

    server = aBakedServer(host='localhost', port=0, ssh_config={'ssh_key_path': '/path/to/key', 'remote_bind_host': 'h', 'remote_bind_port': 9, 'ssh_user': 'u', 'ssh_host': 'h'})

    # Запускаем сервер, чтобы он установил ПЕРВОЕ соединение
    async with await server.start_server(echo_client_handler):
        assert server.conn is initial_conn
        original_conn_id = id(server.conn)

        # Имитируем разрыв
        initial_conn.is_closed.return_value = True

        # Запускаем переподключение
        await server._reconnect_tunnel()

        # Проверяем, что соединение было заменено на новое
        assert server.conn is reconnected_conn
        assert id(server.conn) != original_conn_id


@pytest.mark.asyncio
async def test_ssh_reconnect_failure(mocker):
    """
    Тест ПОЛНОГО отказа в переподключении (например, неверный пароль).
    """
    mocker.patch('os.path.isfile', return_value=True)
    mocker.patch.object(abakedserver.abaked_server, 'SSHClientConnectionOptions', return_value=mocker.MagicMock())
    # `connect` всегда будет падать с ошибкой
    mocker.patch('asyncssh.connect', side_effect=asyncssh.PermissionDenied("Auth failed"))

    ssh_config = {'reconnect_attempts': 2, 'ssh_key_path': '/path/to/key', 'remote_bind_host': 'h', 'remote_bind_port': 9, 'ssh_user': 'u', 'ssh_host': 'h'}
    server = aBakedServer(host='localhost', port=0, ssh_config=ssh_config)

    # Настраиваем "упавшее" соединение
    server._running = True
    server.conn = AsyncMock(spec=asyncssh.SSHClientConnection)
    server.conn.is_closed = Mock(return_value=True)
    server.conn.close = Mock()

    # Проверяем, что сервер сдается после всех попыток
    with pytest.raises(RuntimeError, match="Could not reconnect SSH tunnel"):
        await server._reconnect_tunnel()

    # Проверяем, что `close` был вызван для каждой попытки
    assert server.conn.close.call_count == ssh_config['reconnect_attempts']


@pytest.mark.asyncio
async def test_ssh_reconnect_reverse_tunnel_failure(mocker):
    """
    Тест отказа на этапе СОЗДАНИЯ ТУННЕЛЯ (connect успешен, а forward_remote_port - нет).
    """
    mocker.patch('os.path.isfile', return_value=True)
    mocker.patch.object(abakedserver.abaked_server, 'SSHClientConnectionOptions', return_value=mocker.MagicMock())

    # Мок, который вернется из `connect`
    mock_conn = AsyncMock(spec=asyncssh.SSHClientConnection)
    mock_conn.is_closed = Mock(return_value=False)
    mock_conn.close = Mock()
    # `forward_remote_port` падает с ошибкой
    mock_conn.forward_remote_port.side_effect = asyncssh.ChannelOpenError(1, "bind failed")

    mocker.patch('asyncssh.connect', new=AsyncMock(return_value=mock_conn))

    ssh_config = {'reconnect_attempts': 2, 'ssh_key_path': '/path/to/key', 'remote_bind_host': 'h', 'remote_bind_port': 9, 'ssh_user': 'u', 'ssh_host': 'h'}
    server = aBakedServer(host='localhost', port=0, ssh_config=ssh_config)

    # Настраиваем "упавшее" соединение
    server._running = True
    initial_mock_conn = AsyncMock(spec=asyncssh.SSHClientConnection)
    initial_mock_conn.is_closed = Mock(return_value=True)
    initial_mock_conn.close = Mock()
    server.conn = initial_mock_conn

    with pytest.raises(RuntimeError, match="Could not reconnect SSH tunnel"):
        await server._reconnect_tunnel()

    # --- ИСПРАВЛЕНИЕ ЛОГИКИ ТЕСТА ---
    # `close` будет вызван только один раз для самого первого "упавшего" соединения.
    # При последующих неудачных попытках `server.conn` заменится на `mock_conn`,
    # у которого `is_closed` вернет False, и `close` для него вызван не будет.
    initial_mock_conn.close.assert_called_once()

@pytest.mark.asyncio
async def test_reconnect_on_healthy_connection(mocker):
    """
    Проверяет, что _reconnect_tunnel ничего не делает, если соединение активно.
    """
    server = aBakedServer(host='localhost', port=0, ssh_config={'ssh_key_path': 'k'})
    
    # Создаем мок "здорового" соединения
    server.conn = AsyncMock(spec=asyncssh.SSHClientConnection)
    server.conn.is_closed.return_value = False
    server._running = True

    # "Шпионим" за методом _setup_tunnel, чтобы убедиться, что он НЕ будет вызван
    mocker.patch.object(server, '_setup_tunnel')

    # Вызываем переподключение
    await server._reconnect_tunnel()

    # Проверяем, что попытки установить туннель не было
    server._setup_tunnel.assert_not_called()


@pytest.mark.asyncio
async def test_ssh_no_reconnect_on_disconnect(mocker):
    """
    Проверяет, что при reconnect_on_disconnect=False обертка выбрасывает
    исключение, а не пытается переподключиться.
    """
    # Настраиваем сервер с отключенным реконнектом
    ssh_config = {'reconnect_on_disconnect': False, 'ssh_host': 'h', 'ssh_user': 'u'}
    server = aBakedServer(host='localhost', port=0, ssh_config=ssh_config)
    
    # Создаем мок "упавшего" соединения
    server.conn = AsyncMock(spec=asyncssh.SSHClientConnection)
    server.conn.is_closed.return_value = True

    # Создаем мок ридера и нашу обертку
    from abakedserver.stream_wrappers import WrappedSSHReader
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    wrapped_reader = WrappedSSHReader(mock_reader, server)

    # Проверяем, что при попытке чтения будет выброшено исключение DisconnectError
    with pytest.raises(asyncssh.DisconnectError):
        await wrapped_reader.read(100)

@pytest.mark.asyncio
async def test_reconnect_does_nothing_on_healthy_connection(mocker):
    """
    Проверяет, что _reconnect_tunnel ничего не делает, если соединение активно.
    Покрывает ветку `if not self._running or ...`
    """
    server = aBakedServer(host='localhost', port=0, ssh_config={'ssh_key_path': 'k'})
    
    # Создаем мок "здорового" соединения
    server.conn = AsyncMock(spec=asyncssh.SSHClientConnection)
    server.conn.is_closed.return_value = False
    server._running = True

    # "Шпионим" за методом _setup_tunnel
    mocker.patch.object(server, '_setup_tunnel')

    # Вызываем переподключение
    await server._reconnect_tunnel()

    # Проверяем, что реальной попытки установить туннель не было
    server._setup_tunnel.assert_not_called()
