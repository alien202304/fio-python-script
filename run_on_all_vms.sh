#!/bin/bash

# === Настройки ===
VMS=("10.85.105.181" "10.85.105.182" "10.85.105.183" "10.85.105.184")  # IP адреса тестовых машин
USER="test"
REMOTE_DIR="/home/$USER"
SCRIPT_NAME="test_fio_7.py"

# === Запрос параметров один раз ===
echo "=== Настройка fio-теста для всех ВМ ==="
read -p "Название теста (по умолчанию: cluster_run): " TEST_NAME
TEST_NAME="${TEST_NAME:-cluster_run}"

read -p "Размер файла (по умолчанию: 10G): " SIZE
SIZE="${SIZE:-10G}"

read -p "Размер блока (по умолчанию: 4k): " BS
BS="${BS:-4k}"

read -p "Процент записи в RW (по умолчанию: 60): " MIX
MIX="${MIX:-60}"

read -p "Глубина очереди (по умолчанию: 64): " IO_DEPTH
IO_DEPTH="${IO_DEPTH:-64}"

read -p "Время выполнения (сек, по умолчанию: 60): " RUNTIME
RUNTIME="${RUNTIME:-60}"

# === Формирование команды ===
CMD="cd $REMOTE_DIR && python3 ./$SCRIPT_NAME \
  --test-name '$TEST_NAME' \
  --size '$SIZE' \
  --bs '$BS' \
  --mix '$MIX' \
  --io-depth $IO_DEPTH \
  --runtime $RUNTIME"

echo -e "\n▶️ Запуск на ${#VMS[@]} ВМ с параметрами:"
echo "   Тест: $TEST_NAME"
echo "   Время: ${RUNTIME} сек"
echo "   Блок: $BS, Запись: ${MIX}%, Очередь: $IO_DEPTH"
echo ""

# === Запуск на всех ВМ параллельно ===
for ip in "${VMS[@]}"; do
    echo "🚀 Запуск на $ip..."
    ssh "$USER@$ip" "$CMD" > "fio_output_$ip.log" 2>&1 &
done

wait
echo -e "\n✅ Все тесты завершены. Логи: fio_output_<IP>.log"