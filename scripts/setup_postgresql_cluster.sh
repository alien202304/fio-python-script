#!/bin/bash

set -e  # Остановить при любой ошибке

echo "=== Настройка PostgreSQL 17 на /mnt/pgdata ==="

# === 1. Проверка существования /mnt/pgdata ===
if [ ! -d "/mnt/pgdata" ]; then
    echo "❌ Ошибка: каталог /mnt/pgdata не существует. Убедитесь, что диск смонтирован."
    exit 1
fi

# === 2. Очистка содержимого (если есть) ===
echo "Очистка /mnt/pgdata..."
sudo rm -rf /mnt/pgdata/*
sudo chown postgres:postgres /mnt/pgdata
sudo chmod 700 /mnt/pgdata

# === 3. Останов и удаление старого кластера (если существует) ===
echo "Удаление старого кластера 17/main (если есть)..."
sudo pg_ctlcluster 17 main stop --force 2>/dev/null || true
sudo pg_dropcluster 17 main --stop 2>/dev/null || true

# Удаляем остаточные конфиги (если остались)
sudo rm -rf /etc/postgresql/17/main /var/lib/postgresql/17/main 2>/dev/null || true

# === 4. Создание нового кластера в /mnt/pgdata ===
echo "Создание нового кластера PostgreSQL 17 в /mnt/pgdata..."
sudo pg_createcluster 17 main \
    --datadir=/mnt/pgdata \
    -- --auth-local=trust --auth-host=trust

# === 5. Применение настроек производительности ===
echo "Применение настроек производительности..."

cat <<EOF | sudo tee -a /etc/postgresql/17/main/postgresql.conf

# === Performance Tuning (для 16 ГБ RAM) ===
shared_buffers = 4GB
effective_cache_size = 12GB
work_mem = 64MB
maintenance_work_mem = 1GB

wal_level = replica
max_wal_size = 8GB
min_wal_size = 2GB
checkpoint_timeout = 30min
checkpoint_completion_target = 0.9

max_connections = 200
max_worker_processes = 4
max_parallel_workers_per_gather = 2
max_parallel_workers = 4

log_min_duration_statement = 1000
log_statement = 'none'

listen_addresses = '*'
EOF

# === 6. Настройка pg_hba.conf для тестов ===
echo "Настройка pg_hba.conf..."

cat <<EOF | sudo tee /etc/postgresql/17/main/pg_hba.conf
# TYPE  DATABASE        USER            ADDRESS                 METHOD
local   all             all                                     trust
host    all             all             0.0.0.0/0               trust
EOF

# === 7. Запуск службы ===
echo "Перезапуск PostgreSQL..."
sudo systemctl daemon-reload
sudo systemctl restart postgresql@17-main

# === 8. Проверка ===
echo "Проверка конфигурации..."
sleep 3

if sudo systemctl is-active --quiet postgresql@17-main; then
    echo "✅ PostgreSQL 17 успешно запущен."
    echo "📁 data_directory: $(sudo -u postgres psql -tA -c "SHOW data_directory;")"
    echo "⚙️ shared_buffers: $(sudo -u postgres psql -tA -c "SHOW shared_buffers;")"
    echo "🔌 max_connections: $(sudo -u postgres psql -tA -c "SHOW max_connections;")"
else
    echo "❌ Ошибка: PostgreSQL не запущен."
    sudo journalctl -u postgresql@17-main --no-pager -n 20
    exit 1
fi

echo "=== Настройка завершена! Готов к тестированию. ==="