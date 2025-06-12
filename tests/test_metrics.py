import pytest
import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from abakedserver import aBakedServer

pytestmark = [pytest.mark.asyncio, pytest.mark.metrics]

async def test_metrics_collection(echo_client_handler):
    """Проверяет базовый сбор метрик после одного успешного соединения."""
    server = aBakedServer(host='localhost', port=0)
    metrics = None
    
    async with await server.start_server(echo_client_handler):
        port = server.server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection('localhost', port)
        writer.write(b"hello")
        await writer.drain()
        await reader.read(1024)
        writer.close()
        await writer.wait_closed()
        
        # Ждем агрегации ВНУТРИ блока, пока сервер работает
        await asyncio.sleep(server.metrics._metrics_interval + 0.1)
        metrics = await server.metrics.get_metrics()
    
    assert metrics is not None
    assert metrics['connections_total'] == 1
    assert metrics['active_connections'] == 0
    assert len(metrics['connection_durations']) == 1
    assert metrics['connection_stats']['count'] == 1
    assert metrics['connection_stats']['mean'] > 0

async def test_metrics_reset(echo_client_handler):
    """Проверяет, что сброс метрик обнуляет все счетчики."""
    server = aBakedServer(host='localhost', port=0)
    
    async with await server.start_server(echo_client_handler):
        port = server.server.sockets[0].getsockname()[1]
        _, writer = await asyncio.open_connection('localhost', port)
        writer.close()
        await writer.wait_closed()

        # Дожидаемся сбора метрик перед сбросом
        await asyncio.sleep(server.metrics._metrics_interval + 0.1)
        await server.metrics.reset_metrics()
        
        metrics = await server.metrics.get_metrics()
        assert metrics['connections_total'] == 0
        assert metrics['active_connections'] == 0
        assert metrics['connection_durations'] == []
    
    # Проверяем еще раз после закрытия сервера
    final_metrics = await server.metrics.get_metrics()
    assert final_metrics['connections_total'] == 0

async def test_metrics_duration_outliers(variable_sleep_client_handler_factory):
    """
    Проверяет стратегию 'outliers', запуская три соединения параллельно.
    """
    metrics_config = {
        'retention_strategy': 'outliers',
        'max_durations': 2,
        'interval': 0.1 # Уменьшаем интервал для быстрого теста
    }
    server = aBakedServer(host='localhost', port=0, metrics_config=metrics_config)
    metrics = None

    handler_queue = asyncio.Queue()
    await handler_queue.put(variable_sleep_client_handler_factory(sleep_duration=0.05))
    await handler_queue.put(variable_sleep_client_handler_factory(sleep_duration=0.25))
    await handler_queue.put(variable_sleep_client_handler_factory(sleep_duration=0.15))

    async def dispatcher_handler(reader, writer):
        handler_to_run = await handler_queue.get()
        await handler_to_run(reader, writer)

    async def connect_and_wait(port):
        try:
            reader, writer = await asyncio.open_connection('localhost', port)
            await reader.read()
            writer.close()
            await writer.wait_closed()
        except ConnectionResetError:
            pass

    async with await server.start_server(dispatcher_handler):
        port = server.server.sockets[0].getsockname()[1]
        
        tasks = [connect_and_wait(port) for _ in range(3)]
        await asyncio.gather(*tasks)

        # Ждем агрегации ВНУТРИ блока
        await asyncio.sleep(server.metrics._metrics_interval + 0.2)
        metrics = await server.metrics.get_metrics()

    assert metrics is not None
    assert len(metrics['connection_durations']) == 2
    
    durations = sorted(metrics['connection_durations'], reverse=True)
    assert durations[0] > 0.20
    assert durations[1] > 0.10

# tests/test_metrics.py

# ... (существующие импорты и тесты) ...

async def test_metrics_manager_lifecycle():
    """
    Проверяет многократные запуски и остановки менеджера метрик.
    Покрывает ветки `if not self._metrics_task` и `if self._metrics_task`.
    """
    metrics_manager = aBakedServer(host='localhost', port=0).metrics

    # Проверяем, что повторные вызовы не вызывают ошибок
    await metrics_manager.start()
    assert metrics_manager._running and not metrics_manager._metrics_task.done()
    
    await metrics_manager.start() # Повторный вызов на работающем
    await metrics_manager.stop()
    assert not metrics_manager._running
    
    await metrics_manager.stop() # Повторный вызов на остановленном
    await metrics_manager.start() # Рестарт
    assert metrics_manager._running
    
    await metrics_manager.stop()


async def test_error_metric_collection():
    """
    Проверяет, что ошибки соединения корректно записываются в метрики.
    Покрывает ветку `self._pending_metrics['errors'].extend(errors)`.
    """
    metrics_manager = aBakedServer(host='localhost', port=0).metrics

    await metrics_manager.start()
    await metrics_manager.record_connection(duration=0.1, errors=['TestError'])
    
    # Ждем агрегации
    await asyncio.sleep(metrics_manager._metrics_interval + 0.1)

    metrics = await metrics_manager.get_metrics()
    await metrics_manager.stop()

    assert metrics['connection_errors'] == ['TestError']
