import type { ChatResponse } from "@/features/chat";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: ChatResponse;
}

export interface ChatMessageListProps {
  messages: ChatMessage[];
  pending?: boolean;
}

export function ChatMessageList({ messages, pending }: ChatMessageListProps): JSX.Element {
  if (messages.length === 0 && !pending) {
    return (
      <div className="flex h-full min-h-[40vh] flex-col items-center justify-center text-center text-slate-500 dark:text-slate-400">
        <div className="mb-2 text-4xl">💬</div>
        <p className="text-sm">Задайте вопрос по документу «КЦ».</p>
        <p className="text-xs">Например: «Что с детьми при банкротстве?»</p>
      </div>
    );
  }
  return (
    <ul className="flex flex-col gap-4">
      {messages.map((m) => (
        <li
          key={m.id}
          className={m.role === "user" ? "flex justify-end" : "flex justify-start"}
        >
          <div
            className={[
              "flex max-w-[85%] items-start gap-3 rounded-2xl px-4 py-3 text-sm shadow-sm",
              m.role === "user"
                ? "bg-accent text-white"
                : "bg-white text-slate-800 dark:bg-slate-900 dark:text-slate-100",
            ].join(" ")}
          >
            <div
              className={[
                "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold",
                m.role === "user" ? "bg-white/20 text-white" : "bg-accent/10 text-accent",
              ].join(" ")}
            >
              {m.role === "user" ? "Я" : "AI"}
            </div>
            <div className="min-w-0">
              <div className="whitespace-pre-wrap break-words">{m.text}</div>
              {m.response && !m.response.grounded && (
                <div className="mt-2 text-xs text-amber-600 dark:text-amber-400">
                  Ответа в документе не найдено.
                </div>
              )}

            </div>
          </div>
        </li>
      ))}
      {pending && (
        <li className="flex justify-start">
          <div className="flex items-center gap-2 rounded-2xl bg-white px-4 py-3 text-sm text-slate-500 shadow-sm dark:bg-slate-900 dark:text-slate-400">
            <span className="flex gap-1">
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent [animation-delay:-0.3s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent [animation-delay:-0.15s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent" />
            </span>
            печатает…
          </div>
        </li>
      )}
    </ul>
  );
}
