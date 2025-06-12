import asyncio
from datetime import datetime
from typing import Dict, Optional, List, Any
from copy import deepcopy
from .logging import configure_logger

logger = configure_logger('abakedserver')

class MetricsManager:
    def __init__(self, host: str, port: int, use_ssh: bool, ssh_host: str, metrics_config: Dict):
        
        # Parse config with defaults
        self._metrics_interval = metrics_config.get('interval', 1.0)
        self._max_connection_durations = metrics_config.get('max_durations', 1000)
        self._duration_retention_strategy = metrics_config.get('retention_strategy', 'recent')

        self.lock = asyncio.Lock()
        self._metrics_task = None
        self._running = False
        self._start_time: Optional[datetime] = None
        
        self._metrics_labels = {
            'host': str(host), 'port': str(port),
            'connection_type': 'ssh' if use_ssh else 'tcp',
            'ssh_host': ssh_host or 'n/a'
        }
        self._metrics = self._get_initial_metrics_state()
        self._pending_metrics = self._get_initial_pending_state()

    def _get_initial_metrics_state(self):
        return {
            'connections_total': 0, 'active_connections': 0,
            'connection_errors': [], 'ssh_reconnects_total': 0,
            'ssh_reconnect_successes_total': 0, 'connection_durations': [],
            'connection_stats': {'mean': 0.0, 'max': 0.0, 'count': 0},
            'uptime_seconds': 0.0, 'metrics_task_health': {'restarts': 0},
            'rejected_connections_total': 0
        }

    def _get_initial_pending_state(self):
        return {
            'total': 0, 'active_delta': 0, 'errors': [], 'reconnects': 0,
            'reconnect_successes': 0, 'durations': [], 'rejected': 0
        }

    async def start(self):
        self._running = True
        self._start_time = datetime.now()
        if not self._metrics_task or self._metrics_task.done():
            self._metrics_task = asyncio.create_task(self._update_metrics_periodically())

    async def stop(self):
        self._running = False
        if self._metrics_task:
            self._metrics_task.cancel()
            try:
                await self._metrics_task
            except asyncio.CancelledError:
                pass
        self._metrics_task = None

    async def get_metrics(self) -> Dict[str, Any]:
        async with self.lock:
            # Update uptime before returning
            if self._start_time:
                self._metrics['uptime_seconds'] = (datetime.now() - self._start_time).total_seconds()
            metrics_copy = deepcopy(self._metrics)
            metrics_copy['labels'] = self._metrics_labels
            return metrics_copy

    async def reset_metrics(self):
        async with self.lock:
            self._metrics = self._get_initial_metrics_state()
            self._pending_metrics = self._get_initial_pending_state()
        self._start_time = datetime.now()
        logger.info("Metrics reset successfully")

    async def inc_pending_value(self, field, inc):
        self._pending_metrics[field] += inc

    async def record_ssh_reconnect(self, success: bool):
        async with self.lock:
            self._pending_metrics['reconnects'] += 1
            if success:
                self._pending_metrics['reconnect_successes'] += 1

    async def record_connection(self, duration: float, errors: List[str]):
        async with self.lock:
            self._pending_metrics['total'] += 1
            self._pending_metrics['durations'].append(duration)
            self._pending_metrics['errors'].extend(errors)

    async def record_rejection(self):
        async with self.lock:
            self._pending_metrics['rejected'] += 1

    async def _update_metrics_periodically(self):
        while self._running:
            try:
                await asyncio.sleep(self._metrics_interval)
                async with self.lock:
                    self._metrics['connections_total'] += self._pending_metrics['total']
                    self._metrics['active_connections'] += self._pending_metrics['active_delta']
                    self._metrics['rejected_connections_total'] += self._pending_metrics['rejected']
                    self._metrics['ssh_reconnects_total'] += self._pending_metrics['reconnects']
                    self._metrics['ssh_reconnect_successes_total'] += self._pending_metrics['reconnect_successes']

                    # --- ВОССТАНОВЛЕННАЯ ЛОГИКА ---
                    if self._pending_metrics['durations']:
                        durations = self._pending_metrics['durations']
                        self._metrics['connection_stats'].update({
                            'mean': sum(durations) / len(durations),
                            'max': max(durations),
                            'count': len(durations)
                        })
                        
                        if self._duration_retention_strategy == 'outliers':
                            all_durations = self._metrics['connection_durations'] + durations
                            all_durations.sort(reverse=True)
                            self._metrics['connection_durations'] = all_durations[:self._max_connection_durations]
                        else: # 'recent'
                            combined = self._metrics['connection_durations'] + durations
                            self._metrics['connection_durations'] = combined[-self._max_connection_durations:]
                    
                    if self._pending_metrics['errors']:
                         self._metrics['connection_errors'].extend(self._pending_metrics['errors'])
                         self._metrics['connection_errors'] = self._metrics['connection_errors'][-1000:] # Limit stored errors
                    
                    self._pending_metrics = self._get_initial_pending_state()

            except asyncio.CancelledError:
                break

