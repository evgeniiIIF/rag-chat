/* eslint-disable react-refresh/only-export-components -- разметка ответа, а не компонент */
import type { ReactNode } from "react";

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
const BOLD = /^\*\*[^*]+\*\*$/;

// то, что клиент должен увидеть сразу: суммы, телефон и время звонка
const DETAIL = new RegExp(
  [
    "\\b\\d[\\d\\s\\u00a0]*(?:₽|руб\\w*|тыс\\w*|млн\\w*|миллион\\w*)",
    "\\+?\\d[\\d\\s\\u00a0()\\-]{8,}\\d",
    "\\b\\d{1,2}[:.]\\d{2}\\b",
  ].join("|"),
  "g",
);

/** Суммы, телефон и время выделяем, если бэкенд уже не расставил **…**. */
export function highlightDetails(text: string): string {
  if (text.includes("**")) return text; // разметку бэкенда не ломаем
  return text.replace(DETAIL, (match) => `**${match}**`);
}

export function renderInline(text: string): ReactNode[] {
  return highlightDetails(text)
    .split(/(\*\*[^*]+\*\*)/g)
    .map((part, index) => {
      const bold = BOLD.test(part);
      const value = bold ? part.slice(2, -2) : part;
      return bold ? (
        <strong key={index} className="font-semibold text-accent dark:text-accent">
          {value}
        </strong>
      ) : (
        <span key={index}>{value}</span>
      );
    });
}

export type RenderBlock = MessageBlock | { kind: "q"; text: string };

const QUESTION_END = /\?\**$/;

/** Последний абзац-вопрос ассистента выделяем отдельной плашкой (вопрос фильтра, приглашение). */
export function markQuestion(blocks: MessageBlock[]): RenderBlock[] {
  const last = blocks[blocks.length - 1];
  if (last?.kind === "p" && QUESTION_END.test(last.text.trim())) {
    return [...blocks.slice(0, -1), { kind: "q", text: last.text }];
  }
  return blocks;
}
