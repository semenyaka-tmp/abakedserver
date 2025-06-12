# Руководство по тестированию `abakedserver`

Это документ представляет собой комплексное руководство по тестированию пакета `abakedserver`.

## Обзор

Тесты `abakedserver` разделены на модули и используют `pytest` для выполнения. Они проверяют основной функционал, пограничные случаи и сценарии интеграции, используя моки для изоляции от внешних зависимостей.

## Конфигурация сервера

Конструктор `aBakedServer` был переработан для повышения читаемости и гибкости. Параметры теперь сгруппированы в словари:

- **`max_concurrent_connections: int`**: Общий лимит одновременных подключений.
- **`ssh_config: dict`**: Содержит все параметры, связанные с SSH.
  - `ssh_host`, `ssh_port`, `ssh_user`, `ssh_key_path`, `remote_bind_host`, `remote_bind_port`
  - `known_hosts`, `host_key_checking`, `keepalive_interval`, `keepalive_count_max`, `reconnect_on_disconnect`, `reconnect_attempts`, `reconnect_backoff`, `reconnect_backoff_factor`, `check_key_permissions`, `ssh_tun_timeout`.
- **`metrics_config: dict`**: Настройки для сбора метрик.
  - `interval`, `max_durations`, `retention_strategy`.
- **`timing_config: dict`**: Настройки временных интервалов.
  - `client_handler_timeout`, `close_timeout`, `ssh_close_timeout`.
- **`suppress_client_errors: bool`**: По умолчанию `True`. Подавляет падение сервера из-за ошибок в клиентском коде.

## Запуск тестов

### Запуск всех тестов (кроме реальных интеграционных)
```bash
pytest
```

### Запуск тестов по группам
```bash
pytest -m tcp
pytest -m ssh
```

### Настройка и запуск реальных интеграционных тестов (SSH)

По умолчанию реальный SSH-тест (`test_integration_ssh_real`) пропускается. Чтобы его запустить, необходимо один раз настроить и запустить **изолированный экземпляр SSH-сервера**.

#### 1. Единоразовая настройка тестового SSH-сервера
Эти команды нужно выполнить один раз в корне вашего проекта.

* **Создайте директорию для конфигурации:**
    ```bash
    mkdir -p tests/sshd_test_config
    ```

* **Сгенерируйте отдельный ключ хоста для тестового сервера:**
    ```bash
    ssh-keygen -t rsa -f ./tests/sshd_test_config/ssh_host_rsa_key -N ""
    ```

* **Добавьте ключ в авторизованные, и позаботьтесь о правильных правах доступа:**
    ```bash
    cat tests/sshd_test_config/ssh_host_rsa_key.pub >>~/.ssh/authorized_key
    chmod 700 ~/.ssh
    chmod 600 ~/.ssh/authorized_keys
    ```

* **Создайте конфигурационный файл для тестового сервера:**
    ```bash
    cat <<EOF > ./tests/sshd_test_config/sshd_config
    Port 2222
    PidFile /tmp/abakedserver-sshd.pid
    HostKey $(pwd)/tests/sshd_test_config/ssh_host_rsa_key
    AuthorizedKeysFile .ssh/authorized_keys
    UsePAM no
    PasswordAuthentication no
    ChallengeResponseAuthentication no
    PermitRootLogin no
    GatewayPorts yes
    EOF
    ```
    На этом этапе можно выполнить ручную проверку того, что туннель может быть установлен (см. раздел 4. Примечания)

#### 2. Запуск и остановка тестового SSH-сервера

* **Запустить сервер (требуется `sudo`):**
    ```bash
    sudo /usr/sbin/sshd -f "$(pwd)/tests/sshd_test_config/sshd_config"
    ```

* **Остановить сервер:**
    ```bash
    sudo pkill -F /tmp/abakedserver-sshd.pid
    ```

#### 3. Запуск реального теста

Когда тестовый сервер запущен, выполните:
```bash
RUN_REAL_SSH_TESTS=1 pytest -m integration -v
```

### 4. Примечания

* **Проверка того, что форвардинг сам по себе может работать.**

    Первый терминал:
    ```bash
    nc -l 8888
    ```

    Второй терминал:
    ```bash
    ssh -i tests/sshd_test_config/ssh_host_rsa_key -N -R 127.0.0.1:9999:localhost:8888 -p 2222 $(whoami)@localhost
    ```

    Третий терминал:
    ```bash
    nc localhost 9999
    ```
