import os
import sys
import asyncio
import asyncssh
import time
from typing import Dict, Optional, Any
from asyncssh.connection import SSHClientConnectionOptions

from .logging import configure_logger
from .stream_wrappers import WrappedSSHReader, WrappedSSHWriter
from .metrics import MetricsManager
from .utils import check_that

logger = configure_logger('abakedserver')

class aBakedServer:
    # ... (код __init__, _setup_tunnel без изменений) ...
    def __init__(self, host: str, port: int,
                 max_concurrent_connections: Optional[int] = None,
                 ssh_config: Optional[Dict] = None,
                 metrics_config: Optional[Dict] = None,
                 timing_config: Optional[Dict] = None,
                 suppress_client_errors: bool = True):
        
        logger.debug(f"Initializing aBakedServer: host={host}, port={port}")
        check_that(host, 'is not empty string', f"Host must be a non-empty string, got {host}")
        check_that(port, 'is non-negative', f"Port must be a non-negative integer, got {port}")
        check_that(max_concurrent_connections, 'is int or none', "max_concurrent_connections must be a positive integer or None")
        if max_concurrent_connections is not None:
            check_that(max_concurrent_connections, 'is positive', "max_concurrent_connections must be a positive integer")
        check_that(suppress_client_errors, 'is bool', "suppress_client_errors must be a boolean")

        self.ssh_config = {
            'known_hosts': None,
            'keepalive_interval': 60, 'keepalive_count_max': 3,
            'reconnect_on_disconnect': True, 'reconnect_attempts': 5,
            'reconnect_backoff': 1.0, 'reconnect_backoff_factor': 2.0,
            'check_key_permissions': False, 'ssh_tun_timeout': 30.0,
            **(ssh_config or {})
        }

        self.timing_config = {
            'idle_timeout': None,
            'close_timeout': 1.0,
            'ssh_close_timeout': 5.0,
            **(timing_config or {})
        }
        self.metrics_config = metrics_config or {}

        self.host, self.port = host, int(port)
        self.use_ssh = 'ssh_host' in self.ssh_config
        self.max_concurrent_connections = max_concurrent_connections
        self.suppress_client_errors = suppress_client_errors
        
        self.server = self.tunnel = self.conn = None
        self._running = False
        self._conn_num = 0
        self._active_connections = {}
        self._reconnect_lock = asyncio.Lock()

        self.metrics = MetricsManager(
            host=self.host, port=self.port, use_ssh=self.use_ssh,
            ssh_host=self.ssh_config.get('ssh_host', ''),
            metrics_config=self.metrics_config
        )
        logger.debug("aBakedServer initialized successfully")

    async def _setup_tunnel(self):
        logger.debug("Setting up SSH tunnel")
        required_keys = {'ssh_user', 'ssh_key_path', 'ssh_host', 'remote_bind_host', 'remote_bind_port'}
        if not required_keys.issubset(self.ssh_config.keys()):
            raise ValueError(f"Missing SSH config keys: {required_keys - set(self.ssh_config.keys())}")
        
        key_path = self.ssh_config['ssh_key_path']
        if self.ssh_config.get('check_key_permissions') and os.name == 'posix':
            if os.path.exists(key_path):
                permissions = os.stat(key_path).st_mode
                if permissions & 0o077:
                    raise PermissionError(
                        f"Unprotected private key file for {key_path}! "
                        f"Permissions are too open: {oct(permissions)[-3:]}"
                    )
        
        if not os.path.isfile(key_path):
            raise FileNotFoundError(f"SSH key file not found: {key_path}")
        
        ssh_options = {
            'username': self.ssh_config['ssh_user'],
            'client_keys': [key_path],
            'host': self.ssh_config['ssh_host'],
            'port': self.ssh_config.get('ssh_port', 22),
            'known_hosts': self.ssh_config.get('known_hosts'),
            'keepalive_interval': self.ssh_config.get('keepalive_interval'),
            'keepalive_count_max': self.ssh_config.get('keepalive_count_max'),
        }

        if self.conn and self.conn.is_closed():
            self.conn.close()

        try:
            options = SSHClientConnectionOptions(**ssh_options)
            self.conn = await asyncio.wait_for(asyncssh.connect(options=options), timeout=self.ssh_config['ssh_tun_timeout'])
            
            self.tunnel = await self.conn.forward_remote_port(
                self.ssh_config['remote_bind_host'],
                self.ssh_config['remote_bind_port'],
                self.host,
                self.port
            )
            logger.info(f"SSH tunnel established to {self.ssh_config['ssh_host']}")
        except (asyncio.TimeoutError, asyncssh.Error) as exc:
            raise RuntimeError(f"SSH connection failed: {exc}") from exc

    async def start_server(self, client_handler):
        logger.debug("Starting server")
        async def connection_handler(reader, writer):
            # ... (connection_handler без изменений) ...
            conn_id = id(writer)
            reject_connection = False
            
            async with self.metrics.lock:
                if self.max_concurrent_connections is not None and self._conn_num >= self.max_concurrent_connections:
                    reject_connection = True
                else:
                    self._conn_num += 1
                    self._active_connections[conn_id] = writer
            
            if reject_connection:
                await self.metrics.record_rejection()
                writer.close()
                return

            start_time = time.monotonic()
            errors = []
            try:
                smart_reader = WrappedSSHReader(reader, self)
                smart_writer = WrappedSSHWriter(writer, self)
                
                await client_handler(smart_reader, smart_writer)
            except Exception as e:
                errors.append(type(e).__name__)
                if not self.suppress_client_errors and not isinstance(e, (asyncio.TimeoutError, ConnectionResetError, asyncssh.DisconnectError)):
                    raise
            finally:
                duration = time.monotonic() - start_time
                await self.metrics.record_connection(duration, errors)
                if not writer.is_closing():
                    writer.close()
                async with self.metrics.lock:
                    if conn_id in self._active_connections:
                        self._conn_num -= 1
                        del self._active_connections[conn_id]

        self._running = True
        await self.metrics.start()
        
        # --- ИСПРАВЛЕННАЯ ЛОГИКА ЗАПУСКА ("ТРАНЗАКЦИЯ") ---
        self.server = await asyncio.start_server(connection_handler, self.host, self.port)
        
        if self.port == 0:
            self.port = self.server.sockets[0].getsockname()[1]
        
        logger.info(f"Server TCP listener started on {self.host}:{self.port}")
        
        if self.use_ssh:
            try:
                await self._setup_tunnel()
            except Exception as e:
                # Если настройка туннеля провалилась, останавливаем TCP-сервер
                logger.error(f"SSH tunnel setup failed. Shutting down TCP listener. Error: {e}")
                self.server.close()
                await self.server.wait_closed()
                # И "пробрасываем" ошибку дальше, чтобы пользователь знал о сбое
                raise

        return self

    # ... (остальные методы close, _reconnect_tunnel и т.д. без изменений) ...
    async def close(self):
        logger.debug("Closing server")
        self._running = False

        if self._active_connections:
            logger.debug(f"Closing {len(self._active_connections)} active client connection(s)...")
            active_writers = list(self._active_connections.values())
            for writer in active_writers:
                if not writer.is_closing():
                    writer.close()
            await asyncio.gather(*(w.wait_closed() for w in active_writers if not w.is_closing()), return_exceptions=True)

        if self.server:
            self.server.close()
            await self.server.wait_closed()
            
        if self.tunnel:
            self.tunnel.close()
        if self.conn and not self.conn.is_closed():
            self.conn.close()
            try:
                timeout = self.timing_config.get('ssh_close_timeout', 5.0)
                await asyncio.wait_for(self.conn.wait_closed(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.debug(f"SSH connection wait_closed timed out after {timeout} seconds.")
            except Exception as e:
                logger.info(f"An error occurred while waiting for SSH connection to close: {e}", exc_info=True)
        
        await self.metrics.stop()
        logger.info("Server closed")

    async def _reconnect_tunnel(self):
        async with self._reconnect_lock:
            if not self._running or (self.conn and not self.conn.is_closed()):
                return

            logger.warning("SSH connection lost, attempting to reconnect...")
            attempts = self.ssh_config.get('reconnect_attempts', 5)
            current_delay = self.ssh_config.get('reconnect_backoff', 1.0)
            backoff_factor = self.ssh_config.get('reconnect_backoff_factor', 2.0)
            
            for i in range(attempts):
                try:
                    await self._setup_tunnel()
                    logger.info("SSH tunnel reconnected successfully.")
                    await self.metrics.record_ssh_reconnect(success=True)
                    return
                except Exception as e:
                    logger.error(f"Reconnect attempt {i + 1} failed: {e}")
                    await self.metrics.record_ssh_reconnect(success=False)
                    if i < attempts - 1:
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff_factor
            
            logger.critical("Could not reconnect SSH tunnel. Stopping server.")
            self._running = False
            raise RuntimeError("Could not reconnect SSH tunnel")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()
