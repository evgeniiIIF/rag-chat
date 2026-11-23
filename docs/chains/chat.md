🎛 ════ · 16:27:31 · 839 файлов · 0 символов · ✓

⚠️ ЦЕПОЧКА ЗАМЕНЕНА: действия v1 (FSM/regex/condenser) противоречат D2/D3.
   Активная цепочка — docs/chains/chat_v2.md (A1–A7, D1–D6). Здесь только история.


[FE] 01 🧩 IA·component  <ChatPage/>.onSubmit(question)               ─► useChat
[FE] 02 🧩 IA·hook       useChat().mutateAsync(ChatRequest)          ─► ChatApi.post
[FE] 03 📡 IA·http       ChatApi.post(ChatRequest)                   ─► HttpClient.send
[FE] 04 🚦 IA·interceptor CsrfInterceptor.request / UnauthorizedInterceptor.response
[FE] 05 🧩 IA·component  <ChatMessageList/>.render(ChatResponse)     ─► zod parse → UI

[BE] 06 🎛️ FD·router     ChatRouter.chat(ChatRequest)                 ─► ChatService.ask
                          └─x─► 🚨 422 [schema]
07 🧭 APP·service   ChatService.ask(request)
   ├─► 08 🛡️ APP·guard     InputGuardrail.check(q)                   ─► bool
   │        └─x─► false ─► 18 🎁 present(«Я ассистент…», NOT_ANSWERABLE)
   ├─► 09 🔎 APP·intent    IntentDetector.detect(q)                  ─► Intent
   │        ├─► GREETING/THANKS/BYE ─► 10 🧭 APP·small_talk ChatService._small_talk_answer(q, history)
   │        │        ├─► 09a 🔎 APP·intent IntentDetector.already_greeted(history) ─► bool (нормализация пунктуации)
   │        │        └─► 18 🎁 present(text, GROUNDED)
   │        └─► QUESTION ─► дальше
   ├─► 11 🗄️ APP·memory    ConversationMemory.get_processed_history(history) ─► (summary, recent)
   ├─► 12 🗄️ APP·profile   ProfileMemory.extract(q, history)         ─► Profile
   ├─► 13 🧭 APP·strategy  DialogStrategy.decide(q, profile, intent) ─► StrategyHint(stage, goal, missing, suggested_question)
   ├─► 14 🧭 APP·condenser QueryCondenser.standalone(q, recent)      ─► standalone
   ├─► 15 🗄️ APP·retriever HybridRetriever.search(standalone, k)     ─► hits
   ├─► 16 🧭 APP·generate  AnswerGenerator.generate(q, context, recent, summary, hint, profile) ─► answer|NO_ANSWER
   ├─► 17 🚦 APP·gate      AnswerGate.gate(hits, answer, settings)   ─► Grounding
   └─► 18 🎁 APP·presenter ChatPresenter.present(answer, grounding, hits, expanded) ─► ChatResponse
19 📤 FD·response        HTTP 200 ChatResponse

──── VERIFY ────
20 ✅ make check в backend → ruff + ruff format + mypy strict + pytest + audit → exit 0 (55 passed)
