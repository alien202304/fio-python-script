# PostgreSQL & fio Performance Testing Suite

## Архитектура
- **Управляющая машина**: MacBook (или любой control host)
- **Тестовые ВМ**: 1–4 машины с Debian 12, PostgreSQL 17, XFS
- **Сценарии**: fio → pgbench → сбор → анализ

## Быстрый старт
1. Настрой ВМ по `TESTING_METHOD.md`
2. Скопируй `scripts/` на все ВМ
3. На MacBook:  
   ```bash
   ./control/run_tests.sh
   python3 control/tools/parse_results.py results/run_20251106_1200
