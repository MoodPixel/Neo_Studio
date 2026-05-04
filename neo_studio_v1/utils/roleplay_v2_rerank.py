from __future__ import annotations

import re
from functools import lru_cache
from typing import Any


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", str(text or '').lower()))


@lru_cache(maxsize=2)
def _load_cross_encoder(model_path: str):
    clean_path = str(model_path or '').strip()
    if not clean_path:
        return None
    try:
        from sentence_transformers import CrossEncoder  # type: ignore
    except Exception:
        return None
    try:
        return CrossEncoder(clean_path)
    except Exception:
        return None


def _token_overlap_rerank(query: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    query_tokens = _tokenize(query)
    reranked: list[dict[str, Any]] = []
    for row in rows:
        tokens = set(row.get('tokens') or [])
        overlap = len(query_tokens & tokens)
        salience = float(row.get('salience') or 0.0)
        base_score = float(row.get('score') or 0.0)
        rerank_bonus = overlap * 0.06 + salience * 0.08
        enriched = dict(row)
        enriched['score'] = round(base_score + rerank_bonus, 6)
        enriched['rerank_overlap'] = overlap
        enriched['rerank_backend'] = 'token_overlap'
        reranked.append(enriched)
    reranked.sort(key=lambda item: float(item.get('score') or 0.0), reverse=True)
    return reranked


def _cross_encoder_rerank(query: str, rows: list[dict[str, Any]], model_path: str) -> list[dict[str, Any]]:
    model = _load_cross_encoder(model_path)
    if model is None:
        return _token_overlap_rerank(query, rows)
    pairs: list[tuple[str, str]] = []
    for row in rows:
        doc = str(row.get('document') or '').strip()
        title = str(row.get('title') or '').strip()
        pairs.append((query, f'{title}\n{doc}'.strip()))
    try:
        scores = model.predict(pairs)
    except Exception:
        return _token_overlap_rerank(query, rows)
    reranked: list[dict[str, Any]] = []
    for row, rerank_score in zip(rows, scores):
        base_score = float(row.get('score') or 0.0)
        enriched = dict(row)
        enriched['score'] = round(base_score + float(rerank_score), 6)
        enriched['cross_encoder_score'] = round(float(rerank_score), 6)
        enriched['rerank_backend'] = 'cross_encoder_local'
        reranked.append(enriched)
    reranked.sort(key=lambda item: float(item.get('score') or 0.0), reverse=True)
    return reranked



def rerank_results(query: str, rows: list[dict[str, Any]], settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    active_settings = settings if isinstance(settings, dict) else {}
    backend = str(active_settings.get('reranker_backend') or 'token_overlap').strip().lower()
    if backend == 'cross_encoder_local':
        return _cross_encoder_rerank(query, rows, str(active_settings.get('reranker_model_path') or '').strip())
    return _token_overlap_rerank(query, rows)
