#!/usr/bin/env python3
"""
Скрипт для агрегации результатов множественных итераций тестирования.
Вычисляет средние значения, стандартные отклонения и создает сводные отчеты.
"""

import os
import re
import json
import sys
from pathlib import Path
from statistics import mean, stdev
from datetime import datetime

def parse_results_sheet(file_path):
    """Парсит файл results_sheet и извлекает метрики"""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        results = {
            'fio': {},
            'pgbench': {}
        }
        
        # Парсинг FIO результатов
        fio_pattern = r'(\d+)\s+(.+?)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)'
        for match in re.finditer(fio_pattern, content):
            test_num, test_name, iops, bandwidth, latency = match.groups()
            results['fio'][test_name.strip()] = {
                'IOPS': float(iops),
                'Bandwidth': float(bandwidth),
                'Latency': float(latency)
            }
        
        # Парсинг pgbench результатов
        tps_match = re.search(r'TPS.*?:\s*([\d.]+)', content)
        lat_avg_match = re.search(r'Средняя задержка:\s*([\d.]+)', content)
        lat_std_match = re.search(r'Стандартное отклонение задержки:\s*([\d.]+)', content)
        transactions_match = re.search(r'Обработано транзакций:\s*(\d+)', content)
        
        if tps_match:
            results['pgbench'] = {
                'TPS': float(tps_match.group(1)),
                'Latency_Avg': float(lat_avg_match.group(1)) if lat_avg_match else None,
                'Latency_Stddev': float(lat_std_match.group(1)) if lat_std_match else None,
                'Transactions': int(transactions_match.group(1)) if transactions_match else None
            }
        
        return results
    except Exception as e:
        print(f"⚠️ Ошибка парсинга {file_path}: {e}")
        return None

def aggregate_results(results_dir):
    """Агрегирует результаты всех итераций"""
    results_dir = Path(results_dir)
    
    # Поиск всех файлов results_sheet
    iterations_data = {}
    
    # Ищем файлы напрямую и в поддиректориях
    all_result_files = list(results_dir.glob('**/results_sheet_*.txt'))
    
    if not all_result_files:
        print("❌ Не найдено файлов results_sheet_*.txt")
        return None
    
    print(f"Найдено {len(all_result_files)} файлов результатов:")
    
    for file in all_result_files:
        print(f"  • {file.relative_to(results_dir)}")
        
        # Извлекаем номер итерации из пути к файлу или из имени директории
        iter_num = None
        
        # Попытка 1: из имени директории (iter1, iter2, etc.)
        for parent in file.parents:
            iter_match = re.search(r'iter(\d+)', parent.name)
            if iter_match:
                iter_num = int(iter_match.group(1))
                break
        
        # Попытка 2: из имени файла (если содержит iter)
        if iter_num is None:
            iter_match = re.search(r'iter(\d+)', file.name)
            if iter_match:
                iter_num = int(iter_match.group(1))
        
        # Попытка 3: по timestamp (группируем по времени)
        if iter_num is None:
            # Если нет явного номера итерации, используем timestamp как идентификатор
            timestamp_match = re.search(r'(\d{8}_\d{6})', file.name)
            if timestamp_match:
                # Создаем псевдо-номер итерации на основе хэша timestamp
                timestamp = timestamp_match.group(1)
                iter_num = hash(timestamp) % 1000  # Используем хэш для уникальности
        
        # По умолчанию - итерация 1
        if iter_num is None:
            iter_num = 1
        
        parsed = parse_results_sheet(file)
        if parsed:
            if iter_num not in iterations_data:
                iterations_data[iter_num] = []
            iterations_data[iter_num].append(parsed)
    
    if not iterations_data:
        print("❌ Не удалось распарсить результаты")
        return None
    
    # Агрегация по итерациям
    aggregated = {
        'fio': {},
        'pgbench': {},
        'iterations': sorted(iterations_data.keys()),
        'num_vms': len(iterations_data[list(iterations_data.keys())[0]])
    }
    
    # Агрегация FIO
    all_fio_tests = set()
    for iter_results in iterations_data.values():
        for vm_result in iter_results:
            all_fio_tests.update(vm_result['fio'].keys())
    
    for test_name in all_fio_tests:
        metrics = {'IOPS': [], 'Bandwidth': [], 'Latency': []}
        
        for iter_results in iterations_data.values():
            for vm_result in iter_results:
                if test_name in vm_result['fio']:
                    for metric in metrics.keys():
                        metrics[metric].append(vm_result['fio'][test_name][metric])
        
        aggregated['fio'][test_name] = {
            'IOPS_mean': mean(metrics['IOPS']),
            'IOPS_stdev': stdev(metrics['IOPS']) if len(metrics['IOPS']) > 1 else 0,
            'Bandwidth_mean': mean(metrics['Bandwidth']),
            'Bandwidth_stdev': stdev(metrics['Bandwidth']) if len(metrics['Bandwidth']) > 1 else 0,
            'Latency_mean': mean(metrics['Latency']),
            'Latency_stdev': stdev(metrics['Latency']) if len(metrics['Latency']) > 1 else 0,
            'samples': len(metrics['IOPS'])
        }
    
    # Агрегация pgbench
    pgbench_metrics = {'TPS': [], 'Latency_Avg': [], 'Latency_Stddev': [], 'Transactions': []}
    
    for iter_results in iterations_data.values():
        for vm_result in iter_results:
            if vm_result['pgbench']:
                for metric, values in pgbench_metrics.items():
                    val = vm_result['pgbench'].get(metric)
                    if val is not None:
                        values.append(val)
    
    if pgbench_metrics['TPS']:
        aggregated['pgbench'] = {
            'TPS_mean': mean(pgbench_metrics['TPS']),
            'TPS_stdev': stdev(pgbench_metrics['TPS']) if len(pgbench_metrics['TPS']) > 1 else 0,
            'Latency_Avg_mean': mean(pgbench_metrics['Latency_Avg']),
            'Latency_Avg_stdev': stdev(pgbench_metrics['Latency_Avg']) if len(pgbench_metrics['Latency_Avg']) > 1 else 0,
            'samples': len(pgbench_metrics['TPS'])
        }
    else:
        print("⚠️  Нет результатов pgbench для агрегации")
    
    return aggregated

def generate_report(aggregated, output_file):
    """Генерирует текстовый отчет"""
    report = []
    report.append("="*80)
    report.append("АГРЕГИРОВАННЫЕ РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    report.append("="*80)
    report.append(f"Дата создания отчета: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Количество итераций: {len(aggregated['iterations'])}")
    report.append(f"Количество ВМ: {aggregated['num_vms']}")
    report.append("")
    
    # FIO результаты
    if aggregated['fio']:
        report.append("="*80)
        report.append("FIO - Тестирование дисковой подсистемы (средние значения)")
        report.append("="*80)
        report.append("")
        report.append(f"{'Test Name':<30} {'IOPS':<20} {'Bandwidth (MiB/s)':<20} {'Latency (ms)':<20}")
        report.append("-"*80)
        
        for test_name, metrics in sorted(aggregated['fio'].items()):
            report.append(
                f"{test_name:<30} "
                f"{metrics['IOPS_mean']:>8.1f} ±{metrics['IOPS_stdev']:>6.1f}  "
                f"{metrics['Bandwidth_mean']:>8.1f} ±{metrics['Bandwidth_stdev']:>6.1f}  "
                f"{metrics['Latency_mean']:>8.2f} ±{metrics['Latency_stdev']:>6.2f}"
            )
        report.append("")
    
    # pgbench результаты
    if aggregated['pgbench']:
        report.append("="*80)
        report.append("pgbench - Тестирование PostgreSQL OLTP (средние значения)")
        report.append("="*80)
        report.append("")
        pg = aggregated['pgbench']
        report.append(f"TPS (Transactions Per Second): {pg['TPS_mean']:.2f} ± {pg['TPS_stdev']:.2f}")
        report.append(f"Средняя задержка: {pg['Latency_Avg_mean']:.3f} ± {pg['Latency_Avg_stdev']:.3f} ms")
        report.append(f"Количество измерений: {pg['samples']}")
        report.append("")
    else:
        report.append("="*80)
        report.append("pgbench - Тестирование PostgreSQL OLTP")
        report.append("="*80)
        report.append("")
        report.append("⚠️  Результаты pgbench отсутствуют (тест не запускался или не был включен)")
        report.append("")
    
    report.append("="*80)
    report.append("Примечание: Значения указаны в формате 'среднее ± стандартное отклонение'")
    report.append("="*80)
    
    report_text = "\n".join(report)
    
    # Вывод в консоль
    print(report_text)
    
    # Сохранение в файл
    with open(output_file, 'w') as f:
        f.write(report_text)
    
    print(f"\n📄 Отчет сохранен: {output_file}")
    
    return report_text

def save_json(aggregated, output_file):
    """Сохраняет агрегированные данные в JSON"""
    with open(output_file, 'w') as f:
        json.dump(aggregated, f, indent=2)
    print(f"📊 JSON данные сохранены: {output_file}")

def main():
    if len(sys.argv) < 2:
        print("Использование: python3 aggregate_results.py <путь_к_директории_с_результатами>")
        sys.exit(1)
    
    results_dir = sys.argv[1]
    
    if not os.path.exists(results_dir):
        print(f"❌ Директория не найдена: {results_dir}")
        sys.exit(1)
    
    print(f"📁 Анализ результатов в: {results_dir}")
    print("⏳ Обработка данных...")
    
    aggregated = aggregate_results(results_dir)
    
    if not aggregated:
        print("❌ Не удалось агрегировать результаты")
        sys.exit(1)
    
    # Генерация отчетов
    output_base = os.path.join(results_dir, "aggregated_report")
    generate_report(aggregated, f"{output_base}.txt")
    save_json(aggregated, f"{output_base}.json")
    
    print("\n✅ Агрегация завершена!")

if __name__ == "__main__":
    main()