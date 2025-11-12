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
CMD=""

# Случай 1: Только pgbench (без fio)
if [ "$RUN_FIO" = false ] && [ "$RUN_PG" = true ]; then
    echo "Режим: только pgbench"
    CMD="mkdir -p $REMOTE_DIR/results && cd $REMOTE_DIR && sudo -u postgres pgbench -i -s100 postgres && sudo -u postgres pgbench -c32 -j4 -T600 -P30 postgres > results/pgbench_output.txt 2>&1"
fi

# Случай 2: Только fio (без pgbench)
if [ "$RUN_FIO" = true ] && [ "$RUN_PG" = false ]; then
    echo "Режим: только fio"
    CMD="cd $REMOTE_DIR && python3 ./test_fio_7.py"
    CMD="$CMD --test-name '$TEST_NAME'"
    CMD="$CMD --size '$SIZE'"
    CMD="$CMD --bs '$BS'"
    CMD="$CMD --mix '$MIX'"
    CMD="$CMD --io-depth $IO_DEPTH"
    CMD="$CMD --runtime $RUNTIME"
fi

# Случай 3: fio + pgbench (оба теста)
if [ "$RUN_FIO" = true ] && [ "$RUN_PG" = true ]; then
    echo "Режим: fio + pgbench"
    CMD="cd $REMOTE_DIR && python3 ./test_fio_7.py"
    CMD="$CMD --test-name '$TEST_NAME'"
    CMD="$CMD --size '$SIZE'"
    CMD="$CMD --bs '$BS'"
    CMD="$CMD --mix '$MIX'"
    CMD="$CMD --io-depth $IO_DEPTH"
    CMD="$CMD --runtime $RUNTIME"
    CMD="$CMD --run-pgbench"
fi

# Проверка, что команда сформирована
if [ -z "$CMD" ]; then
    echo "❌ Ошибка: не удалось сформировать команду запуска"
    exit 1
fi

echo "Команда для выполнения: $CMD"

# === 7. Запуск с прогресс-баром ===
echo -e "\n🚀 Запуск тестов на ${#VMS[@]} ВМ..."
PIDS=()
for ip in "${VMS[@]}"; do
    echo "  → Запуск на $ip"
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

# Сбор результатов fio
if [ "$RUN_FIO" = true ]; then
    echo "📥 Сбор результатов fio..."
    for ip in "${VMS[@]}"; do
        echo "  ← $ip"
        scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
            -r "$USER@$ip:$REMOTE_DIR/results/" "$RESULTS_DIR/results_$ip/" 2>/dev/null || echo "  ⚠️ Не удалось скопировать с $ip"
    done
fi

# Сбор результатов pgbench
if [ "$RUN_PG" = true ]; then
    echo "📥 Сбор результатов pgbench..."
    for ip in "${VMS[@]}"; do
        # Если pgbench запускался отдельно
        if [ "$RUN_FIO" = false ]; then
            if ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
                "$USER@$ip" "[ -f $REMOTE_DIR/results/pgbench_output.txt ]" 2>/dev/null; then
                scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
                    "$USER@$ip:$REMOTE_DIR/results/pgbench_output.txt" "$RESULTS_DIR/pgbench_$ip.txt" 2>/dev/null
                echo "  ← pgbench_$ip.txt"
            else
                echo "  ⚠️ Файл pgbench_output.txt не найден на $ip"
            fi
        else
            # Если pgbench был частью python скрипта, результаты уже в results_sheet
            echo "  → Результаты pgbench включены в results_sheet_*.txt"
        fi
    done
fi

# Копирование логов выполнения
echo "📋 Копирование логов выполнения..."
for ip in "${VMS[@]}"; do
    if [ -f "fio_log_$ip.log" ]; then
        cp "fio_log_$ip.log" "$RESULTS_DIR/"
        echo "  → fio_log_$ip.log"
    fi
done

echo -e "\n📁 Результаты сохранены в: ./$RESULTS_DIR/"
echo "Содержимое:"
ls -lh "$RESULTS_DIR"

echo -e "\n✅ Готово! Проверьте файлы results_sheet_*.txt для просмотра результатов."