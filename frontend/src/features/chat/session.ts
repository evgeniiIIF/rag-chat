/**
 * Идентификатор диалога (цепочка chat_v2, узел [FE] 03).
 *
 * Клиент хранит session_id в localStorage: перезагрузка страницы и переход на другую
 * вкладку не роняют состояние диалога на сервере. Новый чат = новый id.
 * SSR/приватный режим (localStorage кидается) → id живёт только в памяти вкладки.
 * http://IP — не secure context: crypto.randomUUID там отсутствует, поэтому запасной id
 * собирается из времени и Math.random (иначе падал весь render → белый экран).
 */

const STORAGE_KEY = "rag_chat_session_id";

let memoryFallback: string | null = null;

function createId(): string {
  const webCrypto: Crypto | undefined = globalThis.crypto;
  if (typeof webCrypto?.randomUUID === "function") return webCrypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function getSessionId(): string {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored !== null && stored.length > 0) return stored;
    const fresh = createId();
    localStorage.setItem(STORAGE_KEY, fresh);
    return fresh;
  } catch {
    if (memoryFallback === null) memoryFallback = createId();
    return memoryFallback;
  }
}

export function resetSessionId(): string {
  const fresh = createId();
  memoryFallback = fresh;
  try {
    localStorage.setItem(STORAGE_KEY, fresh);
  } catch {
    /* память вкладки уже обновлена выше */
  }
  return fresh;
}
