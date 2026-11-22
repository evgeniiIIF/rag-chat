import { describe, expect, it } from "vitest";
import { chatResponseSchema, chatRequestSchema } from "@/features/chat";

describe("chat zod schemas", () => {
  it("parses a well-formed response", () => {
    const parsed = chatResponseSchema.parse({
      answer: "С 2017 года.",
      sources: [
        { source: "КЦ.docx", paragraph_start: 3, paragraph_end: 3, text: "…" },
      ],
      grounded: true,
      top_score: 0.9,
      state: {
        kind: "question",
        step: "rag",
        filters_passed: true,
        search_query: "срок исковой давности",
        retrieved: 1,
        chunks: [
          {
            id: "КЦ.docx-0000",
            source: "КЦ.docx",
            paragraph_start: 3,
            paragraph_end: 3,
            score: 0.72,
            text: "…",
          },
        ],
        llm: [
          {
            purpose: "answer",
            model: "gpt-4o-mini",
            stage: "rag",
            system: "system prompt",
            history: [{ role: "human", content: "предыдущий вопрос" }],
            inputs: { вопрос: "…", "состояние фильтров": "фильтры: пройдены" },
            messages: [
              { role: "system", content: "…" },
              { role: "human", content: "…" },
            ],
            output: '{"answer":"…"}',
          },
        ],
        profile: {
          debt_amount: 800000,
          region: "Москва",
          phone: null,
          consultation_time: null,
          facts: {},
        },
      },
    });
    expect(parsed.grounded).toBe(true);
    expect(parsed.sources[0]?.paragraph_start).toBe(3);
    expect(parsed.state.filters_passed).toBe(true);
    expect(parsed.state.llm[0]?.purpose).toBe("answer");
  });

  it("rejects out-of-range top_score", () => {
    expect(() =>
      chatResponseSchema.parse({
        answer: "x",
        sources: [],
        grounded: false,
        top_score: 1.5,
        state: {
          kind: "question",
          step: "rag",
          filters_passed: true,
          search_query: "срок исковой давности",
          retrieved: 1,
          chunks: [],
          llm: [],
          profile: {
            debt_amount: 800000,
            region: "Москва",
            phone: null,
            consultation_time: null,
            facts: {},
          },
        },
      }),
    ).toThrow();
  });

  it("validates history length in request", () => {
    const tooLong = Array.from({ length: 31 }, () => ({
      role: "user" as const,
      content: "q",
    }));
    expect(() => chatRequestSchema.parse({ question: "q", history: tooLong })).toThrow();
    const ok = Array.from({ length: 30 }, () => ({ role: "user" as const, content: "q" }));
    expect(() => chatRequestSchema.parse({ question: "q", history: ok })).not.toThrow();
  });

  it("accepts an optional session_id and bounds its length", () => {
    expect(() => chatRequestSchema.parse({ question: "q", session_id: "abc" })).not.toThrow();
    expect(() => chatRequestSchema.parse({ question: "q", session_id: "" })).toThrow();
    expect(() => chatRequestSchema.parse({ question: "q", session_id: "x".repeat(65) })).toThrow();
  });
});
