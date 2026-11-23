import { useMutation, useQuery } from "@tanstack/react-query";
import { getHistory, postChat } from "../api/chatApi";
import type { ChatRequest, ChatResponse, ChatTurn } from "../types";

export function useChat() {
  return useMutation<ChatResponse, Error, ChatRequest>({
    mutationFn: (payload) => postChat(payload),
  });
}

export function useHistory(sessionId: string) {
  return useQuery<ChatTurn[]>({
    queryKey: ["history", sessionId],
    queryFn: () => getHistory(sessionId),
  });
}
