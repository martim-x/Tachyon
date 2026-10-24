#!/usr/bin/env bash
# Границы доменов: автоматическая проверка (docs/02 §дисциплина границ).
# Запускается в CI и локально: bash scripts/check_boundaries.sh
set -uo pipefail

fail=0
report() { echo "FAIL: $1"; fail=1; }

# grep с различением "совпадений нет" (0/1) и реальной ошибки (2).
# stderr не прячем: ошибка grep должна быть видна, а не маскироваться
# под "граница соблюдена".
run_grep() {
  # $1 — шаблон, остальное — пути/флаги. Печатает совпадения на stdout.
  grep -rn "$@" 2>&1
}

required_paths=(
  app/domains/forecasting
  app/domains/reporting
  app/core/money.py
  app/infrastructure/scheduler.py
)
for path in "${required_paths[@]}"; do
  if [ ! -e "$path" ]; then
    report "отсутствует проверяемый путь: $path"
  fi
done

# forecasting — чистое ядро: без SQLAlchemy и FastAPI.
output=$(run_grep -E "^[[:space:]]*(from|import)[[:space:]]+(sqlalchemy|fastapi)" app/domains/forecasting/); rc=$?
if [ "$rc" -eq 2 ]; then report "grep завершился ошибкой: $output"
elif [ "$rc" -eq 0 ]; then report "forecasting импортирует sqlalchemy/fastapi"; echo "$output"
fi

# reporting — только чтение: никаких commit().
raw_output=$(run_grep "\.commit(" app/domains/reporting/); raw_rc=$?
output=$(echo "$raw_output" | grep -Ev ":[0-9]+:[[:space:]]*#" || true)
rc=$raw_rc
if [ "$raw_rc" -eq 0 ] && [ -z "$output" ]; then rc=1; fi
if [ "$rc" -eq 2 ]; then report "grep завершился ошибкой: $output"
elif [ "$rc" -eq 0 ]; then report "reporting вызывает commit()"; echo "$output"
fi

# apscheduler — только в infrastructure/scheduler.py.
output=$(run_grep -rl "apscheduler" app/ --include="*.py"); rc=$?
if [ "$rc" -eq 2 ]; then report "grep завершился ошибкой: $output"
elif [ "$rc" -eq 0 ]; then
  bad=$(echo "$output" | grep -v "app/infrastructure/scheduler.py" || true)
  if [ -n "$bad" ]; then report "apscheduler вне app/infrastructure/scheduler.py"; echo "$bad"; fi
fi

# Деньги: только Decimal, никакого float в money/forecasting.
raw_output=$(run_grep -E "float\\(" app/core/money.py app/domains/forecasting/); raw_rc=$?
output=$(echo "$raw_output" | grep -Ev ":[0-9]+:[[:space:]]*#" || true)
rc=$raw_rc
if [ "$raw_rc" -eq 0 ] && [ -z "$output" ]; then rc=1; fi
if [ "$rc" -eq 2 ]; then report "grep завершился ошибкой: $output"
elif [ "$rc" -eq 0 ]; then report "float() в money/forecasting"; echo "$output"
fi

if [ "$fail" -ne 0 ]; then
  echo "Проверка границ провалена."
  exit 1
fi

echo "Проверка границ пройдена."
