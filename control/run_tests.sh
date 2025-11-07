#!/bin/bash

# === Настройки ===
USER="testuser"
REMOTE_DIR="/home/$USER"
LOCAL_SCRIPT="../scripts/test_fio_7.py"

# === Проверка наличия скрипта ===
if [ ! -f "$LOCAL_SCRIPT" ]; then
    echo "❌ Ошибка: не найден локальный скрипт $LOCAL_SCRIPT"
    echo "Убедитесь, что запускаете из директории control/ и что скрипт существует в ../scripts/"
    exit 1
fi

# === Запрос количества ВМ ===
read -p "Сколько ВМ будут участвовать в тесте? (например, 1, 2, 4): " VM_COUNT
if ! [[ "$VM_COUNT" =~ ^[1-9][0-9]*$ ]]; then
    echo "❌ Ошибка: введите целое число ≥ 1"
    exit 1
fi

# === Запрос IP-адресов ===
declare -a VMS
for ((i=1; i<=VM_COUNT; i++)); do
    read -p "Введите IP-адрес ВМ #$i: " ip
    if [[ ! $ip =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "❌ Некорректный IP: $ip"
        exit 1
    fi
    VMS+=("$ip")
done

# === Параметры fio (единые для всех ВМ) ===
TEST_NAME="run_$(date +%Y%m%d_%H%M)"
SIZE="10G"
BS="4k"
MIX="60"
IO_DEPTH="64"
RUNTIME="60"

# === Копирование скрипта на все ВМ ===
echo -e "\n📤 Копирование скрипта test_fio_7.py на все ВМ..."
for ip in "${VMS[@]}"; do
    echo "  → $ip"
    scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        "$LOCAL_SCRIPT" "$USER@$ip:$REMOTE_DIR/" >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo "⚠️  Не удалось скопировать скрипт на $ip"
        exit 1
    fi
done

# === Формирование команды запуска ===
CMD="cd $REMOTE_DIR && python3 ./test_fio_7.py \
  --test-name '$TEST_NAME' \
  --size '$SIZE' \
  --bs '$BS' \
  --mix '$MIX' \
  --io-depth $IO_DEPTH \
  --runtime $RUNTIME"

# === Запуск тестов параллельно ===
echo -e "\n🚀 Запуск тестов на ${#VMS[@]} ВМ..."
for ip in "${VMS[@]}"; do
    echo "  → $ip"
    ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        "$USER@$ip" "$CMD" > "fio_log_$ip.log" 2>&1 &
done

wait
echo -e "\n✅ Все тесты завершены."

# === Сбор результатов ===
RESULTS_DIR="results/$TEST_NAME"
mkdir -p "$RESULTS_DIR"

echo -e "\n⬇️ Сбор результатов..."
for ip in "${VMS[@]}"; do
    echo "  ← $ip"
    scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -r "$USER@$ip:$REMOTE_DIR/results/" "$RESULTS_DIR/results_$ip/" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "⚠️  Не удалось собрать результаты с $ip"
    fi
done

echo -e "\n📁 Результаты сохранены в: ./$RESULTS_DIR/"
ls -l "$RESULTS_DIR"