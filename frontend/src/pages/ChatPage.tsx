import { useRef, useState, useEffect, useLayoutEffect } from "react";
import { useChat, type ChatResponse } from "@/features/chat";
import { UIInput } from "@/shared/ui";
import { ChatMessageList } from "@/components/ChatMessageList";

// interface Message {
//   id: string;
//   role: "user" | "assistant";
//   text: string;
//   response?: ChatResponse;
// }

let seq = 0;
const nextId = () => `m${++seq}`;

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: ChatResponse;
}

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

  // Возврат фокуса в инпут (синхронно, после каждого рендера)
  useLayoutEffect(() => {
    if (document.activeElement !== inputRef.current) {
      inputRef.current?.focus();
    }
  });

  async function send(): Promise<void> {
    const q = draft.trim();
    if (!q || isPending) return;
    setDraft("");
    inputRef.current?.focus();
    setMessages((prev) => [...prev, { id: nextId(), role: "user", text: q }]);
    try {
      const history = messages.slice(-10).map((m) => ({ role: m.role, content: m.text }));
      console.log("DEBUG history:", history);
      const response = await mutateAsync({ question: q, history });
      setMessages((prev) => [...prev, { id: nextId(), role: "assistant", text: response.answer, response }]);
    } catch {
      setMessages((prev) => [...prev, { id: nextId(), role: "assistant", text: "Ошибка сети. Попробуйте еще раз." }]);
    } finally {
      // фокус вернется через useEffect
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
          <ChatMessageList 
            messages={messages.map(m => ({
              id: m.id,
              role: m.role,
              text: m.text,
              response: m.response
            }))}
            pending={isPending}
          />
          <div ref={messagesEndRef} />
        </div>

        {/* Поле ввода */}
        <div className="border-t border-slate-800 bg-slate-900 p-4">
          <div className="mx-auto max-w-3xl relative">
            <UIInput
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (draft.trim() && !isPending) void send(); } }}
              placeholder="Задайте вопрос..."
              className="w-full pr-16"
            />
            <div
              role="button"
              tabIndex={-1}
              onClick={() => { if (draft.trim() && !isPending) void send(); }}
              className={"absolute right-2 top-2 rounded-lg bg-blue-600 p-2 text-white transition-colors hover:bg-blue-500 " + ((!draft.trim() || isPending) ? "opacity-50 cursor-not-allowed" : "cursor-pointer")}
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5">
                <path d="M3.478 2.404a.75.75 0 00-.926.941l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.404z" />
              </svg>
            </div>
          </div>
          {error && <p className="mt-2 text-center text-xs text-rose-500">{error.message}</p>}
          <p className="mt-3 text-center text-xs text-slate-500">RAG Chat может ошибаться. Проверяйте важную информацию.</p>
        </div>
      </main>
    </div>
  );
}
