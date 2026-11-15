════ CHAT · RAG ПО ДОКУМЕНТУ ════

[FE] 01 🧩 IA·component  <ChatPage/>.onSubmit(question)               ─► useChat
[FE] 02 🧩 IA·hook       useChat().mutateAsync(ChatRequest)          ─► ChatApi.post
[FE] 03 📡 IA·http       ChatApi.post(ChatRequest)                   ─► HttpClient.send
[FE] 04 🚦 IA·interceptor CsrfInterceptor.request / UnauthorizedInterceptor.response
[FE] 05 🧩 IA·component  <ChatMessageList/>.render(ChatResponse)     ─► zod parse → UI

[BE] 06 🎛️ FD·router     ChatRouter.chat(ChatRequest)                 ─► ChatService.ask
                          └─x─► 🚨 422 [schema]
[BE] 07 🧭 APP·service   ChatService.ask(q, history)
   ├─► 08 🧭 APP·service    QueryCondenser.standalone(q, history)     ─► question
