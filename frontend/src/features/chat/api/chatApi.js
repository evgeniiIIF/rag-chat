import { httpClient } from "@/shared/api";
import { chatResponseSchema } from "../types";
export async function postChat(payload) {
    return httpClient.send(chatResponseSchema, {
        method: "POST",
        path: "/chat",
        body: payload,
    });
}
