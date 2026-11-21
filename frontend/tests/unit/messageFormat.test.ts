import { describe, expect, it } from "vitest";
import { parseBlocks } from "@/components/ChatMessageList";

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
