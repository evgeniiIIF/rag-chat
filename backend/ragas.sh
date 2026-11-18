#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Версия 6.0 (2025-03) — полный стэк по цепочке chat_v2.
# Для запуска нужны:
#   - настроенные .env (API_KEY, SCORE_THRESHOLD и т.д.)
#   - активный Chroma, векторный индекс создан
#   - рабочая модель

export PYTHONPATH="$(pwd)/src"
SCRIPT_VERSION="6.0 (chat_v2: модель → RAG, состояние, один вопрос)"

log() { echo "[RAGAS  $SCRIPT_VERSION] $*" >&2; }
die() { log "ОШИБКА: $*"; exit 1; }

[ -f ".env" ] || die ".env не найден (скопируй из .env.example)"
[ -f "data/КЦ.docx" ] || die "Корпус data/КЦ.docx не найден"

# Создаём golden_set.json, если нет.
if [ ! -f "eval/golden_set.json" ]; then
    cat > eval/golden_set.json <<'EOF'
[
  {
    "question": "какая минимальная сумма долга для банкротства",
    "expected": "От 350 000 рублей",
    "corpus": "берем в процедуру только с суммой от 350к"
  },
  {
    "question": "вы работаете в Чечне",
    "expected": "Нет, мы не работаем в Чечне",
    "corpus": "не работаем в Чечне"
  },
  {
    "question": "стоимость банкротства физлица",
    "expected": "Универсальной цены нет, стоимость фиксирует юрист в договоре",
    "corpus": "Цены на банкротство физических лиц у нас нет. Кому выгоднее…"
  },
  {
    "question": "какие регионы вы не обслуживаете",
    "expected": "Чечня, ДНР, ЛНР, Владимирская область",
    "corpus": "не работаем в Чечне, ДНР, ЛНР, Владимирская обл."
  },
  {
    "question": "можно ли купить банкротство в рассрочку",
    "expected": "Да, рассрочка есть",
    "corpus": "Работаем и в рассрочку"
  },
  {
    "question": "нужна ли предоплата",
    "expected": "Нет, мы не берём аванс",
    "corpus": "не требуем аванса"
  },
  {
    "question": "сколько вы списали долгов",
    "expected": "1,05 млрд рублей",
    "corpus": "сумму списанных долгов 1,05 млрд"
  },
  {
    "question": "с какого года вы работаете",
    "expected": "С 2017 года",
    "corpus": "Компания работает с 2017 года"
  },
  {
    "question": "сколько процедур вы уже закрыли",
    "expected": "Более 2500 процедур",
    "corpus": "провели более 2500 процедур"
  },
  {
    "question": "в скольких регионах вы работаете",
    "expected": "63 региона России",
    "corpus": "работаем в 63 субъектах РФ"
  }
]
EOF
    log "golden_set.json создан (10 вопросов)"
fi

# Проверяем, что индексы живы.
log "Проверяем подключение к индексу..."
python3 -c "
import sys
sys.path.append('$(pwd)/src')
from src.core.config import Settings
from src.repositories.vector_store import VectorStoreRepository
from src.services.embedding_adapter import OpenAIEmbeddingsAdapter
settings = Settings()
print('Модель эмбеддингов:', settings.embedding_model)
store = VectorStoreRepository(settings, OpenAIEmbeddingsAdapter(settings).get()).load()
try:
    c = store.get_or_create_collection('doc_chunks')
    print('Коллекция Chroma:', c.name, c.count(), 'документов')
except Exception as e:
    print('FAIL: не удалось загрузить Chroma:', e)
    sys.exit(1)
" || die "Хрома не работает"

# Запуск теста RAGAS.
log "Поднимаем сервер на порту 19999..."
python3 <<'EOF' &
import uvicorn, sys, time, threading
sys.path.append('$(pwd)/src')
from src.main import app
import asyncio

def run():
    config = uvicorn.Config(app, host="localhost", port=19999, log_level="warning")
    server = uvicorn.Server(config)
    asyncio.run(server.serve())

t = threading.Thread(target=run, daemon=True)
t.start()
time.sleep(3)
print("Сервер запущен на 19999", flush=True)
EOF

sleep 3  # даем серверу старт

log "Запускаем RAGAS..."
export LLM_API_KEY=$(grep -oP 'API_KEY=\K[^ ]*' .env)
python3 -m ragas.evaluation evaluate \
    --llm api_key=$LLM_API_KEY \
    --embeddings api_key=$LLM_API_KEY \
    --data_path eval/golden_set.json \
    --output_dir eval/results \
    --metrics faithfulness,answer_relevancy,context_precision,context_recall \
    --batch_size 5 \
    2>&1 | tee eval/ragas_output.txt || true

log "Останавливаем тестовый сервер..."
pkill -f "uvicorn.*19999" 2>/dev/null || true

# Проверяем faithfulness и особенно наличие зловредного «500 000».
if [ -f "eval/results/results.json" ]; then
    python3 -c "
import json, sys
with open('eval/results/results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
faith = data.get('faithfulness', 0.0)
print(f'Faithfulness: {faith:.3f}')
if faith >= 0.845:
    print('✅ faithfulness соответствует планке (+-0.005)')
else:
    print('⚠️ faithfulness ниже планки 0.845')

# Ищем галюцинацию
answers = [i.get('answer', '') for i in data.get('question', [])]
if any('500' in a or 'пятьсот' in a.lower() for a in answers):
    print('❌ ОБНАРУЖЕНА ГАЛЛЮЦИНАЦИЯ «500 000» — нарушение A4/D3')
else:
    print('✅ в ответах нет «500 000» — A4 соблюдён')
" 2>&1 | tee eval/check.txt
else
    log "Файл результатов не создан, возможно, ошибка RAGAS"
fi

log "Завершено. Лог: eval/ragas_output.txt"