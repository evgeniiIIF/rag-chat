import type { ChatBlock, ChatResponse } from "@/features/chat";

import { markQuestion, parseBlocks, renderInline } from "./messageFormat";
import type { RenderBlock } from "./messageFormat";

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

interface MessageTextProps {
  text: string;
  role: "user" | "assistant";
  question?: string;
  blocks?: ChatBlock[];
  known?: string[];
  booking?: ChatResponse["booking"];
}

// единая типографика ответа: подпись раздела, основной текст, тонкая линия-акцент
// чат живёт на тёмном каркасе (app-shell #0f172a): светлый текст и полупрозрачные плашки
const LABEL = "text-[10px] font-semibold tracking-[0.14em] text-slate-400 uppercase";
const BODY = "text-[15px] leading-7 break-words text-slate-100";
const CARD = "rounded-lg border border-slate-700/60 bg-slate-800/50";

function Bullet(): JSX.Element {
  return <span className="mt-[11px] h-1 w-1 shrink-0 rounded-full bg-slate-500" />;
}

function QuestionPlaque({ text }: { text: string }): JSX.Element {
  return (
    <div className="rounded-r-lg border-l-2 border-accent bg-accent/10 py-2 pr-3 pl-4">
      <p className={LABEL}>Вопрос</p>
      <p className="mt-1 text-[15px] leading-7 font-medium break-words text-white">
        {renderInline(text)}
      </p>
    </div>
  );
}

/** Пояснения списком: сдержанные маркеры, заголовок раздела мелким капсом. */
function ListPlaque({ title, items }: { title: string; items: string[] }): JSX.Element {
  return (
    <section className="space-y-2">
      {title !== "" && <p className={LABEL}>{title}</p>}
      <ul className="space-y-1.5">
        {items.map((item) => (
          <li key={item} className="flex gap-2.5">
            <Bullet />
            <span className={`min-w-0 ${BODY}`}>{renderInline(item)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Оговорка клиенту: не приговор, а уточнение. */
function NotePlaque({ text }: { text: string }): JSX.Element {
  return (
    <p className="border-l-2 border-amber-400/70 bg-amber-400/10 py-2 pr-3 pl-4 text-[13px] leading-6 break-words text-amber-50">
      {renderInline(text)}
    </p>
  );
}

/** Готовые блоки с бэкенда: каждый тип рисуем своей плашкой. */
function BlockList({ blocks }: { blocks: ChatBlock[] }): JSX.Element {
  return (
    <div className="space-y-3">
      {blocks.map((block, index) => {
        switch (block.type) {
          case "lead":
            return (
              <p key={index} className={BODY}>
                {renderInline(block.text)}
              </p>
            );
          case "list":
            return <ListPlaque key={index} title={block.title} items={block.items} />;
          case "note":
            return <NotePlaque key={index} text={block.text} />;
          case "question":
            return <QuestionPlaque key={index} text={block.text} />;
          default:
            return (
              <p key={index} className={`whitespace-pre-wrap ${BODY}`}>
                {renderInline(block.text)}
              </p>
            );
        }
      })}
    </div>
  );
}

function KnownFacts({ facts }: { facts: string[] }): JSX.Element {
  return (
    <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-[12px] text-slate-400">
      <span className={LABEL}>Уже известно</span>
      {facts.map((fact) => (
        <span key={fact} className="rounded bg-white/10 px-1.5 py-0.5 text-slate-200">
          {fact}
        </span>
      ))}
    </p>
  );
}

function BookingPlaque({ booking }: { booking: NonNullable<ChatResponse["booking"]> }): JSX.Element {
  return (
    <section className={`${CARD} px-4 py-3`}>
      <p className={LABEL}>Консультация</p>
      <dl className="mt-2 space-y-1.5">
        <div className="flex items-baseline justify-between gap-4">
          <dt className="text-[12px] text-slate-400">Телефон</dt>
          <dd className="text-[14px] font-semibold break-words text-white">
            {renderInline(booking.phone)}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-4">
          <dt className="text-[12px] text-slate-400">Время звонка</dt>
          <dd className="text-[14px] font-semibold break-words text-white">
            {renderInline(booking.date_time)}
          </dd>
        </div>
      </dl>
    </section>
  );
}

function MessageText({
  text,
  role,
  question = "",
  blocks: serverBlocks = [],
  known = [],
  booking = null,
}: MessageTextProps): JSX.Element {
  // бэкенд уже разложил ответ на блоки: вопрос внутри них, отдельной плашкой не дублируем
  const hasBlocks = role === "assistant" && serverBlocks.length > 0;
  const parsed = hasBlocks ? [] : parseBlocks(text);
  const blocks: RenderBlock[] = role === "assistant" ? markQuestion(parsed) : parsed;
  return (
    <div className="space-y-3">
      {hasBlocks ? <BlockList blocks={serverBlocks} /> : <MessageBody text={text} blocks={blocks} />}
      {!hasBlocks && question !== "" && <QuestionPlaque text={question} />}
      {booking?.is_confirmed === true && <BookingPlaque booking={booking} />}
      {known.length > 0 && <KnownFacts facts={known} />}
    </div>
  );
}

function MessageBody({ text, blocks }: { text: string; blocks: RenderBlock[] }): JSX.Element {
  if (blocks.length <= 1 && !text.includes("- ")) {
    return <p className={`whitespace-pre-wrap ${BODY}`}>{renderInline(text)}</p>;
  }
  return (
    <div className="space-y-3">
      {blocks.map((block, index) => {
        if (block.kind === "ul") {
          return (
            <ul key={index} className="space-y-1.5">
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex} className="flex gap-2.5">
                  <Bullet />
                  <span className={`min-w-0 ${BODY}`}>{renderInline(item)}</span>
                </li>
              ))}
            </ul>
          );
        }
        if (block.kind === "q") {
          return <QuestionPlaque key={index} text={block.text} />;
        }
        return (
          <p key={index} className={`whitespace-pre-wrap ${BODY}`}>
            {renderInline(block.text)}
          </p>
        );
      })}
    </div>
  );
}

export function ChatMessageList({ messages, pending }: ChatMessageListProps): JSX.Element {
  // «уже известно» показываем один раз — в последней реплике ассистента, а не в каждом пузыре
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant")?.id;
  if (messages.length === 0 && !pending) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-center">
        <p className="text-[15px] font-medium text-slate-200">Задайте вопрос</p>
        <p className="mt-1 text-[13px] text-slate-400">
          Подскажу по процедуре банкротства, условиям и порядку работы.
        </p>
      </div>
    );
  }
  return (
    <ul className="flex flex-col gap-5 [&>li:last-child]:pb-5">
      {messages.map((m) =>
        m.role === "user" ? (
          <li key={m.id} className="flex justify-end">
            <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-accent px-4 py-2.5 text-[15px] leading-7 break-words text-white shadow-sm">
              {m.text}
            </div>
          </li>
        ) : (
          <li key={m.id} className="flex justify-start">
            <div className="min-w-0 max-w-[92%] rounded-2xl rounded-bl-sm border border-slate-700/70 bg-slate-900/90 px-4 py-3 shadow-sm sm:max-w-[85%]">
              <MessageText
                text={m.text}
                role={m.role}
                question={m.response?.question ?? ""}
                blocks={m.response?.blocks ?? []}
                known={m.id === lastAssistant ? (m.response?.known ?? []) : []}
                booking={m.id === lastAssistant ? (m.response?.booking ?? null) : null}
              />
            </div>
          </li>
        ),
      )}
      {pending && (
        <li className="flex justify-start">
          <div className="flex items-center gap-2 py-1 pl-1 text-[13px] text-slate-400">
            <span className="flex gap-1">
              <span className="h-1 w-1 animate-bounce rounded-full bg-accent [animation-delay:-0.3s]" />
              <span className="h-1 w-1 animate-bounce rounded-full bg-accent [animation-delay:-0.15s]" />
              <span className="h-1 w-1 animate-bounce rounded-full bg-accent" />
            </span>
            печатает…
          </div>
        </li>
      )}
    </ul>
  );
}
