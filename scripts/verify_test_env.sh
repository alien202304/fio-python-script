#!/bin/bash

echo "=== Автоматическая проверка окружения для тестирования PostgreSQL 17 ==="
echo

# Функция вывода результата
pass() { echo "✅ $1"; }
fail() { echo "❌ $1"; }

ALL_OK=true

# 1. Служба активна
if sudo systemctl is-active --quiet postgresql@17-main; then
    pass "Служба postgresql@17-main активна"
else
    fail "Служба postgresql@17-main НЕ активна"
    ALL_OK=false
fi

# 2. data_directory = /mnt/pgdata
DATA_DIR=$(sudo -u postgres psql -tA -c "SHOW data_directory;" 2>/dev/null || echo "")
if [ "$DATA_DIR" = "/mnt/pgdata" ]; then
    pass "data_directory = /mnt/pgdata"
else
    fail "data_directory = '$DATA_DIR' (ожидалось /mnt/pgdata)"
    ALL_OK=false
fi

# 3. Версия 17
VERSION=$(sudo -u postgres psql -tA -c "SELECT version();" 2>/dev/null || echo "")
if [[ $VERSION == *"PostgreSQL 17."* ]]; then
    pass "Версия PostgreSQL: 17.x"
else
    fail "Версия PostgreSQL: $VERSION (не 17.x)"
    ALL_OK=false
fi

# 4. Параметры производительности
check_param() {
    local param=$1
    local expected=$2
    local actual=$(sudo -u postgres psql -tA -c "SHOW $param;" 2>/dev/null || echo "")
    if [ "$actual" = "$expected" ]; then
        pass "$param = $expected"
    else
        fail "$param = '$actual' (ожидалось $expected)"
        ALL_OK=false
    fi
}

check_param "shared_buffers" "4GB"
check_param "effective_cache_size" "12GB"
check_param "work_mem" "64MB"
check_param "maintenance_work_mem" "1GB"
check_param "max_connections" "200"
check_param "wal_level" "replica"
check_param "max_wal_size" "8GB"
check_param "checkpoint_timeout" "30min"
check_param "listen_addresses" "*"

# 5. Права на /mnt/pgdata
if [ -d "/mnt/pgdata" ]; then
    OWNER=$(stat -c '%U:%G' /mnt/pgdata)
    if [ "$OWNER" = "postgres:postgres" ]; then
        pass "Владелец /mnt/pgdata: postgres:postgres"
    else
        fail "Владелец /mnt/pgdata: $OWNER (ожидалось postgres:postgres)"
        ALL_OK=false
    fi
else
    fail "/mnt/pgdata не существует"
    ALL_OK=false
fi

# 6. Файловая система — XFS
FS_TYPE=$(df -T /mnt/pgdata 2>/dev/null | awk 'NR==2 {print $2}')
if [ "$FS_TYPE" = "xfs" ]; then
    pass "Файловая система: XFS"
else
    fail "Файловая система: $FS_TYPE (ожидалось xfs)"
    ALL_OK=false
fi

# 7. Подключение без пароля
if psql -U postgres -d postgres -c "\q" >/dev/null 2>&1; then
    pass "Подключение без пароля работает"
else
    fail "Не удаётся подключиться без пароля"
    ALL_OK=false
fi

# 8. Тест записи
if psql -U postgres -c "CREATE TABLE verify_test(id int); DROP TABLE verify_test;" >/dev/null 2>&1; then
    pass "Тест записи на диск успешен"
else
    fail "Ошибка записи на диск"
    ALL_OK=false
fi

echo
if [ "$ALL_OK" = true ]; then
    echo "🎉 ВСЁ ГОТОВО К ТЕСТИРОВАНИЮ!"
    echo "Можно запускать fio и pgbench."
else
    echo "⚠️ Некоторые проверки не пройдены. Исправьте ошибки перед тестированием."
    exit 1
fi