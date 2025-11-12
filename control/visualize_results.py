#!/usr/bin/env python3
"""
Скрипт для визуализации результатов тестирования.
Создает графики для сравнения результатов между разными конфигурациями.
"""

import json
import sys
import os
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Для работы без GUI

def load_aggregated_data(json_file):
    """Загружает агрегированные данные из JSON"""
    with open(json_file, 'r') as f:
        return json.load(f)

def plot_fio_comparison(datasets, output_dir):
    """Создает графики сравнения FIO тестов"""
    
    # Получаем все уникальные имена тестов
    all_tests = set()
    for data in datasets.values():
        if 'fio' in data:
            all_tests.update(data['fio'].keys())
    
    all_tests = sorted(all_tests)
    
    # График IOPS
    fig, ax = plt.subplots(figsize=(14, 8))
    x = range(len(all_tests))
    width = 0.8 / len(datasets)
    
    for idx, (label, data) in enumerate(datasets.items()):
        iops_values = []
        iops_errors = []
        for test in all_tests:
            if test in data.get('fio', {}):
                iops_values.append(data['fio'][test]['IOPS_mean'])
                iops_errors.append(data['fio'][test]['IOPS_stdev'])
            else:
                iops_values.append(0)
                iops_errors.append(0)
        
        offset = width * idx - width * (len(datasets) - 1) / 2
        ax.bar([i + offset for i in x], iops_values, width, 
               label=label, yerr=iops_errors, capsize=5, alpha=0.8)
    
    ax.set_xlabel('Тип теста', fontsize=12)
    ax.set_ylabel('IOPS (тысячи)', fontsize=12)
    ax.set_title('Сравнение IOPS между конфигурациями', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([t.replace(' ', '\n') for t in all_tests], rotation=0, ha='center')
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'fio_iops_comparison.png'), dpi=300)
    plt.close()
    
    # График Bandwidth
    fig, ax = plt.subplots(figsize=(14, 8))
    
    for idx, (label, data) in enumerate(datasets.items()):
        bw_values = []
        bw_errors = []
        for test in all_tests:
            if test in data.get('fio', {}):
                bw_values.append(data['fio'][test]['Bandwidth_mean'])
                bw_errors.append(data['fio'][test]['Bandwidth_stdev'])
            else:
                bw_values.append(0)
                bw_errors.append(0)
        
        offset = width * idx - width * (len(datasets) - 1) / 2
        ax.bar([i + offset for i in x], bw_values, width,
               label=label, yerr=bw_errors, capsize=5, alpha=0.8)
    
    ax.set_xlabel('Тип теста', fontsize=12)
    ax.set_ylabel('Bandwidth (MiB/s)', fontsize=12)
    ax.set_title('Сравнение Bandwidth между конфигурациями', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([t.replace(' ', '\n') for t in all_tests], rotation=0, ha='center')
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'fio_bandwidth_comparison.png'), dpi=300)
    plt.close()
    
    # График Latency
    fig, ax = plt.subplots(figsize=(14, 8))
    
    for idx, (label, data) in enumerate(datasets.items()):
        lat_values = []
        lat_errors = []
        for test in all_tests:
            if test in data.get('fio', {}):
                lat_values.append(data['fio'][test]['Latency_mean'])
                lat_errors.append(data['fio'][test]['Latency_stdev'])
            else:
                lat_values.append(0)
                lat_errors.append(0)
        
        offset = width * idx - width * (len(datasets) - 1) / 2
        ax.bar([i + offset for i in x], lat_values, width,
               label=label, yerr=lat_errors, capsize=5, alpha=0.8)
    
    ax.set_xlabel('Тип теста', fontsize=12)
    ax.set_ylabel('Latency (ms)', fontsize=12)
    ax.set_title('Сравнение задержки между конфигурациями', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([t.replace(' ', '\n') for t in all_tests], rotation=0, ha='center')
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'fio_latency_comparison.png'), dpi=300)
    plt.close()
    
    print("✅ Графики FIO созданы")

def plot_pgbench_comparison(datasets, output_dir):
    """Создает графики сравнения pgbench тестов"""
    
    # Фильтруем датасеты с данными pgbench
    pgbench_data = {label: data for label, data in datasets.items() 
                    if 'pgbench' in data and data['pgbench']}
    
    if not pgbench_data:
        print("⚠️  Нет данных pgbench для визуализации")
        return
    
    labels = list(pgbench_data.keys())
    
    # График TPS
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    tps_values = [data['pgbench']['TPS_mean'] for data in pgbench_data.values()]
    tps_errors = [data['pgbench']['TPS_stdev'] for data in pgbench_data.values()]
    
    bars1 = ax1.bar(range(len(labels)), tps_values, yerr=tps_errors, 
                    capsize=10, alpha=0.8, color='steelblue')
    ax1.set_xlabel('Конфигурация', fontsize=12)
    ax1.set_ylabel('TPS (Transactions Per Second)', fontsize=12)
    ax1.set_title('Сравнение TPS (pgbench)', fontsize=14, fontweight='bold')
    ax1.set_xticks(range(len(labels)))
    ax1.set_xticklabels(labels, rotation=45, ha='right')
    ax1.grid(axis='y', alpha=0.3)
    
    # Добавляем значения над столбцами
    for i, (bar, val, err) in enumerate(zip(bars1, tps_values, tps_errors)):
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height + err,
                f'{val:.0f}\n±{err:.0f}',
                ha='center', va='bottom', fontsize=9)
    
    # График Latency
    lat_values = [data['pgbench']['Latency_Avg_mean'] for data in pgbench_data.values()]
    lat_errors = [data['pgbench']['Latency_Avg_stdev'] for data in pgbench_data.values()]
    
    bars2 = ax2.bar(range(len(labels)), lat_values, yerr=lat_errors,
                    capsize=10, alpha=0.8, color='coral')
    ax2.set_xlabel('Конфигурация', fontsize=12)
    ax2.set_ylabel('Средняя задержка (ms)', fontsize=12)
    ax2.set_title('Сравнение задержки (pgbench)', fontsize=14, fontweight='bold')
    ax2.set_xticks(range(len(labels)))
    ax2.set_xticklabels(labels, rotation=45, ha='right')
    ax2.grid(axis='y', alpha=0.3)
    
    # Добавляем значения над столбцами
    for i, (bar, val, err) in enumerate(zip(bars2, lat_values, lat_errors)):
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height + err,
                f'{val:.2f}\n±{err:.2f}',
                ha='center', va='bottom', fontsize=9)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'pgbench_comparison.png'), dpi=300)
    plt.close()
    
    print("✅ Графики pgbench созданы")

def plot_scalability(datasets, output_dir):
    """Создает графики масштабируемости (зависимость от количества ВМ)"""
    
    # Группируем по количеству ВМ
    vm_groups = {}
    for label, data in datasets.items():
        num_vms = data.get('num_vms', 1)
        if num_vms not in vm_groups:
            vm_groups[num_vms] = []
        vm_groups[num_vms].append((label, data))
    
    if len(vm_groups) < 2:
        print("⚠️  Недостаточно данных для анализа масштабируемости")
        return
    
    vm_counts = sorted(vm_groups.keys())
    
    # Выбираем несколько ключевых тестов для анализа
    key_tests = ['Sequential Read', 'Sequential Write', 'Random Read', 'Random Write']
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    axes = axes.flatten()
    
    for idx, test_name in enumerate(key_tests):
        ax = axes[idx]
        
        iops_by_vms = []
        for vm_count in vm_counts:
            # Берем среднее по всем датасетам с данным количеством ВМ
            iops_values = []
            for label, data in vm_groups[vm_count]:
                if test_name in data.get('fio', {}):
                    iops_values.append(data['fio'][test_name]['IOPS_mean'])
            if iops_values:
                iops_by_vms.append(sum(iops_values) / len(iops_values))
            else:
                iops_by_vms.append(0)
        
        ax.plot(vm_counts, iops_by_vms, marker='o', linewidth=2, markersize=10)
        ax.set_xlabel('Количество ВМ', fontsize=11)
        ax.set_ylabel('IOPS (тысячи)', fontsize=11)
        ax.set_title(f'Масштабируемость: {test_name}', fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3)
        
        # Добавляем значения на точки
        for x, y in zip(vm_counts, iops_by_vms):
            ax.annotate(f'{y:.0f}', (x, y), textcoords="offset points",
                       xytext=(0,10), ha='center', fontsize=9)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'scalability_analysis.png'), dpi=300)
    plt.close()
    
    print("✅ График масштабируемости создан")

def main():
    if len(sys.argv) < 2:
        print("Использование: python3 visualize_results.py <json_файл1> [json_файл2] ...")
        print("\nПример:")
        print("  python3 visualize_results.py results/*/aggregated_report.json")
        print("  python3 visualize_results.py storage1.json storage2.json")
        sys.exit(1)
    
    # Загружаем все JSON файлы
    datasets = {}
    for json_path in sys.argv[1:]:
        if not os.path.exists(json_path):
            print(f"⚠️  Файл не найден: {json_path}")
            continue
        
        data = load_aggregated_data(json_path)
        
        # Извлекаем метку из пути (например, имя директории или файла)
        label = Path(json_path).parent.name
        if label == "." or not label:
            label = Path(json_path).stem
        
        datasets[label] = data
        print(f"✅ Загружен: {json_path} -> {label}")
    
    if not datasets:
        print("❌ Не удалось загрузить данные")
        sys.exit(1)
    
    # Создаем директорию для графиков
    output_dir = "visualization_output"
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"\n📊 Создание графиков в: {output_dir}/")
    
    # Создаем графики
    plot_fio_comparison(datasets, output_dir)
    plot_pgbench_comparison(datasets, output_dir)
    plot_scalability(datasets, output_dir)
    
    print(f"\n✅ Визуализация завершена!")
    print(f"📁 Графики сохранены в: {output_dir}/")
    print("\nСозданные файлы:")
    for file in sorted(os.listdir(output_dir)):
        if file.endswith('.png'):
            print(f"  • {file}")

if __name__ == "__main__":
    main()