"""Итог ответа: ответил по документу / не смог / ответил по-человечески без документа."""

from __future__ import annotations

from enum import StrEnum


class Grounding(StrEnum):
    GROUNDED = "grounded"  # ответ по контексту, есть источники
    NOT_ANSWERABLE = "not_answerable"  # ответа в базе нет (в т.ч. тема вне корпуса)
    SOCIAL = "social"  # соц-реплика, отказ вне темы, договорённость о консультации — без документа
