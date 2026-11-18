import { z } from "zod";

export const chatSourceSchema = z.object({
  source: z.string(),
  paragraph_start: z.number().int().nonnegative(),
  paragraph_end: z.number().int().nonnegative(),
  text: z.string(),
});

export const chatResponseSchema = z.object({
  answer: z.string(),
  sources: z.array(chatSourceSchema),
  grounded: z.boolean(),
  top_score: z.number().min(0).max(1),
});

export type ChatResponse = z.infer<typeof chatResponseSchema>;
export type ChatSource = z.infer<typeof chatSourceSchema>;

export const chatTurnSchema = z.object({
  role: z.enum(["user", "assistant"]),
  content: z.string().min(1).max(2000),
});

export type ChatTurn = z.infer<typeof chatTurnSchema>;

export const chatRequestSchema = z.object({
  question: z.string().min(1).max(2000),
  history: z.array(chatTurnSchema).max(30).optional(),
  session_id: z.string().min(1).max(64).optional(),
  k: z.number().int().min(1).max(10).optional(),
});

export type ChatRequest = z.infer<typeof chatRequestSchema>;
