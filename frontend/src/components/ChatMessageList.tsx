import type { ReactNode } from "react";
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

export type MessageBlock = { kind: "p"; text: string } | { kind: "ul"; items: string[] };

const BULLET = /^[-•*]\s+/;

/** Простая разметка ответа: абзацы, списки «- » и **жирный** внутри строки. */
export function parseBlocks(text: string): MessageBlock[] {
  const blocks: MessageBlock[] = [];
  for (const raw of text.trim().split(/\n{2,}/)) {
    let paragraph: string[] = [];
    let items: string[] = [];
    const flushParagraph = (): void => {
      if (paragraph.length > 0) blocks.push({ kind: "p", text: paragraph.join(" ") });
      paragraph = [];
    };
    const flushItems = (): void => {
      if (items.length > 0) blocks.push({ kind: "ul", items });
      items = [];
    };
    for (const line of raw.split("\n").map((value) => value.trim()).filter(Boolean)) {
      if (BULLET.test(line)) {
        flushParagraph();
        items.push(line.replace(BULLET, ""));
      } else {
        flushItems();
        paragraph.push(line);
      }
    }
    flushParagraph();
    flushItems();
  }
  return blocks;
}

/** **жирный** внутри строки -> <strong>, остальное как есть. */
export function renderInline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    const bold = /^\*\*[^*]+\*\*$/.test(part);
    const value = bold ? part.slice(2, -2) : part;
    return bold ? (
      <strong key={index} className="font-semibold text-slate-900 dark:text-white">
        {value}
      </strong>
    ) : (
      <span key={index}>{value}</span>
    );
  });
}

type RenderBlock = MessageBlock | { kind: "q"; text: string };

const QUESTION_END = /\?\**$/;

/** Последний абзац-вопрос ассистента выделяем отдельной плашкой (вопрос фильтра, приглашение). */
export function markQuestion(blocks: MessageBlock[]): RenderBlock[] {
  const last = blocks[blocks.length - 1];
  if (blocks.length > 1 && last?.kind === "p" && QUESTION_END.test(last.text.trim())) {
    return [...blocks.slice(0, -1), { kind: "q", text: last.text }];
  }
  return blocks;
}

function MessageText({ text, role }: { text: string; role: "user" | "assistant" }): JSX.Element {
  const parsed = parseBlocks(text);
  const blocks: RenderBlock[] = role === "assistant" ? markQuestion(parsed) : parsed;
  if (blocks.length <= 1 && !text.includes("- ")) {
    return <p className="whitespace-pre-wrap break-words">{renderInline(text)}</p>;
  }
  return (
    <div className="space-y-3">
      {blocks.map((block, index) => {
        if (block.kind === "ul") {
          return (
            <ul key={index} className="space-y-1.5">
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex} className="flex gap-2">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                  <span className="min-w-0 break-words">{renderInline(item)}</span>
                </li>
              ))}
            </ul>
          );
        }
        if (block.kind === "q") {
          return (
            <p
              key={index}
              className="whitespace-pre-wrap break-words rounded-xl border-l-4 border-accent bg-accent/5 px-3 py-2 font-medium text-slate-900 dark:text-white"
            >
              {renderInline(block.text)}
            </p>
          );
        }
        return (
          <p key={index} className="whitespace-pre-wrap break-words">
            {renderInline(block.text)}
          </p>
        );
      })}
    </div>
  );
}

export function ChatMessageList({ messages, pending }: ChatMessageListProps): JSX.Element {
  if (messages.length === 0 && !pending) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-center text-slate-500 dark:text-slate-400">
        <div className="mb-2 text-4xl">💬</div>
        <p className="text-sm">Задайте вопрос.</p>
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
              "flex max-w-[92%] items-start gap-2 rounded-2xl px-3 py-2 text-sm shadow-sm sm:max-w-[85%] sm:gap-3 sm:px-4 sm:py-3",
              m.role === "user"
                ? "bg-accent text-white"
                : "border border-slate-200 bg-white text-slate-800 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100",
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
              <div className="leading-relaxed">
                <MessageText text={m.text} role={m.role} />
              </div>
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
