#!/usr/bin/env python3
# pylint: disable=wrong-import-position, duplicate-code, import-error, wrong-import-order
# ruff: noqa: E402
# -*- coding: utf-8 -*-
"""
L4 Cross-Encoder Reranker – финальный штрих к гибридному поиску.

Загружает легковесную модель cross-encoder/ms-marco-MiniLM-L-6-v2
лениво (при первом использовании) и предоставляет функцию
rerank(query, candidates) для переупорядочивания топ‑выдачи,
полученной от RRF. Модуль не имеет побочных эффектов: возвращает
НОВЫЙ список результатов, не изменяя входной.

``sentence_transformers`` импортируется лениво (внутри ``_get_model``),
а не на уровне модуля — поэтому импорт ``l4_rerank`` никогда не падает
даже если зависимость не установлена: реранк просто молча отключается
(возвращает копию входного списка).

Контракт:
- Принимает query (str) и candidates (list[RankedResult]).
- Возвращает НОВЫЙ список RankedResult, отсортированный по убыванию
  релевантности согласно cross‑encoder'у. Оригинальные объекты не
  мутируются.
- Если модель недоступна, возвращает копию исходного списка без
  изменений и пишет предупреждение в лог.

.. note::
   Значения ``rerank_score`` не являются вероятностями и не
   откалиброваны — они имеют смысл только относительно друг друга
   в рамках одного запроса.

.. note::
   Модуль предназначен для реранкинга небольших кандидатских
   наборов (обычно top‑10 … top‑50). На очень больших наборах
   время работы может стать заметным.

.. warning::
   Потокобезопасность зависит от внутреннего устройства
   sentence‑transformers. При параллельном использовании
   рекомендуется вызывать ``rerank`` из одного потока.
"""

from __future__ import annotations

import logging
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, List, TypedDict

sys.path.insert(0, str(Path(__file__).parent))

from ranking import RankedResult

if TYPE_CHECKING:
    # Import only under the type-checker guard so that merely importing
    # ``l4_rerank`` never hard-requires ``sentence_transformers``. This
    # matches the lazy-load pattern already used by l4_semantic_global.py:
    # the (heavy, optional) CrossEncoder is pulled in on first use inside
    # :func:`_get_model`, not at module import time.
    from sentence_transformers import CrossEncoder

_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_MAX_SNIPPET_CHARS = 1200  # ограничиваем длину для скорости и качества
_BATCH_SIZE = int(os.getenv("RERANK_BATCH_SIZE", "16"))


# ---------------------------------------------------------------------------
# Типы для повышения читаемости (mypy‑friendly)
# ---------------------------------------------------------------------------
class RetrievalHit(TypedDict, total=False):
    """Структура одного хита в источнике (snippet/text/score/distance)."""

    snippet: str
    text: str
    score: float
    distance: float


# ---------------------------------------------------------------------------
# Ленивая загрузка модели – не нагружает импорт
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _get_model() -> CrossEncoder | None:
    """Возвращает модель CrossEncoder или None при ошибке."""
    try:
        # Lazy import: keeps ``import l4_rerank`` cheap and lets the module
        # load on hosts where sentence_transformers isn't installed (the
        # caller simply gets ``None`` and a graceful no-op rerank).
        from sentence_transformers import CrossEncoder  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        logging.warning(
            "sentence_transformers not installed; rerank disabled: %s", exc,
        )
        return None
    try:
        return CrossEncoder(_MODEL_NAME)
    except Exception as exc:  # nosec
        logging.warning("Failed to load cross-encoder model %s: %s", _MODEL_NAME, exc)
        return None


# ---------------------------------------------------------------------------
# Выбор лучшего сниппета (retrieval policy)
# ---------------------------------------------------------------------------
def _hit_quality(hit: RetrievalHit) -> float:
    """
    Оценивает «качество» одного хита для выбора сниппета.

    Приоритет метрик (чем выше значение, тем лучше):
    1. Явный score (BM25, RRF и т.п.)
    2. Обратное distance (для семантических хитов)

    Heuristic only for snippet selection, not global ranking.
    """
    # Явный score – предпочтительнее
    score = hit.get("score")
    if score is not None and isinstance(score, (int, float)):
        return float(score)

    # Семантическое расстояние: чем меньше, тем лучше
    distance = hit.get("distance")
    if distance is not None and isinstance(distance, (int, float)):
        return 1.0 / (1.0 + float(distance))

    return 0.0


def _best_snippet(hits: list) -> str:
    """
    Выбрать лучший сниппет из списка хитов.

    Если список пуст, возвращает пустую строку (total‑function).
    """
    if not hits:
        return ""
    best_hit = max(hits, key=_hit_quality)
    snippet = best_hit.get("snippet") or best_hit.get("text", "")
    return snippet[:_MAX_SNIPPET_CHARS]


# ---------------------------------------------------------------------------
# Основная функция rerank
# ---------------------------------------------------------------------------
# pylint: disable=too-many-locals
def rerank(query: str, candidates: List[RankedResult]) -> List[RankedResult]:
    """
    Пересортирует candidates с помощью cross‑encoder'а.

    Args:
        query: Исходный поисковый запрос.
        candidates: Список результатов (обычно топ‑20 после RRF).

    Returns:
        Новый список RankedResult, отсортированный по убыванию
        rerank_score. Если модель не загружена, возвращает
        shallow copy входного списка без изменений.
    """
    model = _get_model()
    if model is None or not candidates:
        return list(candidates)  # shallow copy – pure function

    # Собираем все хиты из всех источников для каждого документа
    texts: List[str] = []
    for res in candidates:
        all_hits = [hit for source_hits in res.sources.values() for hit in source_hits]
        texts.append(_best_snippet(all_hits))

    # Вычисляем скоры cross‑encoder'ом
    try:
        pairs = [(query, text) for text in texts]
        scores = model.predict(
            list(pairs),  # type: ignore[arg-type]
            batch_size=_BATCH_SIZE,
            show_progress_bar=False,
        )
    except Exception as exc:  # nosec
        logging.warning("Cross-encoder prediction failed: %s", exc)
        return list(candidates)

    # Формируем новый список результатов
    new_results: List[RankedResult] = []
    for res, score in zip(candidates, scores):
        rerank_score = float(score)

        # Копируем источники, НЕ добавляя rerank_score внутрь хитов
        new_sources = {}
        for src_name, hits in res.sources.items():
            new_sources[src_name] = [dict(h) for h in hits]

        new_res = RankedResult(
            key=res.key,
            score=res.score,
            normalized_score=res.normalized_score,
            sources=new_sources,
        )
        new_res.rerank_score = rerank_score
        new_results.append(new_res)

    # Сортируем новый список по убыванию rerank_score
    new_results.sort(key=lambda r: getattr(r, "rerank_score", 0.0), reverse=True)
    return new_results
