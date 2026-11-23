import { describe, expect, it } from "vitest";
import { highlightDetails, parseBlocks } from "@/components/messageFormat";
import { chatResponseSchema } from "@/features/chat";

describe("parseBlocks", () => {
  it("делит ответ на абзацы по пустой строке", () => {
    expect(parseBlocks("Первая мысль.\n\nВторая мысль.")).toEqual([
      { kind: "p", text: "Первая мысль." },
      { kind: "p", text: "Вторая мысль." },
    ]);
  });

  it("собирает строки «- » в список", () => {
    expect(parseBlocks("Итог:\n\n- сумма\n- имущество")).toEqual([
      { kind: "p", text: "Итог:" },
      { kind: "ul", items: ["сумма", "имущество"] },
    ]);
  });

  it("одиночный абзац остаётся абзацем", () => {
    expect(parseBlocks("Просто текст без списков.")).toEqual([{ kind: "p", text: "Просто текст без списков." }]);
  });

  it("не теряет пустые строки внутри пункта", () => {
    expect(parseBlocks("- один\n\n- два")).toEqual([{ kind: "ul", items: ["один"] }, { kind: "ul", items: ["два"] }]);
  });
});

describe("highlightDetails", () => {
  it("выделяет сумму, телефон и время звонка", () => {
    expect(highlightDetails("Долг 500 000 ₽, звонок в 12:00 на +7 999 123-45-67")).toBe(
      "Долг **500 000 ₽**, звонок в **12:00** на **+7 999 123-45-67**",
    );
  });

  it("готовую разметку бэкенда не трогает", () => {
    expect(highlightDetails("Сумма **500 000 ₽** подходит.")).toBe("Сумма **500 000 ₽** подходит.");
  });
});

describe("chatResponseSchema.blocks", () => {
  it("сохраняет блоки ответа, а не срезает их", () => {
    const parsed = chatResponseSchema.parse({
      answer: "Записал вас.",
      sources: [],
      grounded: false,
      top_score: 0,
      blocks: [
        { type: "lead", text: "Записал вас на консультацию." },
        {
          type: "list",
          title: "Что подготовить",
          items: ["Паспорт", "Список кредиторов"],
        },
      ],
      state: {
        kind: "situation",
        step: "booked",
        filters_passed: true,
        search_query: null,
        retrieved: 0,
        chunks: [],
        llm: [],
        profile: {
          debt_amount: 500000,
          region: "Ставропольский край",
          phone: "+7 999 123-45-67",
          consultation_time: "12:00",
          facts: {},
        },
      },
    });
    expect(parsed.blocks.map((block) => block.type)).toEqual(["lead", "list"]);
    expect(parsed.blocks[1]?.title).toBe("Что подготовить");
  });
});
