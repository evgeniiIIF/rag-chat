import { httpClient } from "@/shared/api";
import { chatResponseSchema, type ChatRequest, type ChatResponse } from "../types";

export async function postChat(payload: ChatRequest): Promise<ChatResponse> {
  const response = await httpClient.send(chatResponseSchema, {
    method: "POST",
    path: "/chat",
    body: payload,
  });
  // в консоли — только сообщения, которые реально ушли в модель, ничего больше
  for (const call of response.state.llm) {
    console.log(call.messages);
  }
  return response;
}
