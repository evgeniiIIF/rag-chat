import { httpClient } from "@/shared/api";
import {
  chatResponseSchema,
  type ChatChunk,
  type ChatProfile,
  type ChatRequest,
  type ChatResponse,
  type LlmCall,
  type LlmMessage,
} from "../types";

export interface TurnLog {
  state: {
    question: string;
    answer: string;
    kind: string | null;
    step: string | null;
    profile: ChatProfile;
    filters_passed: boolean;
    grounded: boolean;
    top_score: number;
  };
  history: LlmMessage[];
  context: {
    search_query: string | null;
    chunks: ChatChunk[];
  };
  llm: LlmCall[];
}

export async function postChat(payload: ChatRequest): Promise<ChatResponse> {
  const response = await httpClient.send(chatResponseSchema, {
    method: "POST",
    path: "/chat",
    body: payload,
  });
  // один объект на ход: стейт, история, контекст и всё, что подано модели
  console.log(`💬 ${payload.question}`, turnLog(payload, response));
  return response;
}

function turnLog(payload: ChatRequest, response: ChatResponse): TurnLog {
  const state = response.state;
  const lastCall = state.llm[state.llm.length - 1];
  return {
    state: {
      question: payload.question,
      answer: response.answer,
      kind: state.kind,
      step: state.step,
      profile: state.profile,
      filters_passed: state.filters_passed,
      grounded: response.grounded,
      top_score: response.top_score,
    },
    history: lastCall?.history ?? [],
    context: {
      search_query: state.search_query,
      chunks: state.chunks,
    },
    llm: state.llm,
  };
}
