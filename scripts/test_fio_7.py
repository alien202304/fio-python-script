#!/usr/bin/env python3

import re
import subprocess
import os
import time
from datetime import datetime
import argparse
import sys

# Параметры тестирования по умолчанию
DEFAULT_SIZE = "10G"
DEFAULT_BS = "4k"
DEFAULT_MIX = "60"
DEFAULT_IO_DEPTH = 64

def convert_to_msec(value, unit):
    """Конвертирует значение в миллисекунды с проверкой единиц"""
    try:
        val = float(value)
        unit = unit.lower()
        if unit == 'nsec':
            return val / 1_000_000
        elif unit == 'usec':
            return val / 1_000
        elif unit == 'msec':
            return val
        else:
            print(f"Неизвестная единица измерения: {unit}")
            return 0.0
    except Exception as e:
        print(f"Ошибка конвертации: {str(e)}")
        return 0.0

def error_result():
    return {
        "write": {
            "IOPS": "N/A",
            "Bandwidth (MiB/s)": "N/A",
            "Latency (ms)": "N/A",
            "Latency Details": {}
        },
        "read": {
            "IOPS": "N/A",
            "Bandwidth (MiB/s)": "N/A",
            "Latency (ms)": "N/A",
            "Latency Details": {}
        }
    }

def format_block_size(bs_input):
    """Добавляет 'k' если введено просто число без единиц измерения"""
    if bs_input.replace(".", "").isdigit():
        return bs_input + "k"
    return bs_input

def create_directory(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)
        print(f"Создана директория: {directory}")

def run_fio_test(test_name, filename, size, rw, bs, rwmixwrite=None, results_dir=None, 
                io_depth=DEFAULT_IO_DEPTH, runtime=None, test_suite_name="default_test"):
    # Обрабатываем названия для использования в имени файла
    def sanitize_filename(name):
        return re.sub(r'[^\w-]', '_', name).strip('_')[:50]
    
    test_suite_safe = sanitize_filename(test_suite_name)
    test_name_safe = sanitize_filename(test_name)
    
    base_filename = f"{test_name_safe}_{test_suite_safe}"
    output_file = os.path.join(results_dir, f"{base_filename}_results.txt")
    latency_log = os.path.join(results_dir, f"{base_filename}_latency.log")
    
    command = [
        'fio',
        '--name=' + test_name,
        '--filename=' + filename,
        '--size=' + size,
        '--rw=' + rw,
        '--bs=' + bs,
        '--direct=1',
        '--ioengine=libaio',
        '--iodepth=' + str(io_depth),
        '--numjobs=4',
        '--group_reporting',
        '--output=' + output_file,
        '--output-format=normal',
        '--lat_percentiles=1',
#        '--write_lat_log=' + os.path.join(results_dir, f"{test_name_safe}_latency.log"),
        '--log_avg_msec=1000',
        '--disable_clat=0'
    ]
    
    if runtime is not None:
        command.extend(['--runtime=' + str(runtime), '--time_based'])
    
    if rwmixwrite is not None:
        command.append('--rwmixwrite=' + str(rwmixwrite))
    
    print(f"Запуск теста: {test_name}...")
    result = subprocess.run(command, stderr=subprocess.PIPE)
    
    if result.returncode != 0:
        print(f"Ошибка выполнения теста {test_name}:")
        print(result.stderr.decode())
        return False
    
    print(f"Тест {test_name} завершен. Результаты сохранены в {output_file}")
    return True

def extract_latency(section):
    latencies = {
        "lat_min": "N/A",
        "lat_max": "N/A",
        "lat_avg": "N/A",
        "lat_95th": "N/A",
        "lat_99th": "N/A"
    }

    try:
        # Основные метрики из clat
        clat_match = re.search(
            r'clat.*?min=([\d.]+)\D*max=([\d.]+)\D*avg=([\d.]+)',
            section, 
            re.DOTALL
        )
        if clat_match:
            unit = re.search(r'clat\s*\((\w+)\)', section).group(1).lower()
            latencies.update({
                "lat_min": f"{convert_to_msec(clat_match.group(1), unit):.2f}",
                "lat_max": f"{convert_to_msec(clat_match.group(2), unit):.2f}",
                "lat_avg": f"{convert_to_msec(clat_match.group(3), unit):.2f}"
            })

        # Перцентили
        perc_match = re.search(
            r'95\.00th=\[\s*([\d.]+)\].*?99\.00th=\[\s*([\d.]+)\]',
            section, 
            re.DOTALL
        )
        if perc_match:
            unit = 'usec'
            latencies.update({
                "lat_95th": f"{convert_to_msec(perc_match.group(1), unit):.2f}",
                "lat_99th": f"{convert_to_msec(perc_match.group(2), unit):.2f}"
            })

    except Exception as e:
        print(f"Ошибка парсинга задержек: {str(e)}")

    return latencies

def parse_fio_results(file_path, is_mixed=False):
    try:
        with open(file_path, 'r') as file:
            content = file.read()

        def extract_metrics(section, pattern, default="N/A"):
            match = re.search(pattern, section, re.IGNORECASE)
            return match.group(1) if match else default

        def convert_bandwidth(value, unit):
            """Конвертирует bandwidth в MiB/s"""
            try:
                val = float(value)
                unit = unit.lower()
                if unit == 'kib/s':
                    return val / 1024
                elif unit == 'mib/s':
                    return val
                elif unit == 'gb/s':
                    return val * 1024
                else:
                    return val  # Для неизвестных единиц возвращаем как есть
            except:
                return "N/A"

        if is_mixed:
            results = {"write": {}, "read": {}}
            
            # Обработка записи
            write_bw_match = re.search(
                r'WRITE.*?bw=([\d.]+)([KMGT]?iB/s)',
                content, 
                re.IGNORECASE | re.DOTALL
            )
            if write_bw_match:
                results["write"]["Bandwidth (MiB/s)"] = f"{convert_bandwidth(write_bw_match.group(1), write_bw_match.group(2).lower()):.1f}"
            else:
                results["write"]["Bandwidth (MiB/s)"] = "N/A"

            # Обработка чтения
            read_bw_match = re.search(
                r'READ.*?bw=([\d.]+)([KMGT]?iB/s)',
                content, 
                re.IGNORECASE | re.DOTALL
            )
            if read_bw_match:
                results["read"]["Bandwidth (MiB/s)"] = f"{convert_bandwidth(read_bw_match.group(1), read_bw_match.group(2).lower()):.1f}"
            else:
                results["read"]["Bandwidth (MiB/s)"] = "N/A"

            # Остальные метрики оставляем как было
            write_section = re.search(r'write[\s\S]*?(?=read|$)', content, re.IGNORECASE)
            if write_section:
                write_content = write_section.group(0)
                results["write"].update({
                    "IOPS": extract_metrics(write_content, r'write: IOPS=([\d.]+)'),
                    "Latency Details": extract_latency(write_content)
                })
                results["write"]["Latency (ms)"] = results["write"]["Latency Details"].get("lat_avg", "N/A")

            read_section = re.search(r'read[\s\S]*?(?=write|$)', content, re.IGNORECASE)
            if read_section:
                read_content = read_section.group(0)
                results["read"].update({
                    "IOPS": extract_metrics(read_content, r'read: IOPS=([\d.]+)'),
                    "Latency Details": extract_latency(read_content)
                })
                results["read"]["Latency (ms)"] = results["read"]["Latency Details"].get("lat_avg", "N/A")

            return results

        else:
            # Обработка обычных тестов
            bw_match = re.search(r'BW=([\d.]+)([KMGT]?iB/s)', content, re.IGNORECASE)
            bandwidth = "N/A"
            if bw_match:
                bandwidth = f"{convert_bandwidth(bw_match.group(1), bw_match.group(2).lower()):.1f}"

            return {
                "IOPS": extract_metrics(content, r'IOPS=([\d.]+)'),
                "Bandwidth (MiB/s)": bandwidth,
                "Latency (ms)": extract_latency(content).get("lat_avg", "N/A"),
                "Latency Details": extract_latency(content)
            }

    except Exception as e:
        print(f"Ошибка чтения файла {file_path}: {str(e)}")
        return error_result()
    
def run_pgbench_test():
    """Запускает pgbench и возвращает результаты"""
    print("\n=== Запуск pgbench ===")
    # Проверка наличия pgbench
    if subprocess.run(["which", "pgbench"], capture_output=True, text=True).returncode != 0:
        print("❌ pgbench не установлен")
        return None

    # Проверка доступности БД
    if subprocess.run(["psql", "-c", "SELECT 1"], capture_output=True, text=True).returncode != 0:
        print("❌ PostgreSQL недоступен")
        return None
    # Инициализация
    init_cmd = ["pgbench", "-i", "-s100", "postgres"]
    result = subprocess.run(init_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Ошибка инициализации pgbench:\n{result.stderr}")
        return None
    # OLTP-тест
    test_cmd = ["pgbench", "-c32", "-j4", "-T600", "-P30", "postgres"]
    result = subprocess.run(test_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Ошибка выполнения pgbench:\n{result.stderr}")
        return None
    # Парсинг
    output = result.stdout
    tps = re.search(r'tps = ([\d.]+)', output)
    lat = re.search(r'latency average = ([\d.]+) ms', output)
    return {
        "TPS": tps.group(1) if tps else "N/A",
        "Latency (ms)": lat.group(1) if lat else "N/A"
    }

def print_results_table(results, test_params, pgbench_result=None, output_file=None):
    date_header = f"Дата и время теста: {test_params['start_time']}\n\n"
    
    params_section = "Параметры теста:\n"
    params_section += f"  • Название теста: {test_params['test_name']}\n"
    params_section += f"  • Размер тестового файла, GB: {test_params['size']}\n"
    params_section += f"  • Размер блока данных, bytes: {test_params['bs']}\n"
    params_section += f"  • Процент операций записи в тесте RW: {test_params['mix']}%\n"
    params_section += f"  • Глубина очереди (IO depth): {test_params['io_depth']}\n"
    params_section += f"  • Время выполнения тестов, сек: {test_params['runtime'] if test_params['runtime'] else 'Автоопределение'}\n\n"
    
    # Форматирование основной таблицы результатов
    main_header = f"Основные результаты тестов: {test_params['test_name']}\n"
    main_columns = "{:<10} {:<30} {:<15} {:<20} {:<15}".format(
        "Test No.", "Test Name", "kIOPS", "Bandwidth (MiB/s)", "Latency (ms)"
    )
    main_width = len(main_columns)  # Вычисляем реальную ширину таблицы
    
    main_table_divider_top = "=" * main_width
    main_table_divider_bottom = "_" * main_width
    main_table_rows = []

    for result in results:
        main_table_rows.append("{:<10} {:<30} {:<15} {:<20} {:<15}".format(
            result["Test Number"],
            result["Test Name"],
            result["IOPS"],
            result["Bandwidth (MiB/s)"],
            result.get("Latency (ms)", "N/A")
        ))

    full_output = date_header + params_section + main_header + "\n"
    full_output += main_table_divider_top + "\n"
    full_output += main_columns + "\n"
    full_output += main_table_divider_bottom + "\n"
    full_output += "\n".join(main_table_rows) + "\n"

    # Форматирование таблицы детализированных задержек
    latency_header = "\nДетализированная информация о задержках:"
    latency_columns = "{:<10} {:<30} {:<15} {:<15} {:<15} {:<15} {:<15}".format(
        "Test No.", "Test Name", "Min (ms)", "Avg (ms)", "Max (ms)", "95th (ms)", "99th (ms)"
    )
    latency_width = len(latency_columns)  # Вычисляем реальную ширину таблицы
    
    latency_divider_top = "=" * latency_width
    latency_divider_bottom = "_" * latency_width
    latency_table_rows = []

    for result in results:
        if "Latency Details" in result:
            lat_details = result["Latency Details"]
            latency_table_rows.append("{:<10} {:<30} {:<15} {:<15} {:<15} {:<15} {:<15}".format(
                result["Test Number"],
                result["Test Name"],
                lat_details.get("lat_min", "N/A"),
                lat_details.get("lat_avg", "N/A"),
                lat_details.get("lat_max", "N/A"),
                lat_details.get("lat_95th", "N/A"),
                lat_details.get("lat_99th", "N/A")
            ))

    full_output += latency_header + "\n"
    full_output += latency_divider_top + "\n"
    full_output += latency_columns + "\n"
    full_output += latency_divider_bottom + "\n"
    full_output += "\n".join(latency_table_rows) + "\n"

    # Добавляем обработку отсутствующих значений задержки
    for result in results:
        if result.get("Latency (ms)") == "N/A":
            if "Latency Details" in result:
                avg_lat = result["Latency Details"].get("lat_avg", "N/A")
                if avg_lat != "N/A":
                    result["Latency (ms)"] = avg_lat

    # === ДОБАВЛЕНО: ВЫВОД PG BENCH ===
    if 'pgbench_result' in locals() or 'pgbench_result' in globals():
        # Но лучше передавать как параметр — см. шаг 3
        pass  # временно
    
    if pgbench_result:
        full_output += "\n" + "="*60 + "\n"
        full_output += "Результаты pgbench (OLTP):\n"
        full_output += "="*60 + "\n"
        full_output += f"TPS (Transactions Per Second): {pgbench_result['TPS']}\n"
        full_output += f"Средняя задержка: {pgbench_result['Latency (ms)']} ms\n"
    print(f"\n{full_output}")

    if output_file:
        try:
            with open(output_file, 'w') as file:
                file.write(full_output)
            print(f"Полный отчет сохранен в файл: {output_file}")
        except Exception as e:
            print(f"Ошибка при сохранении отчета: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description="fio тестирование дисковой подсистемы")
    parser.add_argument('--test-name', type=str, default=None, help="Название теста")
    parser.add_argument('--size', type=str, default=DEFAULT_SIZE, help=f"Размер файла (по умолчанию {DEFAULT_SIZE})")
    parser.add_argument('--bs', type=str, default=DEFAULT_BS, help=f"Размер блока (по умолчанию {DEFAULT_BS})")
    parser.add_argument('--mix', type=str, default=DEFAULT_MIX, help=f"Процент записи в RW (по умолчанию {DEFAULT_MIX})")
    parser.add_argument('--io-depth', type=int, default=DEFAULT_IO_DEPTH, help=f"Глубина очереди (по умолчанию {DEFAULT_IO_DEPTH})")
    parser.add_argument('--runtime', type=int, default=None, help="Время выполнения в секундах (опционально)")
    parser.add_argument('--run-pgbench', action='store_true', help="Запустить pgbench после fio")
    args = parser.parse_args()

    start_time_test = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    home_dir = os.getenv("HOME")
    testfile_path = os.path.join(home_dir, 'testfile')
    results_dir = os.path.join(home_dir, 'results')
    create_directory(results_dir)

    # Если test-name не задан — запрашиваем интерактивно (для обратной совместимости)
    if args.test_name is None:
        print("Параметры по умолчанию:")
        print(f"  Название теста: default test")
        print(f"  Размер тестового файла: {args.size}")
        print(f"  Размер блока данных: {args.bs}")
        print(f"  Процент операций записи: {args.mix}%")
        print(f"  Глубина очереди: {args.io_depth}\n")

        test_name = input("Введите название теста (по умолчанию 'default test'): ") or "default test"
    else:
        test_name = args.test_name

    # Используем аргументы
    size = args.size
    bs = format_block_size(args.bs)
    mix = args.mix
    io_depth = args.io_depth
    runtime = args.runtime

    # Остальной код без изменений...
    tests = [
        {"name": "Sequential Write", "rw": "write", "bs": bs},
        {"name": "Sequential Read", "rw": "read", "bs": bs},
        {"name": "Random Write", "rw": "randwrite", "bs": bs},
        {"name": "Random Read", "rw": "randread", "bs": bs},
        {"name": "Mixed RW", "rw": "randrw", "bs": bs, "mix": mix}
    ]

    test_params = {
        "start_time": start_time_test,
        "test_name": test_name,
        "size": size,
        "bs": bs,
        "mix": mix,
        "io_depth": io_depth,
        "runtime": runtime
    }

    results = []
    all_tests_passed = True
    total_start_time = time.time()

    for index, test in enumerate(tests, start=1):
        print(f"\nТест {index}: {test['name']}")
        success = run_fio_test(
            test_name=test['name'],
            filename=testfile_path,
            size=size,
            rw=test['rw'],
            bs=test['bs'],
            rwmixwrite=test.get("mix"),
            results_dir=results_dir,
            io_depth=io_depth,
            runtime=runtime,
            test_suite_name=test_name
        )
        if not success:
            all_tests_passed = False
            continue

        test_name_safe = test['name'].replace(" ", "_")
        output_file = os.path.join(results_dir, f"{test_name_safe}_{test_name}_results.txt")

        if test['rw'] == 'randrw':
            mixed_results = parse_fio_results(output_file, is_mixed=True)
            results.extend([
                {
                    "Test Number": index,
                    "Test Name": test['name'] + " (Write)",
                    "IOPS": mixed_results["write"]["IOPS"],
                    "Bandwidth (MiB/s)": mixed_results["write"]["Bandwidth (MiB/s)"],
                    "Latency (ms)": mixed_results["write"]["Latency (ms)"],
                    "Latency Details": mixed_results["write"]["Latency Details"]
                },
                {
                    "Test Number": index,
                    "Test Name": test['name'] + " (Read)",
                    "IOPS": mixed_results["read"]["IOPS"],
                    "Bandwidth (MiB/s)": mixed_results["read"]["Bandwidth (MiB/s)"],
                    "Latency (ms)": mixed_results["read"]["Latency (ms)"],
                    "Latency Details": mixed_results["read"]["Latency Details"]
                }
            ])
        else:
            test_results = parse_fio_results(output_file)
            results.append({
                "Test Number": index,
                "Test Name": test['name'],
                "IOPS": test_results["IOPS"],
                "Bandwidth (MiB/s)": test_results["Bandwidth (MiB/s)"],
                "Latency (ms)": test_results["Latency (ms)"],
                "Latency Details": test_results["Latency Details"]
            })

    total_time = time.time() - total_start_time

    # === Запуск pgbench: интерактивно ИЛИ автоматически ===
    pgbench_res = None
    if args.run_pgbench:
        # Автоматический запуск из run_tests.sh
        pgbench_res = run_pgbench_test()
    elif args.test_name is None:
        # Интерактивный режим (запуск вручную на ВМ)
        if input("\nЗапустить pgbench после fio? (y/N): ").strip().lower() in ('y', 'yes'):
            pgbench_res = run_pgbench_test()

    test_suite_safe = re.sub(r'[^\w-]', '_', test_name).strip('_')[:50]
    results_sheet_path = os.path.join(results_dir, f"results_sheet_{test_suite_safe}.txt")
    if all_tests_passed:
        print_results_table(results, test_params, pgbench_result=pgbench_res, output_file=results_sheet_path)
        print(f"\nОбщее время выполнения всех тестов: {total_time:.2f} секунд.")
    else:
        print("\nНекоторые тесты завершились с ошибками. Итоговый отчет не сформирован.")
        print(f"Общее время выполнения: {total_time:.2f} секунд.")

if __name__ == "__main__":
    main()  