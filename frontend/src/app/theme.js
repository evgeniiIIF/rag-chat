import { useEffect, useState } from "react";
const KEY = "ragchat-theme";
function initial() {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark")
        return saved;
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    return prefersDark ? "dark" : "light";
}
export function useTheme() {
    const [theme, setTheme] = useState(initial);
    useEffect(() => {
        const root = document.documentElement;
        if (theme === "dark")
            root.classList.add("dark");
        else
            root.classList.remove("dark");
        localStorage.setItem(KEY, theme);
    }, [theme]);
    return {
        theme,
        toggle: () => { setTheme((t) => (t === "dark" ? "light" : "dark")); },
    };
}
