import { useRef, useState } from "react";
import { useChat, type ChatResponse } from "@/features/chat";
import { ChatMessageList, type ChatMessage } from "@/components/ChatMessageList";
import { UIButton, UIInput } from "@/shared/ui";
import { useTheme } from "@/app/theme";

let seq = 0;
function nextId(): string {
  seq += 1;
  return `m${String(seq)}`;
}

export function ChatPage(): JSX.Element {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const { mutateAsync, isPending, error } = useChat();
  const { theme, toggle } = useTheme();

  async function send(): Promise<void> {
    const q = draft.trim();
    if (q.length === 0) return;
    setDraft("");
    setMessages((prev) => [...prev, { id: nextId(), role: "user", text: q }]);
    try {
      const response: ChatResponse = await mutateAsync({ question: q });
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "assistant", text: response.answer, response },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "assistant", text: "Ошибка запроса." },
      ]);
    } finally {
      inputRef.current?.focus();
    }
  }

  return (
    <div className="flex h-screen flex-col bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <header className="border-b border-slate-200 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-900/80">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-white">
              💬
            </div>
            <div>
              <h1 className="text-sm font-semibold">RAG Chat</h1>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Ответы строго по документу
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={toggle}
            aria-label="Переключить тему"
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
          >
            {theme === "dark" ? "☀️" : "🌙"}
          </button>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto px-4 py-6">
          <ChatMessageList messages={messages} pending={isPending} />
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
          className="border-t border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
        >
          <div className="mx-auto flex max-w-3xl gap-2">
            <UIInput
              ref={inputRef}
              value={draft}
              onChange={(e) => { setDraft(e.target.value); }}
              placeholder="Спросите по документу…"
              disabled={isPending}
            />
            <UIButton type="submit" disabled={isPending || draft.trim().length === 0}>
              {isPending ? "…" : "Отправить"}
            </UIButton>
          </div>
          {error && (
            <p className="mx-auto mt-2 max-w-3xl text-xs text-rose-600 dark:text-rose-400">
              Ошибка: {error.message}
            </p>
          )}
        </form>
      </main>
    </div>
  );
}
