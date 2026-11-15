import { useRef, useState } from "react";
import { useChat, type ChatResponse } from "@/features/chat";
import { ChatMessageList, type ChatMessage } from "@/components/ChatMessageList";
import { UIButton, UIInput } from "@/shared/ui";

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

  async function send(): Promise<void> {
    const q = draft.trim();
    if (q.length === 0) {
      return;
    }
    setDraft("");
    const userMsg: ChatMessage = { id: nextId(), role: "user", text: q };
    setMessages((prev) => [...prev, userMsg]);
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
    <section style={{ maxWidth: 720, margin: "24px auto", padding: 16 }}>
      <h1 style={{ marginTop: 0 }}>RAG Chat · документ «КЦ»</h1>
      <ChatMessageList messages={messages} />
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
        style={{ display: "flex", gap: 8, marginTop: 16 }}
      >
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
      </form>
      {error && <p style={{ color: "#b91c1c" }}>Ошибка: {error.message}</p>}
    </section>
  );
}
