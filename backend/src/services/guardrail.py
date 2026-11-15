"""Input Guardrail: защита от мусора, оскорблений и prompt injection."""

from __future__ import annotations

TOXIC_WORDS = {
    "дурак", "тупой", "идиот", "хер", "бля", "сука", "говно", "мразь", "убей", "ублюдок"
}

INJECTION_PATTERNS = {
    "ignore previous", "ignore all", "забудь все инструкции", "system prompt",
    "повтори свои инструкции", "выведи инструкции", "ты теперь", "act as"
}

class InputGuardrail:
    def __init__(self) -> None:
        self._toxic = TOXIC_WORDS
        self._injection = INJECTION_PATTERNS

    def check(self, question: str) -> bool:
        """Возвращает True, если вопрос безопасен. False — если нужно отклонить."""
        low = question.lower()
        
        # 1) Токсичность
        if any(word in low for word in self._toxic):
            return False
            
        # 2) Prompt injection
        if any(pattern in low for pattern in self._injection):
            return False
            
        return True
