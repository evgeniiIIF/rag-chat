"""Тесты индекса корпуса: манифест решает перестройку, артефакты пишутся."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from core.config import Settings
from domain.models import Chunk, RetrievedChunk
from infrastructure.artifacts import read_json, read_jsonl
from infrastructure.loader import LoadedDocument
from infrastructure.splitter import chunk_id
from services.index_service import CHUNKS_NAME, MANIFEST_NAME, IndexService, build_manifest


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        api_key=SecretStr("test"),
        data_dir=tmp_path / "data",
        artifacts_dir=tmp_path / "artifacts",
        chroma_dir=tmp_path / "chroma",
        chunks_doc=tmp_path / "docs" / "chunks.md",
    )


def make_document(sha: str = "a" * 64) -> LoadedDocument:
    return LoadedDocument(
        source="doc.docx",
        text="В процедуру берут с суммой от 350 000 рублей, если общий долг больше порога.",
        sha256=sha,
    )


class FakeRetriever:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks

    def search(self, question: str, k: int) -> list[RetrievedChunk]:
        return []


class FakeIndexFactory:
    def __init__(self) -> None:
        self.calls: list[tuple[int, bool]] = []

    def __call__(self, chunks: list[Chunk], settings: Settings, *, rebuild: bool) -> FakeRetriever:
        self.calls.append((len(chunks), rebuild))
        return FakeRetriever(list(chunks))


def make_service(tmp_path: Path, documents: list[LoadedDocument], factory: FakeIndexFactory) -> IndexService:
    def loader(data_dir: Path) -> list[LoadedDocument]:
        return documents

    def split(docs: list[LoadedDocument]) -> list[Chunk]:
        return [
            Chunk(
                id=chunk_id(document.source, order),
                source=document.source,
                order=order,
                paragraph_start=1,
                paragraph_end=1,
                text=document.text,
            )
            for order, document in enumerate(docs)
        ]

    return IndexService(
        make_settings(tmp_path),
        loader=loader,
        split=split,
        index_factory=factory,  # type: ignore[arg-type]
    )


def test_first_run_builds_and_writes_artifacts(tmp_path: Path) -> None:
    factory = FakeIndexFactory()
    service = make_service(tmp_path, [make_document()], factory)

    service.ensure_index()

    index_dir = make_settings(tmp_path).artifacts_dir / "index"
    assert factory.calls == [(1, True)]
    assert read_json(index_dir / MANIFEST_NAME) is not None
    assert read_jsonl(index_dir / CHUNKS_NAME)[0]["source"] == "doc.docx"
    assert [chunk.order for chunk in service.chunks] == [0]


def test_second_run_reuses_index(tmp_path: Path) -> None:
    factory = FakeIndexFactory()
    make_service(tmp_path, [make_document()], factory).ensure_index()
    service = make_service(tmp_path, [make_document()], factory)

    service.ensure_index()

    assert factory.calls == [(1, True), (1, False)]


def test_changed_document_rebuilds_index(tmp_path: Path) -> None:
    factory = FakeIndexFactory()
    make_service(tmp_path, [make_document()], factory).ensure_index()
    service = make_service(tmp_path, [make_document(sha="b" * 64)], factory)

    service.ensure_index()

    assert factory.calls[-1] == (1, True)


def test_missing_chunks_file_forces_rebuild(tmp_path: Path) -> None:
    factory = FakeIndexFactory()
    make_service(tmp_path, [make_document()], factory).ensure_index()
    chunks_path = make_settings(tmp_path).artifacts_dir / "index" / CHUNKS_NAME
    chunks_path.write_text("", encoding="utf-8")

    make_service(tmp_path, [make_document()], factory).ensure_index()

    assert factory.calls[-1] == (1, True)


def test_search_requires_index(tmp_path: Path) -> None:
    service = make_service(tmp_path, [make_document()], FakeIndexFactory())

    with pytest.raises(RuntimeError, match="индекс не построен"):
        service.search("вопрос", 3)

    service.ensure_index()
    assert service.search("вопрос", 3) == []


def test_build_manifest_contains_settings(tmp_path: Path) -> None:
    manifest = build_manifest([make_document()], make_settings(tmp_path))

    assert manifest["chunking"] == "paragraph"
    assert manifest["splitter_version"] == 3
    assert manifest["documents"] == [{"source": "doc.docx", "sha256": "a" * 64}]


def test_snapshot_is_written_with_index(tmp_path: Path) -> None:
    """chunks/chunks.md обновляется при сборке индекса, без ручного make chunks."""
    service = make_service(tmp_path, [make_document()], FakeIndexFactory())

    service.ensure_index()

    text = make_settings(tmp_path).chunks_doc.read_text(encoding="utf-8")
    assert "## doc.docx-0000" in text
    assert "- абзацы: 1-1" in text


def test_snapshot_failure_does_not_break_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Read-only каталог: снимок не обновился, но индекс и поиск работают."""
    service = make_service(tmp_path, [make_document()], FakeIndexFactory())

    def broken(chunks: object, path: Path) -> None:
        raise OSError("read-only")

    monkeypatch.setattr("services.index_service.write_chunks_markdown", broken)

    service.ensure_index()

    assert [chunk.order for chunk in service.chunks] == [0]
