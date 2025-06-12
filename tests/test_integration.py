import pytest
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from abakedserver import aBakedServer

ssh_key_path = os.path.expanduser('tests/sshd_test_config/ssh_host_rsa_key')
run_real_ssh_str = os.environ.get('RUN_REAL_SSH_TESTS', 'false')
real_ssh_tests_enabled = run_real_ssh_str.lower() in ('true', '1', 'yes')

real_ssh_test_marker = pytest.mark.skipif(
    not real_ssh_tests_enabled,
    reason="RUN_REAL_SSH_TESTS is not set to 1"
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

async def test_integration_tcp(echo_client_handler):
    server = aBakedServer(host='localhost', port=0)
    async with await server.start_server(echo_client_handler):
        port = server.server.sockets[0].getsockname()[1]
        r, w = await asyncio.open_connection('localhost', port)
        w.write(b"hello tcp")
        await w.drain()
        data = await r.read(1024)
        assert data == b"HELLO TCP"
        w.close()
        await w.wait_closed()

async def test_integration_ssh_mocked(ssh_server, echo_client_handler):
    async with await ssh_server.start_server(echo_client_handler):
        port = ssh_server.server.sockets[0].getsockname()[1]
        r, w = await asyncio.open_connection('localhost', port)
        w.write(b"hello mock")
        await w.drain()
        data = await r.read(1024)
        assert data == b"HELLO MOCK"
        w.close()
        await w.wait_closed()

@real_ssh_test_marker
async def test_integration_ssh_real(echo_client_handler):
    assert os.path.exists(ssh_key_path), f"SSH key not found at {ssh_key_path}"
    ssh_config = {
        'ssh_host': 'localhost',
        'ssh_port': 2222,
        'ssh_user': os.getlogin(),
        'ssh_key_path': ssh_key_path,
        'remote_bind_host': '127.0.0.1',
        'remote_bind_port': 9999
    }
    server = aBakedServer(host='localhost', port=0, ssh_config=ssh_config)
    async with await server.start_server(echo_client_handler):
        r, w = await asyncio.open_connection('localhost', 9999)
        w.write(b"hello real")
        await w.drain()
        data = await r.read(1024)
        assert data == b"HELLO REAL"
        w.close()
        await w.wait_closed()

