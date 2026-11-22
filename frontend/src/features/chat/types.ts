import { z } from "zod";

export const chatSourceSchema = z.object({
  source: z.string(),
  paragraph_start: z.number().int().nonnegative(),
  paragraph_end: z.number().int().nonnegative(),
  text: z.string(),
});

export const chatProfileSchema = z.object({
  debt_amount: z.number().int().nullable(),
  region: z.string().nullable(),
  phone: z.string().nullable(),
  consultation_time: z.string().nullable(),
  facts: z.record(z.string()),
});

export const chatChunkSchema = z.object({
  id: z.string(),
  source: z.string(),
  paragraph_start: z.number().int(),
  paragraph_end: z.number().int(),
  score: z.number(),
  text: z.string(),
});

export const llmMessageSchema = z.object({
  role: z.string(),
  content: z.string(),
});

export const llmCallSchema = z.object({
  purpose: z.string(),
  model: z.string(),
  stage: z.string().nullable(),
  system: z.string().nullable(),
  history: z.array(llmMessageSchema),
  inputs: z.record(z.string()),
  messages: z.array(llmMessageSchema),
  output: z.string().nullable(),
});

export const chatStateSchema = z.object({
  kind: z.string().nullable(),
  step: z.string().nullable(),
  filters_passed: z.boolean(),
  search_query: z.string().nullable(),
  retrieved: z.number().int().nonnegative(),
  chunks: z.array(chatChunkSchema),
  profile: chatProfileSchema,
  llm: z.array(llmCallSchema),
});

export const chatResponseSchema = z.object({
  answer: z.string(),
  sources: z.array(chatSourceSchema),
  grounded: z.boolean(),
  top_score: z.number().min(0).max(1),
  state: chatStateSchema,
});

export type ChatResponse = z.infer<typeof chatResponseSchema>;
export type ChatSource = z.infer<typeof chatSourceSchema>;
export type ChatState = z.infer<typeof chatStateSchema>;
export type ChatProfile = z.infer<typeof chatProfileSchema>;
export type ChatChunk = z.infer<typeof chatChunkSchema>;
export type LlmCall = z.infer<typeof llmCallSchema>;
export type LlmMessage = z.infer<typeof llmMessageSchema>;

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
