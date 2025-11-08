#!/bin/bash

# === Вспомогательная функция: запрос с дефолтом ===
ask_with_default() {
    local prompt="$1"
    local default="$2"
    read -p "$prompt (Enter → $default): " value
    echo "${value:-$default}"
}

# === Настройки ===
USER="testuser"
REMOTE_DIR="/home/$USER"
LOCAL_SCRIPT="../scripts/test_fio_7.py"

# === Проверка скрипта ===
if [ ! -f "$LOCAL_SCRIPT" ]; then
    echo "❌ Ошибка: не найден $LOCAL_SCRIPT"
    exit 1
fi

# === 1. Запрос количества ВМ и IP ===
read -p "Сколько ВМ будут участвовать в тесте? (например, 1, 2, 4): " VM_COUNT
if ! [[ "$VM_COUNT" =~ ^[1-9][0-9]*$ ]]; then
    echo "❌ Ошибка: введите целое число ≥ 1"
    exit 1
fi

declare -a VMS
for ((i=1; i<=VM_COUNT; i++)); do
    read -p "Введите IP-адрес ВМ #$i: " ip
    if [[ ! $ip =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "❌ Некорректный IP: $ip"
        exit 1
    fi
    VMS+=("$ip")
done

# === 2. Выбор типа теста ===
echo
echo "Выберите тип теста:"
echo "  1) Только fio"
echo "  2) Только pgbench"
echo "  3) fio + pgbench (рекомендуется)"
read -p "Ваш выбор (1/2/3): " TEST_MODE
case $TEST_MODE in
    1) RUN_FIO=true;   RUN_PG=false;  ;;
    2) RUN_FIO=false;  RUN_PG=true;   ;;
    3) RUN_FIO=true;   RUN_PG=true;   ;;
    *) echo "❌ Неверный выбор. Выход."; exit 1 ;;
esac

# === 3. Параметры fio (если нужен) ===
if [ "$RUN_FIO" = true ]; then
    echo
    echo "=== Настройка fio (оставьте пустым для значений по умолчанию) ==="
    TEST_NAME=$(ask_with_default "Название теста" "interactive_run")
    SIZE=$(ask_with_default "Размер файла" "10G")
    BS=$(ask_with_default "Размер блока" "4k")
    MIX=$(ask_with_default "Процент записи в RW" "60")
    IO_DEPTH=$(ask_with_default "Глубина очереди" "64")
    RUNTIME=$(ask_with_default "Время выполнения (сек)" "60")
fi

# === 4. Подтверждение ===
echo
echo "=== Подтверждение запуска ==="
echo "• ВМ: ${VMS[*]}"
echo "• Тесты: $( [ "$RUN_FIO" = true ] && echo "fio " )$( [ "$RUN_PG" = true ] && echo "pgbench" )"
if [ "$RUN_FIO" = true ]; then
    echo "• fio: ${SIZE}, блок=${BS}, время=${RUNTIME} сек"
fi
echo
read -p "Запустить тесты? (y/N): " confirm
if [[ ! $confirm =~ ^[Yy]$ ]]; then
    echo "Отмена."
    exit 0
fi

# === 5. Копирование скрипта на ВМ ===
echo -e "\n📤 Копирование скрипта на ВМ..."
for ip in "${VMS[@]}"; do
    scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        "$LOCAL_SCRIPT" "$USER@$ip:$REMOTE_DIR/" >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo "⚠️ Не удалось скопировать на $ip"
        exit 1
    fi
done

# === 5.1 Очистка старых результатов на ВМ ===
echo -e "\n🧹 Очистка предыдущих результатов на ВМ..."
for ip in "${VMS[@]}"; do
    ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        "$USER@$ip" "rm -rf $REMOTE_DIR/results/* $REMOTE_DIR/testfile* 2>/dev/null || true"
    echo "  → Очищено: $ip"
done

# === 6. Формирование команды ===
CMD="cd $REMOTE_DIR && python3 ./test_fio_7.py"
CMD="$CMD --test-name '$TEST_NAME'"
CMD="$CMD --size '$SIZE'"
CMD="$CMD --bs '$BS'"
CMD="$CMD --mix '$MIX'"
CMD="$CMD --io-depth $IO_DEPTH"
CMD="$CMD --runtime $RUNTIME"
if [ "$RUN_PG" = true ]; then
    CMD="$CMD --run-pgbench"
fi

# Если выбран только pgbench — запускаем его отдельно
if [ "$RUN_FIO" = false ] && [ "$RUN_PG" = true ]; then
    CMD="mkdir -p $REMOTE_DIR/results && cd $REMOTE_DIR && pgbench -i -s100 postgres && pgbench -c32 -j4 -T600 postgres > results/pgbench_output.txt 2>&1"
fi

# Если fio + pgbench — добавляем флаг (предполагается, что test_fio_7.py поддерживает --run-pgbench)
if [ "$RUN_FIO" = true ] && [ "$RUN_PG" = true ]; then
    CMD="$CMD --run-pgbench"
fi

# === 7. Запуск с прогресс-баром ===
echo -e "\n🚀 Запуск тестов на ${#VMS[@]} ВМ..."
PIDS=()
for ip in "${VMS[@]}"; do
    ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        "$USER@$ip" "$CMD" > "fio_log_$ip.log" 2>&1 &
    PIDS+=($!)
done

# Простой прогресс-бар (каждые 10 секунд точка)
echo -n "Прогресс: "
while kill -0 ${PIDS[0]} 2>/dev/null; do
    echo -n "."
    sleep 10
done
wait
echo " ✅ Завершено."

# === 8. Сбор результатов ===
RESULTS_DIR="results/$(date +%Y%m%d_%H%M)_test"
mkdir -p "$RESULTS_DIR"

echo -e "\n⬇️ Сбор результатов..."
for ip in "${VMS[@]}"; do
    echo "  ← $ip"
    # Собираем папку results/ ИЛИ pgbench_output.txt
    if [ "$RUN_FIO" = true ]; then
        scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
            -r "$USER@$ip:$REMOTE_DIR/results/" "$RESULTS_DIR/results_$ip/" 2>/dev/null
    fi
    if [ "$RUN_PG" = true ] && [ "$RUN_FIO" = false ]; then
        scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
            "$USER@$ip:$REMOTE_DIR/results/pgbench_output.txt" "$RESULTS_DIR/pgbench_$ip.txt" 2>/dev/null
    fi
done
# Сбор результатов pgbench
if [ "$RUN_PG" = true ]; then
    echo -e "\n📥 Сбор результатов pgbench..."
    for ip in "${VMS[@]}"; do
        # Проверяем, есть ли файл с результатами
        if ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
            "$USER@$ip" "[ -f $REMOTE_DIR/results/pgbench_output.txt ]"; then
            scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
                "$USER@$ip:$REMOTE_DIR/results/pgbench_output.txt" "$RESULTS_DIR/pgbench_$ip.txt" 2>/dev/null
            echo "  ← pgbench_$ip.txt"
        fi
    done
fi

echo -e "\n📁 Результаты сохранены в: ./$RESULTS_DIR/"
ls -l "$RESULTS_DIR"