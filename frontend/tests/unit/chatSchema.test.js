import { describe, expect, it } from "vitest";
import { chatResponseSchema, chatRequestSchema } from "@/features/chat";
describe("chat zod schemas", () => {
    it("parses a well-formed response", () => {
        const parsed = chatResponseSchema.parse({
            answer: "С 2017 года.",
            sources: [
                { source: "КЦ.docx", paragraph_start: 3, paragraph_end: 3, snippet: "…" },
            ],
            grounded: true,
            top_score: 0.9,
        });
        expect(parsed.grounded).toBe(true);
        expect(parsed.sources[0]?.paragraph_start).toBe(3);
    });
    it("rejects out-of-range top_score", () => {
        expect(() => chatResponseSchema.parse({
            answer: "x",
            sources: [],
            grounded: false,
            top_score: 1.5,
        })).toThrow();
    });
    it("validates history length in request", () => {
        const tooLong = Array.from({ length: 11 }, () => ({
            role: "user",
            content: "q",
        }));
        expect(() => chatRequestSchema.parse({ question: "q", history: tooLong })).toThrow();
    });
});
