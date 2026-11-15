import type { ChatResponse } from "@/features/chat";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: ChatResponse;
}

export interface ChatMessageListProps {
  messages: ChatMessage[];
}

export function ChatMessageList({ messages }: ChatMessageListProps): JSX.Element {
  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12 }}>
      {messages.map((m) => (
        <li
          key={m.id}
          style={{
            padding: 12,
            borderRadius: 10,
            background: m.role === "user" ? "#eef2ff" : "#f8fafc",
            border: "1px solid #e2e8f0",
          }}
        >
          <strong>{m.role === "user" ? "Вы" : "Ассистент"}:</strong> {m.text}
          {m.response && !m.response.grounded && (
            <div style={{ color: "#b45309", marginTop: 6 }}>
              Ответа в документе не найдено.
            </div>
          )}
          {m.response && m.response.sources.length > 0 && (
            <ul style={{ marginTop: 8, color: "#475569", fontSize: 13 }}>
              {m.response.sources.map((s, i) => (
                <li key={`${s.source}-${String(s.paragraph_start)}-${String(i)}`}>
                  {s.source} · абзац {String(s.paragraph_start)}
                  {s.paragraph_end !== s.paragraph_start ? `–${String(s.paragraph_end)}` : ""}
                  : «{s.snippet}»
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  );
}
