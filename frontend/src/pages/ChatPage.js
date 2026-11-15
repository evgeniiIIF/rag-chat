import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useRef, useState } from "react";
import { useChat } from "@/features/chat";
import { ChatMessageList } from "@/components/ChatMessageList";
import { UIButton, UIInput } from "@/shared/ui";
import { useTheme } from "@/app/theme";
let seq = 0;
function nextId() {
    seq += 1;
    return `m${String(seq)}`;
}
export function ChatPage() {
    const [messages, setMessages] = useState([]);
    const [draft, setDraft] = useState("");
    const inputRef = useRef(null);
    const { mutateAsync, isPending, error } = useChat();
    const { theme, toggle } = useTheme();
    async function send() {
        const q = draft.trim();
        if (q.length === 0)
            return;
        setDraft("");
        setMessages((prev) => [...prev, { id: nextId(), role: "user", text: q }]);
        try {
            const response = await mutateAsync({ question: q });
            setMessages((prev) => [
                ...prev,
                { id: nextId(), role: "assistant", text: response.answer, response },
            ]);
        }
        catch {
            setMessages((prev) => [
                ...prev,
                { id: nextId(), role: "assistant", text: "Ошибка запроса." },
            ]);
        }
        finally {
            inputRef.current?.focus();
        }
    }
    return (_jsxs("div", { className: "flex h-screen flex-col bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100", children: [_jsx("header", { className: "border-b border-slate-200 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-900/80", children: _jsxs("div", { className: "mx-auto flex max-w-3xl items-center justify-between px-4 py-3", children: [_jsxs("div", { className: "flex items-center gap-3", children: [_jsx("div", { className: "flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-white", children: "\uD83D\uDCAC" }), _jsxs("div", { children: [_jsx("h1", { className: "text-sm font-semibold", children: "RAG Chat" }), _jsx("p", { className: "text-xs text-slate-500 dark:text-slate-400", children: "\u041E\u0442\u0432\u0435\u0442\u044B \u0441\u0442\u0440\u043E\u0433\u043E \u043F\u043E \u0434\u043E\u043A\u0443\u043C\u0435\u043D\u0442\u0443" })] })] }), _jsx("button", { type: "button", onClick: toggle, "aria-label": "\u041F\u0435\u0440\u0435\u043A\u043B\u044E\u0447\u0438\u0442\u044C \u0442\u0435\u043C\u0443", className: "rounded-lg border border-slate-200 px-3 py-1.5 text-sm hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800", children: theme === "dark" ? "☀️" : "🌙" })] }) }), _jsxs("main", { className: "mx-auto flex w-full max-w-3xl flex-1 flex-col overflow-hidden", children: [_jsx("div", { className: "flex-1 overflow-y-auto px-4 py-6", children: _jsx(ChatMessageList, { messages: messages, pending: isPending }) }), _jsxs("form", { onSubmit: (e) => {
                            e.preventDefault();
                            void send();
                        }, className: "border-t border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900", children: [_jsxs("div", { className: "mx-auto flex max-w-3xl gap-2", children: [_jsx(UIInput, { ref: inputRef, value: draft, onChange: (e) => { setDraft(e.target.value); }, placeholder: "\u0421\u043F\u0440\u043E\u0441\u0438\u0442\u0435 \u043F\u043E \u0434\u043E\u043A\u0443\u043C\u0435\u043D\u0442\u0443\u2026", disabled: isPending }), _jsx(UIButton, { type: "submit", disabled: isPending || draft.trim().length === 0, children: isPending ? "…" : "Отправить" })] }), error && (_jsxs("p", { className: "mx-auto mt-2 max-w-3xl text-xs text-rose-600 dark:text-rose-400", children: ["\u041E\u0448\u0438\u0431\u043A\u0430: ", error.message] }))] })] })] }));
}
