"""Тесты загрузчика: docx → текст, sha256 содержимого, ошибки конфигурации."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest

from infrastructure import loader as loader_module
from infrastructure.loader import load_documents


class FakeDocx2txtLoader:
    """Подмена Docx2txtLoader: без чтения реального .docx."""

    pages: ClassVar[list[str]] = ["Первый абзац.", "Второй абзац."]
    calls: ClassVar[list[str]] = []

    def __init__(self, path: str) -> None:
        self._path = path

    def load(self) -> list[SimpleNamespace]:
        self.calls.append(self._path)
        return [SimpleNamespace(page_content=page) for page in self.pages]


@pytest.fixture
def docx_dir(tmp_path: Path) -> Path:
    (tmp_path / "КЦ.docx").write_bytes(b"docx-bytes")
    return tmp_path


def test_load_documents_reads_text_and_hash(monkeypatch: pytest.MonkeyPatch, docx_dir: Path) -> None:
    monkeypatch.setattr(loader_module, "Docx2txtLoader", FakeDocx2txtLoader)

    documents = load_documents(docx_dir)

    assert len(documents) == 1
    document = documents[0]
    assert document.source == "КЦ.docx"
    assert document.text == "Первый абзац.\n\nВторой абзац."
    assert len(document.sha256) == 64


def test_load_documents_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="каталог документов не найден"):
        load_documents(tmp_path / "нет такого")


def test_load_documents_empty_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="нет файлов"):
        load_documents(tmp_path)


def test_load_documents_empty_text(monkeypatch: pytest.MonkeyPatch, docx_dir: Path) -> None:
    class EmptyLoader(FakeDocx2txtLoader):
        pages: ClassVar[list[str]] = ["   ", ""]

    monkeypatch.setattr(loader_module, "Docx2txtLoader", EmptyLoader)
    with pytest.raises(ValueError, match="документ пуст"):
        load_documents(docx_dir)
