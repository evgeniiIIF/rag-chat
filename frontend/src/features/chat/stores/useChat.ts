import { useMutation } from "@tanstack/react-query";
import { postChat } from "../api/chatApi";
import type { ChatRequest, ChatResponse } from "../types";

export function useChat() {
  return useMutation<ChatResponse, Error, ChatRequest>({
    mutationFn: (payload) => postChat(payload),
  });
}
