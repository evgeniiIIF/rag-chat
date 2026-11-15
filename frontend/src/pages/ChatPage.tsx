import { useRef, useState, useEffect } from "react";
import { useChat, type ChatResponse } from "@/features/chat";
import { UIButton, UIInput } from "@/shared/ui";

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: ChatResponse;
}

let seq = 0;
const nextId = () => `m${++seq}`;

export function ChatPage(): JSX.Element {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { mutateAsync, isPending, error } = useChat();

  // Автоскролл вниз при новом сообщении
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isPending]);

  async function send(): Promise<void> {
    const q = draft.trim();
    if (!q) return;
    setDraft("");
    setMessages((prev) => [...prev, { id: nextId(), role: "user", text: q }]);
    try {
      const response = await mutateAsync({ question: q });
      setMessages((prev) => [...prev, { id: nextId(), role: "assistant", text: response.answer, response }]);
    } catch {
      setMessages((prev) => [...prev, { id: nextId(), role: "assistant", text: "Ошибка сети. Попробуйте еще раз." }]);
    } finally {
      inputRef.current?.focus();
    }
  }

  return (
    <div className="flex h-[100dvh] w-full flex-col bg-slate-900 text-slate-100 font-sans">
      {/* Шапка */}
      <header className="flex items-center justify-between border-b border-slate-800 bg-slate-900/50 px-6 py-4 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 shadow-lg shadow-blue-500/20">
            <span className="text-xl">✨</span>
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-white">RAG Assistant</h1>
            <p className="text-xs text-slate-400">Умные ответы по вашему документу</p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
          </span>
          Онлайн
        </div>
      </header>

      {/* Лента сообщений */}
      <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col overflow-hidden min-h-0">
        <div className="flex-1 overflow-y-auto px-4 py-6 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent">
          {messages.length === 0 && !isPending && (
            <div className="flex h-full flex-col items-center justify-center text-center animate-fade-in">
              <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-3xl bg-slate-800 shadow-xl">
                <span className="text-4xl text-blue-400">💬</span>
              </div>
              <h2 className="mb-2 text-2xl font-semibold text-white">Чем я могу помочь?</h2>
              <p className="text-sm text-slate-400">Задайте вопрос по документу «КЦ».</p>

            </div>
          )}

          <div className="flex flex-col gap-6">
            {messages.map((m) => (
              <div key={m.id} className={`flex gap-4 animate-slide-up ${m.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
                <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg shadow-sm ${
                  m.role === "user" ? "bg-blue-600 text-white" : "bg-slate-800 text-blue-400 border border-slate-700"
                }`}>
                  {m.role === "user" ? "👤" : "🤖"}
                </div>
                <div className={`flex max-w-[80%] flex-col ${m.role === "user" ? "items-end" : "items-start"}`}>
                  <div className={`rounded-2xl px-5 py-3 text-sm leading-relaxed shadow-sm ${
                    m.role === "user" 
                      ? "bg-blue-600 text-white rounded-tr-sm" 
                      : "bg-slate-800 text-slate-200 border border-slate-700 rounded-tl-sm"
                  }`}>
                    <div className="whitespace-pre-wrap">{m.text}</div>
                  </div>
                  

                  {m.response && !m.response.grounded && (
                    <span className="mt-2 text-xs text-amber-500 bg-amber-500/10 px-2 py-1 rounded">Нет ответа в документе</span>
                  )}
                </div>
              </div>
            ))}
            
            {isPending && (
              <div className="flex gap-4 animate-fade-in">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-800 text-blue-400 border border-slate-700">🤖</div>
                <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-sm bg-slate-800 border border-slate-700 px-5 py-4">
                  <div className="h-2 w-2 animate-bounce rounded-full bg-blue-500 [animation-delay:-0.3s]"></div>
                  <div className="h-2 w-2 animate-bounce rounded-full bg-blue-500 [animation-delay:-0.15s]"></div>
                  <div className="h-2 w-2 animate-bounce rounded-full bg-blue-500"></div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Поле ввода */}
        <div className="border-t border-slate-800 bg-slate-900 p-4">
          <form onSubmit={(e) => { e.preventDefault(); void send(); }} className="mx-auto max-w-3xl relative">
            <UIInput
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Задайте вопрос..."
              disabled={isPending}
              className="w-full pr-16"
            />
            <button
              type="submit"
              disabled={isPending || !draft.trim()}
              className="absolute right-2 top-2 rounded-lg bg-blue-600 p-2 text-white transition-colors hover:bg-blue-500 disabled:opacity-50 disabled:hover:bg-blue-600"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5">
                <path d="M3.478 2.404a.75.75 0 00-.926.941l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.404z" />
              </svg>
            </button>
          </form>
          {error && <p className="mt-2 text-center text-xs text-rose-500">{error.message}</p>}
          <p className="mt-3 text-center text-xs text-slate-500">RAG Chat может ошибаться. Проверяйте важную информацию.</p>
        </div>
      </main>
    </div>
  );
}
