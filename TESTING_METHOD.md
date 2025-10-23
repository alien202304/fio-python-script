### Методика тестирования производительности PostgreSQL 17 на локальном и iSCSI-хранилище
#### 	Версия: 1.1
####	Дата: 22 октября 2025 г.
#### 	Цель: Сравнить производительность дисковой подсистемы и СУБД PostgreSQL 17 при размещении ВМ на локальном RAID10 (Dell R750) и на внешнем iSCSI-СХД, подключённом по 25/100GbE в среде VMware vSphere 8.

#### 1. Общие положения
Тестирование проводится на одном хосте ESXi в кластере Т4 ДЦ ВКС.

Сравниваются два типа хранилищ:
+ Локальный: VMFS на RAID10, собранный из 8 локальных дисков на хосте Dell R750.
+ Сетевой: VMFS на выделенном LUN iSCSI-СХД (без фоновой нагрузки).

Все ВМ идентичны и работают под управлением Debian 12.

Тесты включают:
+ Низкоуровневую нагрузку (fio, 60 сек на тест)
+ Прикладную нагрузку (pgbench)

Используем следующие сценарии:
+ 1 ВМ
+ 4 ВМ одновременно на одном хосте

Смешанная нагрузка (mixed RW): 60% запись / 40% чтение.

#### 2. Конфигурация виртуальных машин
| Параметр  | Значение |
|:-----------|:--------------|
| ОС		| Debian 12 (bookworm) |
| vCPU		| 4	ядра		|
| RAM		| 16 ГБ		|
| Системный диск | 30 ГБ, Thick Eager Zeroed |
| Диск данных PostgreSQL | 50 ГБ, отдельный VMDK, Thick Eager Zeroed, контроллер PVSCSI |
| Файловая система системного диска | btrfs |
| Файловая система данных | XFS (noatime, logbufs=8, logbsize=256k) |
| Swap | Отключён |
| Сетевой адаптер | VMXNET3 |
> Диск данных монтируется в /mnt/pgdata и используется как PGDATA


#### 3. Подготовка ВМ
##### 3.1 Базовая настройка ОС
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y wget ca-certificates sysstat dstat htop xfsprogs

# Отключение swap
sudo swapoff -a
sudo sed -i '/ swap / s/^/#/' /etc/fstab

# Настройка ядра
cat <<EOF | sudo tee -a /etc/sysctl.conf
vm.swappiness = 1
vm.overcommit_memory = 2
kernel.shmmax = 4294967296
kernel.shmall = 1048576
EOF
sudo sysctl -p

# Лимиты
cat <<EOF | sudo tee -a /etc/security/limits.conf
* soft nofile 65536
* hard nofile 65536
postgres soft nofile 65536
postgres hard nofile 65536
EOF

sudo reboot
```

##### 3.2 Настройка диска под PostgreSQL
```bash
sudo mkdir -p /mnt/pgdata
echo '/dev/sdb /mnt/pgdata xfs defaults,noatime,logbufs=8,logbsize=256k 0 0' | sudo tee -a /etc/fstab
sudo mount -a
sudo chown postgres:postgres /mnt/pgdata
```

##### 3.3 Установка PostgreSQL 17
```bash
sudo systemctl stop postgresql

# Инициализация на новом томе
sudo -u postgres initdb -D /mnt/pgdata

# Указать PGDATA
sudo sed -i "s|data_directory = '.*'|data_directory = '/mnt/pgdata'|" /etc/postgresql/17/main/postgresql.conf

# Добавить настройки производительности в /mnt/pgdata/postgresql.conf
cat <<EOF | sudo tee -a /mnt/pgdata/postgresql.conf

# === Performance Tuning ===
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
EOF

# Разрешить подключения (только для тестов!)
echo "local all all trust" | sudo tee /mnt/pgdata/pg_hba.conf
echo "host all all 0.0.0.0/0 trust" | sudo tee -a /mnt/pgdata/pg_hba.conf

sudo systemctl start postgresql@17-main
sudo systemctl enable postgresql@17-main
```

> В Debian 12 служба PostgreSQL 17 называется postgresql@17-main

#### 4. План тестирования
| Этап | Тип хранилища | Кол-во в тесте | Тип нагрузки | Кол-во повторов тестов |
|:-----|:--------------|:---------------|:-------------|:-----------------------|
|1 | Локальное | 1 | скрипт fio (60 сек) | 	3 |
|2 | Локальное | 4 | скрипт fio (60 сек) | 3|
|3 | Локальное | 1 | pgbench | 3 |
|4 | Локальное | 4 | pgbench | 3 |


