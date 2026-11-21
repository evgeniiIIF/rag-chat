"""Тесты JSON-логов: формат строки и передача extra-полей."""

from __future__ import annotations

import json
import logging

from core.logging import JsonFormatter, configure_logging


def _record(msg: str, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="core.test", level=logging.INFO, pathname=__file__, lineno=1, msg=msg, args=(), exc_info=None
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formatter_writes_json_with_extras() -> None:
    payload = json.loads(JsonFormatter().format(_record("retrieve", node="retrieve", k=3)))

    assert payload["msg"] == "retrieve"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "core.test"
    assert payload["node"] == "retrieve"
    assert payload["k"] == 3


def test_configure_logging_sets_json_handler() -> None:
    configure_logging("warning")

    root = logging.getLogger()
    assert root.level == logging.WARNING
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
