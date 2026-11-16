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

// iOS/Android: подстраиваем высоту shell под visual viewport (клавиатура).
function applyAppHeight(): void {
  const vv = window.visualViewport;
  const h = vv !== null ? vv.height : window.innerHeight;
  document.documentElement.style.setProperty("--app-height", `${String(h)}px`);
}
applyAppHeight();

if (window.visualViewport !== null) {
  window.visualViewport.addEventListener("resize", applyAppHeight);
  window.visualViewport.addEventListener("scroll", applyAppHeight);
}
window.addEventListener("resize", applyAppHeight);
window.addEventListener("orientationchange", applyAppHeight);

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ChatPage />
    </QueryClientProvider>
  </StrictMode>,
);
