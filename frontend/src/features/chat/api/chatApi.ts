import { httpClient } from "@/shared/api";
import {
  chatHistorySchema,
  chatResponseSchema,
  type ChatRequest,
  type ChatResponse,
  type ChatTurn,
} from "../types";

export async function postChat(payload: ChatRequest): Promise<ChatResponse> {
  const response = await httpClient.send(chatResponseSchema, {
    method: "POST",
    path: "/chat",
    body: payload,
  });
  logTurn(response);
  return response;
}

// одно сообщение консоли: состояние, чанки (из них собирается контекст) и все вызовы модели
function logTurn(response: ChatResponse): void {
  console.log({
    state: response.state,
    chunks: response.state.chunks,
    llm: response.state.llm,
  });
}

export async function getHistory(sessionId: string): Promise<ChatTurn[]> {
  const response = await httpClient.send(chatHistorySchema, {
    method: "GET",
    path: `/session/history?session_id=${encodeURIComponent(sessionId)}`,
  });
  return response.messages;
}
