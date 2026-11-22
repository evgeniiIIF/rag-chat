"""Просмотр графа: схему рисует сам LangGraph, страница только показывает её.

Источник картинки — `draw_mermaid()` скомпилированного графа (graph/build.py): никакой
рукописной схемы нет, поэтому картинка не может разойтись с кодом.
Картинку рендерит браузер (mermaid.js с CDN): draw_mermaid_png() рендерит на сервере
через mermaid.ink, а внешний HTTP из контейнера не гарантирован.

/api/graph         — страница с диаграммой (вписывание выключено, скролл + зум браузера);
/api/graph/mermaid — тот же mermaid-текст, для копирования в редактор.

Текст графа уходит в страницу в base64: так `<p>` и стрелки в нём не искажает HTML-парсер.
"""

from __future__ import annotations

from base64 import b64encode

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, PlainTextResponse

from api.chat import ServiceDep

router = APIRouter(tags=["graph"])

PAGE = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>v3 · граф</title>
  <style>
    html, body { margin: 0; background: #fff; }
    body { font: 18px/1.4 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
    #graph { padding: 20px; }
    #graph svg { max-width: none; height: auto; }
  </style>
</head>
<body>
<div id="graph"></div>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>
  const GRAPH_B64 = "__GRAPH_B64__";
  const decode = (b64) =>
    new TextDecoder().decode(Uint8Array.from(atob(b64), (ch) => ch.charCodeAt(0)));

  mermaid.initialize({
    startOnLoad: false,
    theme: "base",
    themeVariables: {
      fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
      fontSize: "18px",
      lineColor: "#94a3b8",
      primaryColor: "#eef2ff",
      primaryBorderColor: "#6366f1",
      primaryTextColor: "#1e1b4b",
    },
    flowchart: { curve: "basis", nodeSpacing: 34, rankSpacing: 48, useMaxWidth: false },
  });

  mermaid
    .render("graph-svg", decode(GRAPH_B64))
    .then(({ svg }) => { document.getElementById("graph").innerHTML = svg; })
    .catch((error) => { document.getElementById("graph").textContent = String(error); });
</script>
</body>
</html>
"""


def _b64(source: str) -> str:
    return b64encode(source.encode("utf-8")).decode("ascii")


def _mermaid(service: ServiceDep) -> str:
    """Структура скомпилированного графа в нотации mermaid."""
    return str(service.graph.get_graph().draw_mermaid())


@router.get("/graph/mermaid", response_class=PlainTextResponse)
def graph_mermaid(service: ServiceDep) -> str:
    """Узлы, рёбра и условия условных переходов — текстом."""
    return _mermaid(service)


@router.get("/graph", response_class=HTMLResponse)
def graph_page(service: ServiceDep) -> str:
    """Диаграмма из draw_mermaid(): без рукописных подписей и таблиц."""
    return PAGE.replace("__GRAPH_B64__", _b64(_mermaid(service)))
