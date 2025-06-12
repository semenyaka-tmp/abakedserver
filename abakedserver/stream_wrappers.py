# abakedserver/stream_wrappers.py

import asyncio
import inspect
import asyncssh
from .logging import configure_logger

logger = configure_logger('abakedserver')


class WrappedSSHMeta(type):
    EXCLUDE_METHODS = {'is_closing', 'close', 'wait_closed', 'at_eof'}
    READ_METHODS_WITH_TIMEOUT = {'read', 'readline', 'readuntil', 'readexactly'}

    def __new__(mcs, name, bases, dct):
        target_base = None
        if name == 'WrappedSSHReader':
            target_base = asyncio.StreamReader
        elif name == 'WrappedSSHWriter':
            target_base = asyncio.StreamWriter

        if target_base:
            for attr_name, attr_value in inspect.getmembers(target_base):
                if (
                    not attr_name.startswith('_')
                    and callable(attr_value)
                    and attr_name not in mcs.EXCLUDE_METHODS
                ):
                    dct[attr_name] = mcs._make_proxy(attr_name, attr_value)

        return super().__new__(mcs, name, bases, dct)

    @staticmethod
    def _make_proxy(method_name, method_impl):
        if inspect.iscoroutinefunction(method_impl):
            async def async_proxy(self, *args, **kwargs):
                # 1. Логика SSH-переподключения СОХРАНЕНА
                if self._server.use_ssh and self._server.conn and self._server.conn.is_closed():
                    if self._server.ssh_config.get('reconnect_on_disconnect'):
                        logger.warning(f"SSH connection closed; attempting to reconnect before {method_name}()")
                        await self._server._reconnect_tunnel()
                    else:
                        raise asyncssh.DisconnectError(11, "SSH connection is closed and reconnect is disabled")  # 11 = SSH_DISCONNECT_BY_APPLICATION
                
                # "Целевой" вызов, который мы будем выполнять
                target_call = getattr(self._stream_object, method_name)(*args, **kwargs)

                # 2. НОВАЯ логика тайм-аута бездействия
                idle_timeout = self._server.timing_config.get('idle_timeout')

                # Применяем тайм-аут только к методам чтения и если он задан
                if idle_timeout is not None and method_name in WrappedSSHMeta.READ_METHODS_WITH_TIMEOUT:
                    try:
                        return await asyncio.wait_for(target_call, timeout=idle_timeout)
                    except asyncio.TimeoutError:
                        logger.warning(f"Client idle timeout ({idle_timeout}s) exceeded.")                        # 11 = SSH_DISCONNECT_BY_APPLICATION
                        return b'' # Имитируем чистое закрытие соединения
                else:
                    # Для остальных методов (write, drain) просто выполняем вызов
                    return await target_call
            return async_proxy
        else:
            def sync_proxy(self, *args, **kwargs):
                if self._server.use_ssh and self._server.conn and self._server.conn.is_closed():
                    raise asyncssh.DisconnectError(11, "SSH connection is closed")
                return getattr(self._stream_object, method_name)(*args, **kwargs)
            return sync_proxy


class WrappedSSHReader(metaclass=WrappedSSHMeta):
    def __init__(self, reader, server):
        self._stream_object = reader
        self._server = server

    def __getattr__(self, name):
        return getattr(self._stream_object, name)


class WrappedSSHWriter(metaclass=WrappedSSHMeta):
    def __init__(self, writer, server):
        self._stream_object = writer
        self._server = server

    def __getattr__(self, name):
        return getattr(self._stream_object, name)
