#!/usr/bin/env python3.12

import os
import sys
import asyncio
import signal
import json
import string

# Добавляем родительскую директорию в sys.path для импорта abakedserver
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from abakedserver import aBakedServer

async def client_handler(reader, writer):
    """
    Обработчик клиента: читает строку, анализирует символы и отправляет JSON-ответ.
    """
    peername = writer.get_extra_info('peername')
    print(f"Server: Client {peername} connected.")

    try:
        while True:
            # 1. Ждем строку от клиента
            data = await reader.readuntil(b'\n')
            
            # Если получили пустые данные (клиент закрыл соединение), выходим
            if not data:
                break

            # 3. Проверяем на ASCII
            try:
                message = data.decode('ascii').strip()
            except UnicodeDecodeError:
                print(f"Server: Received non-ASCII data from {peername}. Disconnecting.")
                writer.write(b"ERROR\n")
                await writer.drain()
                break # Прерываем цикл, чтобы закрыть соединение в блоке finally

            print(f"Server: Received from {peername}: '{message}'")

            # 2. Считаем символы
            counts = {
                "vowels": 0,
                "consonants": 0,
                "digits": 0,
                "punctuation": 0,
                "others": 0
            }
            
            vowels_set = "aeiouAEIOU"
            consonants_set = "bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ"

            for char in message:
                if char in vowels_set:
                    counts["vowels"] += 1
                elif char in consonants_set:
                    counts["consonants"] += 1
                elif char in string.digits:
                    counts["digits"] += 1
                elif char in string.punctuation:
                    counts["punctuation"] += 1
                else:
                    counts["others"] += 1 # Пробелы и прочие символы

            # Формируем и отправляем JSON-ответ
            response = json.dumps(counts)
            print(f"Server: Sending to {peername}: {response}")
            writer.write(response.encode('ascii') + b'\n')
            await writer.drain()

    except asyncio.IncompleteReadError:
        print(f"Server: Client {peername} disconnected.")
    except Exception as e:
        print(f"Server: An error occurred with client {peername}: {e}")
    finally:
        print(f"Server: Closing connection for {peername}.")
        writer.close()
        await writer.wait_closed()


async def main(port: int):
    """
    Основная функция для запуска TCP-сервера.
    """

    def shutdown_handler(sig: signal.Signals):
        print(f"Received shutdown signal: {sig.name}. Starting graceful shutdown...")
        shutdown_event.set()

    def ignore_handler(sig: signal.Signals):
        print(f"Received signal: {sig.name}. Ignoring.")

    # here we will manage signal catching

    shutdown_signals = (signal.SIGABRT, signal.SIGINT, signal.SIGQUIT, signal.SIGTERM)
    ignore_signals   = (signal.SIGHUP,signal.SIGTSTP)

    shutdown_event   = asyncio.Event()

    loop             = asyncio.get_running_loop()

    for sig in shutdown_signals:
        loop.add_signal_handler(sig, shutdown_handler, sig)
    for sig in ignore_signals:
        loop.add_signal_handler(sig, ignore_handler, sig)

    # Сервер работает только в режиме TCP, поэтому ssh_config не нужен
    server = aBakedServer(
        host='0.0.0.0',
        port=port
    )

    try:
        async with await server.start_server(client_handler):
            print(f"Server: TCP server listening on port {port}. Connect with 'nc localhost {port}'.")
            await shutdown_event.wait()  # Ждем сигнала или типа того
    except Exception as e:
        print(f"Server: Failed to start: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <port>")
        sys.exit(1)

    try:
        server_port = int(sys.argv[1])
        if not 1 <= server_port <= 65535:
            raise ValueError
    except ValueError:
        print("Error: Port must be an integer between 1 and 65535.")
        sys.exit(1)
    
    asyncio.run(main(port=server_port))
