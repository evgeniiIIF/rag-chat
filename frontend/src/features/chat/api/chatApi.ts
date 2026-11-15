import { httpClient } from "@/shared/api";
import { chatResponseSchema, type ChatRequest, type ChatResponse } from "../types";

export async function postChat(payload: ChatRequest): Promise<ChatResponse> {
  return httpClient.send(chatResponseSchema, {
    method: "POST",
    path: "/chat",
    body: payload,
  });
}
