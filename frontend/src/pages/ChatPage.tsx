import { useRef, useState, useEffect, useLayoutEffect } from "react";
import { useChat, getSessionId, type ChatResponse } from "@/features/chat";
import { UIInput } from "@/shared/ui";
import { ChatMessageList } from "@/components/ChatMessageList";

let seq = 0;
const nextId = (): string => `m${String(++seq)}`;

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
  const scrollRef = useRef<HTMLDivElement>(null);
  const { mutateAsync, isPending, error } = useChat();

  useEffect(() => {
    const el = scrollRef.current;
    if (el !== null) el.scrollTop = el.scrollHeight;
  }, [messages, isPending]);

  useLayoutEffect(() => {
    const el = inputRef.current;
    if (el !== null && document.activeElement !== el) {
      el.focus({ preventScroll: true });
    }
  });

  async function send(): Promise<void> {
    const q = draft.trim();
    if (!q || isPending) return;
    setDraft("");
    inputRef.current?.focus({ preventScroll: true });
    setMessages((prev) => [...prev, { id: nextId(), role: "user", text: q }]);
    try {
      const history = messages.slice(-30).map((m) => ({ role: m.role, content: m.text }));
      const response = await mutateAsync({ question: q, history, session_id: getSessionId() });
      setMessages((prev) => [...prev, { id: nextId(), role: "assistant", text: response.answer, response }]);
    } catch {
      setMessages((prev) => [...prev, { id: nextId(), role: "assistant", text: "Ошибка сети. Попробуйте еще раз." }]);
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header flex h-16 shrink-0 items-center justify-between border-b border-slate-800 bg-slate-900/80 px-4 backdrop-blur-md sm:h-auto sm:px-6 sm:py-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 shadow-md shadow-blue-500/20">
            <span className="text-lg leading-none">✨</span>
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold tracking-tight text-white sm:text-lg">RAG Assistant</h1>
            <p className="hidden text-xs text-slate-400 sm:block">Ответы по вашему документу v2</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
          </span>
        </div>
      </header>

      <main className="app-main w-full">
        <div ref={scrollRef} className="app-main__scroll scrollbar-chat w-full px-4 py-5 sm:px-4 sm:py-6">
          <div className="mx-auto flex h-full w-full max-w-4xl flex-col">
            <ChatMessageList
              messages={messages.map((m) => ({ id: m.id, role: m.role, text: m.text, response: m.response }))}
              pending={isPending}
            />
          </div>
        </div>
      </main>

      <footer className="app-footer border-t border-slate-800 bg-slate-900 px-4 py-3 sm:px-4 sm:py-4">
        <div className="relative mx-auto max-w-3xl">
          <UIInput
            ref={inputRef}
            value={draft}
            onChange={(e) => { setDraft(e.target.value); }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (draft.trim() && !isPending) void send();
              }
            }}
            placeholder="Задайте вопрос..."
            className="pr-16 sm:pr-16"
          />
          <div
            role="button"
            tabIndex={-1}
            onClick={() => { if (draft.trim() && !isPending) void send(); }}
            className={
              "absolute right-2 top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-lg bg-blue-600 text-white transition-colors hover:bg-blue-500 sm:h-10 sm:w-10 " +
              ((!draft.trim() || isPending) ? "opacity-50 cursor-not-allowed" : "cursor-pointer")
            }
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="h-6 w-6 sm:h-5 sm:w-5">
              <path d="M3.478 2.404a.75.75 0 00-.926.941l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.404z" />
            </svg>
          </div>
        </div>
      </footer>
    </div>
  );
}
