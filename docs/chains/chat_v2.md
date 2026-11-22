🎛 ════ · 22:16:19 · 960 файлов · 0 символов · ✓

ЦЕЛЬ (критерии приёмки, проверяемые):
A1. «про гипопотамов» → модель по корпусе понимает, что такой темы нет; НЕ угаывает
    («наверное, опечатка, вы про ипотеку…»), НЕ сворачивает в допрос про сумму.
A2. Сущности («310к», «пятьсот тысяч», «Владимирская область», «рассрочка», город)
    извлекает модель. Для деловых фактов в коде нет словарей слов и регулярок.
A3. Приветствие короткое: «Привет! Я ассистент по банкротству. Чем могу помочь?»
    Повтор приветствия: «Мы уже на связи. Расскажите о вашей ситуации — чем помочь?»
    ↑ по решению D1 эта ветка остаётся хардкодом (таблица строк, не размазана по if-ам).
A4. Ни одного факта/числа вне корпуса. В корпусе ЕСТЬ: «берем в процедуру только с суммой
    от 350к»; не работаем: Чечня, ДНР, ЛНР, Владимирская обл.; с 2017 г.; 2500+ процедур;
    1,05 млрд списано; 63 субъекта РФ; без аванса; рассрочка; цена фиксируется в договоре.
    В корпусе НЕТ «500 000 ₽» → теперешний ответ про 500к = баг (галлюцинация).
    Эталон проверки: backend/eval/golden_set.json (10 вопросов, там «От 350 000 рублей»).
A5. Один уточняющий вопрос на ответ; уже заданный вопрос не повторяется.
A6. «давайте консультацию» → ветка handoff, а не очередной допрос про сумму.
A7. Логика ответа = как в эталонном чате: признать слова клиента → сказать только то, что
    реально есть в корпусе → один направляющий шаг. Без выдуманных условий и запугивания.

РЕШЕНИЯ (зафиксированы, в коде не пересматриваются):
D1. Хардкод РАЗРЕШЁН только для: социальных реплик (привет/спасибо/пока) и защитных
    списков (токсика/injection) → узлы 19, 20 остаются как есть.
D2. Хардкод ЗАПРЕЩЁН для: извлечения деловых сущностей, определения «в теме/не в теме»,
    стадий диалога, формулировок уточняющих вопросов, критерия «знаю/не знаю» → узлы 09, 12, 13.
D3. Ответ строго по RAG-контексту: чего нет в корпусе — того для чата не существует.
D4. Вне темы — 1–2 короткие строки по A7; встречный вопрос только по теме корпуса.
D5. (Q1) На реплику ДВА LLM-вызова: 09 анализ → 11 поиск → 14 ответ. Иначе нельзя:
    поисковый запрос рождается в 09, а контекст для ответа известен только после 11.
    Экономия: 09 = короткий JSON (max_tokens ≈ 400, temperature 0, не reasoning-модель),
    14 = обычный генератор. Порога «лишнего» вызова нет: анализ не зовётся вовсе,
    если реплика ушла в SocialBranch (19) или InputGuardrail (20).
D6. (Q2) Состояние — in-memory 🗄️ SessionStore в процессе (в compose один backend-контейнер,
    Redis/Postgres в стеке нет). TTL 24ч + LRU-потолок сессий.
    Рестарт не ломает диалог: при промахе сессии DialogState собирается ХОЛОДНЫМ стартом
    из клиентской истории (последние 10 реплик) тем же вызовом 09 — факты и asked_already
    извлекаются из истории, отдельного LLMP-вызова на bootstrap нет.
    FE шлёт последние 30 реплик (потолок HISTORY_MAX_TURNS поднят в S04).

────────────────────────────────────────────────────────
ДИАГНОЗ (проверено по коду и по КЦ.docx)
────────────────────────────────────────────────────────
1. Деловое «понимание» написано хардкодом, поэтому тупит:
   - IntentDetector: словари GREETING_TOKENS/THANKS_TOKENS + ТОЧНОЕ совпадение строки →
     «банкротство надо», «давайте консультацию», «давай стоимость» = QUESTION без маршрута.
     (сама соц-ветка — ок по D1; плохо, что реплика-простыня и нет деловых намерений)
   - ProfileMemory: regex по суммам + список городов → «310к» ловит кое-как, «пятьсот» — нет
   - DialogStrategy: FSM WELCOME→QUALIFY→… со списком «чего не хватает» в коде
   - QueryCondenser: склеивает последние 3 реплики ВМЕСТЕ с длинными ответами бота в один
     «standalone-запрос» → эмбеддинг размывается, в топ-k попадает случайное
2. Состояния нет: ChatService.ask() создаёт ProfileMemory() и DialogStrategy() заново на
   каждый запрос → FSM вечно стартует с WELCOME → шаг 13 цепочки chat.md мёртв, повторы
   вопросов не помнятся → «информацию вытягиваем клещами».
3. Галлюцинации разрешены конфигом и промптом:
   - SCORE_THRESHOLD=0.02 (.env) → passes_threshold() истинна почти всегда →
     Grounding.NOT_ANSWERABLE физически недостижима, «Не знаю» невозможна, LLM отвечает на всё
   - в SYSTEM_INSTRUCTION нет запрета додумывать смысл слова и нет запрета на цифры,
     которых нет в контексте; сам корпус — скрипт продаж (60 абз., 18К зн.), а не закон
4. У корпуса нет «карты тем» → нечем проверять «в теме ли вопрос» (отсюда «гипопотамы»).

────────────────────────────────────────────────────────
ЦЕПОЧКА v2 (единственный источник истины; код = производное)
────────────────────────────────────────────────────────
Правило ветки: деловое понимание и решения — у модели (LLM-порты). В коде — состояния,
границы, хранение и соц-реплики (D1). Никаких regex-«понималок» и словарей по делу (D2).

[FE] 01 🧩 component   <ChatPage/>.onSubmit(question)                ─► useChat
[FE] 02 🧩 hook        useChat().mutateAsync({question, sessionId})  ─► ChatApi
[FE] 03 📡 http        ChatApi.post + session_id в localStorage      ─► HttpClient
[FE] 04 🚦 middleware  CsrfInterceptor / UnauthorizedInterceptor
[FE] 05 🧩 component   <ChatMessageList/>.render(ChatResponse)

[BE] 06 🎛️ controller   ChatRouter.chat(ChatRequest)                 ─► 19
        └─x─► 🚨 422 [schema]
[BE] 19 🛡️ guard        InputGuardrail.check(q) ─► bool                (D1, остаётся)
        ├─ «здравствуйте» (первое) ─► «Привет! Я ассистент по банкротству. Чем могу помочь?»
        ├─ «здравствуйте» (повтор) ─► «Мы уже на связи. Расскажите о вашей ситуации — чем помочь?»
        ├─ спасибо ─► «Пожалуйста! Если есть ещё вопросы — спрашивайте.»
        ├─ пока ─► «До свидания! Если понадобится помощь — обращайтесь.»
        └─ None ─► дальше по деловой ветке (07)
[BE] 20 🛡️ guard        SocialBranch.replica(q, history) ─► str|None   (D1, хардкод остаётся)
        └─ ─x─► false ─► 16 🎁 present(GUARDRAIL_REPLY, NOT_ANSWERABLE)
[BE] 07 🗄️ repository   SessionStore.load(sessionId) ─► DialogState(turns, facts, asked)
        ├─ in-memory dict, TTL 24ч, LRU-потолок (D6)
        └─ miss ─► DialogState.empty() + 09 достраивает состояние из клиентской истории
[BE] 08 🧭 use-case     TopicsMap.of(corpus) ─► список тем корпуса    [LLM, при индексации]
        └─ кэш по content_hash(docx); НЕ константа в коде
[BE] 09 🧭 use-case     TurnAnalyzer.analyze(q, recent, state, topics) ─► Analysis  [LLM #1]
        ├─ Analysis.scope ∈ in_kb | off_kb | clarify           (по topics, не по словарю)
        ├─ Analysis.question: самостоятельная формулировка     (замена QueryCondenser)
        ├─ Analysis.facts: свободный словарь деловых фактов    (замена ProfileMemory-regex)
        ├─ Analysis.missing: чего не хватает для консультации  (источник — корпус)
        ├─ Analysis.asked_already: что уже спрашивали          (запрет повтора, A5)
        └─ Analysis.style ∈ one_line | explain | reassure
[BE] 10 💎 entity       DialogState.merge(Analysis.facts, Analysis.asked_already)
        └─ + merge(asked=[Policy.ask_about]): что спросили — помнит код, не модель (A5)
[BE] 13 🧭 use-case     Policy.decide(Analysis, DialogState) ─► action          [идёт до 11]
        ├─ answer | ask_one | handoff | decline_offtopic | rephrase
        ├─ в коде только выбор действия; темы и формулировки приходят из Analysis (D2)
        └─ action из off-topic/clarify/handoff веток поиск 11 НЕ зовёт (экономия вызова/индекса)
[BE] 11 🗄️ repository   HybridRetriever.search(Analysis.question, k) ─► hits
[BE] 12 🚦 guard        RelevanceGate.judge(hits, settings) ─► ok | low
        ├─ числовой порог Settings.score_threshold (0.02 → 0.35), замер: `make probe`
        ├─ вердикт модели «есть ли ответ в чанках» = маркер NO_ANSWER в 14 → 15 (D5: без 3-го вызова)
        └─ ─x─► low ─► 14 с пустым контекстом: «уточнит юрист», а не цифра из чужого абзаца
[BE] 14 🧭 use-case     AnswerGenerator.generate(question, context, state, action)  [LLM #2]
        ├─ отвечать ТОЛЬКО по context (D3); нет в context → сказать, что темы нет /
        │  это проверит юрист; запрещено додумывать смысл слова и опечатки
        ├─ запрещены любые числа, сроки, условия, которых нет в context
        ├─ action=ask_one → РОВНО один вопрос (A5), не спрашивать то, что уже в state.asked
        ├─ action=handoff → не рекламировать консультацию, собирать время/контакты (A6)
        ├─ action=decline_offtopic → 1–2 строки, без встречного вопроса про долг (D4)
        └─ порядок реплики по A7: признать → только факты корпуса → один направляющий шаг
[BE] 15 🚦 gate         AnswerGate.gate(hits, answer, settings) ─► Grounding
[BE] 16 🎁 presenter    ChatPresenter.present(answer, grounding, hits, expanded) ─► ChatResponse
[BE] 17 🗄️ repository   SessionStore.save(sessionId, DialogState)
[BE] 18 📤 response     HTTP 200 ChatResponse

УДАЛЯЕТСЯ (противоречит A1–A7, D2, D3):
- ProfileMemory (regex + список городов)                     → 09.facts
- DialogStrategy (FSM + список missing в коде; состояние и так сбрасывалось) → 13
- QueryCondenser (склейка истории в запрос)                  → 09.question
- SCORE_THRESHOLD=0.02 как единственный критерий «знаю»      → 12
ОСТАЁТСЯ КАК ЕСТЬ (D1): InputGuardrail (19), Intent.detect + SocialBranch (20).

────────────────────────────────────────────────────────
ШАГИ РАБОТ (1 шаг = 1 правка кода = 1 апдейт цепочки)
────────────────────────────────────────────────────────
✅ S01 откат STEP-2-костыля — profile_memory.py возвращён к regex-версии (умерла в S12: файл удалён)
✅ S02 🛡️ SocialBranch (src/services/social_branch.py): GREETING_FIRST/GREETING_REPEAT/
        THANKS_REPLY/BYE_REPLY — короткие строки A3; replica(q, history) → str|None.
        Подключён к /chat в S12, unit — test_social_branch.py
✅ S03 💎 DialogState (src/models/dialog_state.py: facts/asked/merged/pending/asked_about) +
        🗄️ SessionStore (src/services/session_store.py: TTL 24ч, LRU, max_turns 30, dedupe_turns)
        + tests/unit/test_dialog_state.py, tests/unit/test_session_store.py
✅ S04 🎛️ ChatRequest.session_id (опц., max 64) + потолок истории 10 → 30 (константа
        HISTORY_MAX_TURNS); 📡 FE: src/features/chat/session.ts (localStorage + фолбэк в память
        вкладки), ChatPage шлёт session_id и последние 30 реплик, zod max 30 + тесты session.test.ts,
        chatSchema.test.ts обновлены
✅ S05 🧭 TopicsMap (src/services/topics_map.py): TOPICS_SYSTEM + parse_topics + кэш по
        sha256(текст корпуса) и cache_key; деградация в Topics.empty() при сбое модели;
        tests/unit/test_topics_map.py
✅ S06 🧭 TurnAnalyzer (src/services/turn_analyzer.py) + 💎 Analysis (src/models/analysis.py:
        scope in_kb|off_kb|clarify, question, facts, missing, asked_already,
        wants_consultation, style). Один вызов LLM-порта, JSON-контракт, fallback на
        Analysis.fallback(исходный вопрос) при мусоре/сбое. Порт вынесен в
        src/services/llm_port.py (узел 18). Tests: tests/unit/test_turn_analyzer.py
✅ S07 🗄️ запрос поиска = Analysis.question: ChatService._retrieve бёт analysis.question
        (при пустом — текст клиента). История в запрос не попадает (QueryCondenser удалён)
✅ S08 🚦 RelevanceGate (src/services/relevance_gate.py): числовой порог из Settings
        (REASON_EMPTY/BELOW_THRESHOLD/OK) + замер скоров eval/score_probe.py (`make probe`).
        SCORE_THRESHOLD поднят 0.02 → 0.35 во всех .env (0.02 делал «Не знаю» недостижимым).
        Вердикт «в контексте ответа нет» остаётся за генератором (маркер NO_ANSWER → 15),
        третьего вызова модели нет по D5. Tests: tests/unit/test_relevance_policy.py
✅ S09 💎 DialogState.merged/pending/asked_about + ChatService сам помечает asked_about
        выбранного Policy-вопроса → повтор невозможен даже если модель не узнала свой
        вопрос в истории. Tests: test_dialog_state.py, test_chat_service.py
✅ S10 🧭 Policy (src/services/policy.py): Action = answer | ask_one | handoff |
        decline_offtopic | rephrase; в коде только выбор действия (D2)
✅ S11 🧭 AnswerGenerator: новый SYSTEM_INSTRUCTION (D3 запрет цифр вне контекста, A5 один
        вопрос, A7 порядок «услышал → факт → шаг», D4 off-topic) + сборка промпта с блоками
        «Что известно» / «О чём уже спрашивали» / «Задача этого хода».
        Tests: tests/unit/test_answer_generator.py
✅ S12 🧩 ChatService → тонкий оркестратор (guardrail → social → store → analyzer → state →
        policy → retriever → relevance → generator → answer_gate → presenter → save).
        УДАЛЕНО: profile_memory.py, dialog_strategy.py, query_condenser.py,
        conversation_memory.py + их unit-тесты. DI пересобран в main.py,
        новые env: SESSION_TTL_SECONDS / SESSION_MAX_SESSIONS / SESSION_MAX_TURNS.
        Grounding + SOCIAL (соц/clarify/handoff не показывают плашку «не найдено»)
✅ S13 🧪 сценарные тесты A1–A7 (tests/unit/test_dialog_scenarios.py) + test_social_branch.py
        + e2e на session_id/потолок истории (tests/e2e/test_chat.py). 99 unit-прогонов зелёные
⚠️ S14 VERIFY (запускает пользователь): `cd backend && make check` → exit 0
⚠️ S15 VERIFY (запускает пользователь): `cd backend && make probe` → назвать порог по факту;
        `./ragas.sh` faithfulness не ниже 0.845 и «минимальная сумма» → «от 350 000»,
        НИКАКОГО «500 000»
⚠️ S16 VERIFY (ручной прогон в UI): «про гипопотамов», «здравствуйте»×2,
        «банкротство надо юрист нужен», «давай стоимость», «давайте консультацию»,
        «рассрочку на 310к платить уже не могу», «непонял», «какая разница» → сверка A1–A7

────────────────────────────────────────────────────────
УТОЧНЕНИЯ ЦЕПОЧКИ ПО ФАКТУ РЕАЛИЗАЦИИ (код ↔ цепочка синхронно)
────────────────────────────────────────────────────────
1. Порядок узлов: 19 🛡️ InputGuardrail.check → 20 🛡️ SocialBranch.replica (токсика/инъекции
   отсекаются раньше, чем что-либо уйдёт в модель).
2. Scope + clarify (узел 09), Action + rephrase (узел 13): клиент «непонял» → переформулировать
   свой прошлый вопрос, а не искать по бессмысленному запросу.
3. Узел 12 = только числовой порог; «есть ли в чанках ответ» решает генератор маркером
   NO_ANSWER (узел 14 → 15). Третьего LLM-вызова нет (D5).
4. Низкий скор (12 = low) ведёт в 14 с action=decline_offtopic и ПУСТЫМ контекстом:
   клиент получает «уточнит юрист», а не цифру из нерелевантного абзаца.
5. NO_ANSWERMarker наружу не отдаётся: 16 показывает NO_MATCH_REPLY
   («Такого нет в нашей базе. Точный ответ даст юрист на бесплатной консультации.»).
   GUARDRAIL_REPLY и NO_MATCH_REPLY — аварийные строки, фактов о компании не содержат (D1).
6. Grounding.SOCIAL (узел 15/16) для соц-реплик, handoff и rephrase: grounded=true,
   sources=[], плашка «Ответ в документе не найдено» не показывается.
7. Дедупликация истории: лента сервера + история клиента склеиваются dedupe_turns по
   (role, content), поэтому холодный старт после рестарта не удваивает реплики.

────────────────────────────────────────────────────────
⚠️ ОГРАНИЧЕНИЯ (приняты осознанно, D6)
────────────────────────────────────────────────────────
1. SessionStore in-process: при >1 uvicorn-воркером состояние живёт в воркере, попадание
   на другой = холодный старт из клиентской истории (диалог не ломается, факты теряются).
   В compose один backend-контейнер → риск нулевой, при масштабировать → выносить в Redis.
2. Порог 0.35 выбран по коду hybrid-скоринга, НЕ по живому замеру → обязателен `make probe`
   (S15). Если позитивные и негативные скоры пересекаются, порог опускаем и полагаемся на
   NO_ANSWER-вердикт модели.
3. ANALYZER и GENERATOR делят один чат LLM (LLM_MODEL) и один max_tokens: отдельного
   лимита токенов на анализ пока нет (D5 хотел ~400) — кандидат на следующую итерацию
   (добавить max_tokens в LLMPort.complete).
4. Ключей «знаю/не знаю» в коде нет: если TopicsMap не смог построить темы (сбой модели),
   scope почти всегда in_kb → A1 деградирует до порога 12 и NO_ANSWER-вердикта 14.

────────────────────────────────────────────────────────
ГОТОВО К VERIFY (S01–S13 ✅, S14–S16 ⚠️ ждут запуска пользователем)
────────────────────────────────────────────────────────
Новые файлы backend: models/dialog_state.py, models/analysis.py, services/llm_port.py,
services/topics_map.py, services/turn_analyzer.py, services/relevance_gate.py,
services/policy.py, services/session_store.py, services/social_branch.py,
eval/score_probe.py, Makefile: цель `probe`.
Изменены: models/grounding.py (+SOCIAL), schemas/chat.py (session_id, история 30),
core/config.py (SESSION_*), services/{answer_generator,chat_service,chat_presenter,
intent_detector}.py, src/main.py (DI), .env/.env.example/.env.prod/backend/.env.example,
FE: features/chat/{session.ts,types.ts,index.ts}, pages/ChatPage.tsx, tests/unit/*.
Удалены: profile_memory.py, dialog_strategy.py, query_condenser.py, conversation_memory.py
и их unit-тесты.
Старая цепочка docs/chains/improve_answer_quality.md ❌ ОТМЕНЕНА: хардкод-план (regex,
словари слов) и выдумка «добавить в документ порог 500 000 ₽».

────────────────────────────────────────────────────────
ИТЕРАЦИЯ 2 · ДИАЛОГ КАК В ЭТАЛОНЕ, ФАКТЫ ТОЛЬКО ИЗ КЦ.docx (S17–S22)
────────────────────────────────────────────────────────
ИСТОЧНИК ПРАВДЫ: backend/data/КЦ.docx. Эталонный чат — только поведение:
признать слова клиента → факт из корпуса → один вопрос → шаг к юристу.
Название компании и любые факты эталона в чат не переносим.

ДИАГНОЗ (по коду и по диалогу; подтверждение — VERIFY):
1. topics_map: _CORPUS_TEXT_LIMIT=15000 меньше длины корпуса → хвост КЦ.docx с критериями
   (сумма долга от 350к, регион прописки) не попадает в темы → missing берётся из списка
   «на что смотрит юрист» (долги и перед кем, сделки, доход) → вопросы не по сценарию.
2. answer_generator: правило 4 «контекст пуст → NO_ANSWER» действует и для handoff/decline/
   rephrase (контекст у них пуст по построению) → «Такого нет в нашей базе» на «давайте консультацию».
3. policy: handoff сразу на «юрист нужен» просит телефон до критериев; по КЦ: сначала
   сумма долга и регион, потом время консультации.
4. Служебные слова («контекст», «база») попадают в речь клиенту.

ЦЕПОЧКА (изменённые узлы):
08 🧭 TopicsMap.of(corpus) ─► Topics(lines, qualify)        [LLM, старт, кэш по хешу]
    ├─ темы: весь корпус батчами (не обрезка 15К)
    └─ qualify: ключевые критерии квалификации из корпуса, по порядку (D2: в коде их нет)
09 🧭 TurnAnalyzer.analyze(q, turns, state, topics) ─► Analysis
    └─ missing ⊆ qualify и ещё не в facts; пусто, когда все собраны
13 🧭 Policy.decide(Analysis, DialogState)
    ├─ wants_consultation и критерии не собраны ─► ask_one
    ├─ wants_consultation и критерии собраны ─► handoff (согласовать время)
    └─ иначе по прежним правилам (clarify / off_kb / ask_one / answer)
14 🧭 AnswerGenerator.generate ─► NO_ANSWER допустим только для answer / ask_one
    └─ речь клиенту без слов «контекст / база / документ»
16 🎁 NO_MATCH_REPLY без «в нашей базе»

ШАГИ (1 шаг = 1 файл = 1 правка):
✅ S17 topics_map.py: весь корпус батчами + Topics.qualify; имя компании убрать из TOPICS_SYSTEM
✅ S18 turn_analyzer.py: missing только из qualify, которых ещё нет в facts
✅ S19 policy.py: wants_consultation + критерии не собраны → ask_one; handoff только после сбора
✅ S20 answer_generator.py: NO_ANSWER только для answer/ask_one; запрет служебных слов; порядок A7
✅ S20b answer_generator.py: пустой контекст → NO_ANSWER только для answer; ask_one без контекста всё равно задаёт вопрос критерия
✅ S21 chat_service.py: NO_MATCH_REPLY без «в нашей базе»; asked помечается после поиска и только если вопрос реально задаётся; низкий скор не превращает ask_one в decline
🚧 S22 тесты на диалог пользователя (test_dialog_scenarios, test_topics_map, test_relevance_policy)
⚠️ S23 VERIFY (запускает пользователь): cd backend && make check → exit 0; ручной прогон диалога

────────────────────────────────────────────────────────
ИТЕРАЦИЯ 3 · ЦЕЛЬ ДИАЛОГА: УСЛОВИЯ ПРИЁМА → ВЕРДИКТ → КОНСУЛЬТАЦИЯ (S24–S33)
────────────────────────────────────────────────────────
ИСТОЧНИК ПРАВДЫ: КЦ.docx (раздел «Главная задача»: сумма долга от порога и регион прописки без
исключений, затем время консультации). Эталонный чат — только поведение: признать → разъяснить
по корпусу → один вопрос к цели; клиента от цели не отпускать.

ДИАГНОЗ (по коду и диалогу; подтверждение — VERIFY):
1. Условия приёма (порог, исключённые регионы) знала только модель → путала регионы.
2. A5 «не повторять вопрос» уводил от цели: после «давай стоимость» вопрос про сумму пропадал.
3. ANSWER сам звал на звонок при неизвестной сумме; правило «подвести к консультации» без условия.
4. В речь клиенту попадали служебные слова; ответы слишком короткие, без разъяснений.
5. «спасибо/пока» стирали факты сессии (commit с пустым DialogState).

ЦЕПОЧКА (изменённые и новые узлы):
08 🧭 TopicsMap.of(corpus) ─► Topics(lines, qualify: Criterion[])   [LLM при первом обращении, кэш]
    └─ Criterion: min_amount(min_rub) | excluded_values(excluded) — из корпуса, не из кода
09 🧭 TurnAnalyzer.analyze ─► Analysis; facts под метками критериев; сумма цифрами; город → регион
21 🧭 Qualification.evaluate(criteria, facts) ─► Verdict (pass/fail/unknown по каждому условию)
    └─ нераспознанный формат = unknown (спрашиваем), не отказ
13 🧭 Policy.decide(Analysis, Verdict)
    ├─ clarify ─► rephrase;  off_kb ─► decline (+ возврат к цели)
    ├─ fail ─► disqualify (вежливо, не окончательно);  pass все ─► handoff
    └─ unknown ─► ask_one по первому неизвестному условию КАЖДЫЙ ход (перефразируя)
14 🧭 AnswerGenerator ─► блок «Проверка условий» (факт от кода) + перечень исключений; 3–6 предложений
17 🎛️ ChatService: вердикт в логе; сессия не стирается соц-репликами; прогрев на старте (main)

ШАГИ:
🚧 S24 chat_v2.md: блок ИТЕРАЦИЯ 3
🚧 S25 models/criteria.py (НОВЫЙ): Criterion, Verdict, Status, Overall
🚧 S26 services/qualification.py (НОВЫЙ): evaluate, describe, parse_amount, same_label
🚧 S27 topics_map.py: структурное извлечение условий; кэши с повтором при пустом результате
🚧 S28 turn_analyzer.py: блок критериев с форматом значений; ключи фактов = метки; str-факты
🚧 S29 policy.py: решения по вердикту; новое действие DISQUALIFY
🚧 S30 answer_generator.py: правила цели и разъяснений; блок проверки условий; хвост реплики
🚧 S31 chat_service.py: вердикт, логирование, поиск для handoff/disqualify, сессия при соц-репликах
🚧 S32 main.py + ChatService.warm_up: прогрев и лог условий на старте
🚧 S33 config.py + .env*: MAX_TOKENS 500 → 800
⏸ S22b–g тесты: не делаются по решению пользователя; старые тесты устарели

────────────────────────────────────────────────────────
ИТЕРАЦИЯ 4 · СОЦ-ВЕТКА: ШИРОКИЙ СЛОВАРЬ, СТРОГОЕ СОВПАДЕНИЕ (S34–S36)
────────────────────────────────────────────────────────
РЕШЕНИЕ (уточняет D1): соц-реплики остаются хардкодом, но:
* словарь приветствий/спасибо/прощания РАСШИРЕН до реальных вариантов письма
  (привет/прив/пр, здравствуй/здрасьте/здр/зд/з, здоров/здорова, хай/hi/hello/ку/йо, алло/ау,
  «добрый день», «доброго времени суток», «здравия желаю», «всем привет» и т.д.);
* сравнение — ТОЛЬКО полное совпадение всей нормализованной реплики (регистр, ё→е,
  пунктуация → пробел, ведущие филлеры «ну/и/а/э/ой/снова/опять/еще» снимаются);
* эвристика «короткая реплика ≤3 токенов с совпавшим словом» УДАЛЕНА — именно она давала
  «пока не знаю» → «До свидания!»;
* «доброй ночи» отнесено к прощанию (не к приветствию);
* «здорово» ловится только как отдельная реплика целиком («здорово получилось…» → деловая ветка).

✅ S34 src/services/intent_detector.py: GREETING_TOKENS/GREETING_PHRASES (широкие),
        THANKS_TOKENS/THANKS_PHRASES, BYE_TOKENS (расширены), normalize() + LEADING_FILLERS,
        detect() = три точных сравнения (BYE → THANKS → GREETING), QUESTION иначе;
        already_greeted() по словам без пунктуации. Подстроги и «≤3 токенов» удалены.
✅ S35 tests/unit/test_intent_detector.py: параметризованные наборы ALL_GREETINGS (43 варианта),
        NOT_GREETINGS (полное совпадение обязательно: «здравствуйте, хочу списать долги»,
        «пр 500000», «куда обратиться по долгам»), BYE-варианты и антикейсы
        («пока не знаю», «пока думаю»), THANKS-варианты.
⚠️ S36 VERIFY (запускает пользователь): cd backend && make check → exit 0

Не менялось: SocialBranch (строки A3), ChatService (порядок узлов), ответы на привет/спасибо/пока.
