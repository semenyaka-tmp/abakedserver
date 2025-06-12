import pytest
import asyncio

from abakedserver import aBakedServer

pytestmark = [pytest.mark.asyncio]


@pytest.fixture
def failing_client_handler():
    """Этот обработчик всегда падает с ошибкой."""
    async def handler(reader, writer):
        raise ValueError("CLIENT_ERROR")
    return handler


async def test_suppress_errors_false_behavior(caplog, failing_client_handler):
    """
    Проверяет поведение при `suppress_client_errors=False`.
    """
    server = aBakedServer(host='localhost', port=0, suppress_client_errors=False)

    async with await server.start_server(failing_client_handler):
        port = server.server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection('localhost', port)
        await reader.read() # Ждем реакции сервера
        writer.close()

    # --- ИСПРАВЛЕНИЕ: Ищем текст, который реально есть в логе ---
    assert "Unhandled exception in client_connected_cb" in caplog.text
    assert "ValueError: CLIENT_ERROR" in caplog.text


async def test_metrics_retention_strategy_recent(variable_sleep_client_handler_factory):
    """
    Проверяет стратегию 'recent' для метрик длительности.
    """
    metrics_config = {
        'retention_strategy': 'recent',
        'max_durations': 2,
        'interval': 0.05
    }
    server = aBakedServer(host='localhost', port=0, metrics_config=metrics_config)

    handlers = [
        variable_sleep_client_handler_factory(0.1),
        variable_sleep_client_handler_factory(0.2),
        variable_sleep_client_handler_factory(0.3)
    ]
    
    async def dispatcher(r, w):
        if handlers:
            await handlers.pop(0)(r, w)

    async def connect_and_wait(port):
        reader, writer = await asyncio.open_connection('localhost', port)
        await reader.read() # Ждем, пока сервер закроет соединение
        writer.close()
        await writer.wait_closed()

    async with await server.start_server(dispatcher):
        port = server.server.sockets[0].getsockname()[1]
        tasks = [connect_and_wait(port) for _ in range(3)]
        await asyncio.gather(*tasks)

        # --- ИСПРАВЛЕНИЕ: Даем фоновой задаче больше времени ---
        # Ждем 3 интервала для надежности
        await asyncio.sleep(server.metrics._metrics_interval * 3) 
        metrics = await server.metrics.get_metrics()
    
    assert metrics is not None
    assert len(metrics['connection_durations']) == 2
    
    durations = sorted(metrics['connection_durations'], reverse=True)
    assert durations[0] > 0.29 # Проверяем, что сохранилось самое новое (0.3с)
    assert durations[1] > 0.19 # и предпоследнее (0.2с)
