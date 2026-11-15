import { useMutation } from "@tanstack/react-query";
import { postChat } from "../api/chatApi";
export function useChat() {
    return useMutation({
        mutationFn: (payload) => postChat(payload),
    });
}
