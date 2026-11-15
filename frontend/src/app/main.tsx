import "@/styles/index.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ChatPage } from "@/pages/ChatPage";
import { env } from "./env";

const queryClient = new QueryClient();

const root = document.getElementById("root");
if (root === null) {
  throw new Error("Не найден #root");
}

document.title = env.appName;

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <main style={{ fontFamily: "system-ui, sans-serif", padding: 16 }}>
        <ChatPage />
      </main>
    </QueryClientProvider>
  </StrictMode>,
);
