"""Итог ответа: ответил по документу / не смог."""

from __future__ import annotations

from enum import StrEnum


class Grounding(StrEnum):
    GROUNDED = "grounded"
    NOT_ANSWERABLE = "not_answerable"
