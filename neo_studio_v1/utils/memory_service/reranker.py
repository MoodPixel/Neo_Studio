from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from .assistant_embedding_runtime import get_assistant_model_status, rerank_with_cross_encoder

RERANKER_NAME = 'neo_local_hybrid_v1'

RERANK_PROFILES: dict[str, dict[str, Any]] = {
    'fast': {
        'label': 'Fast recall',
        'sqlite_limit': 36,
        'chroma_limit': 0,
        'rerank_limit': 24,
        'enabled': False,
        'description': 'SQLite-first recall for lightweight chat previews.',
    },
    'smart': {
        'label': 'Smart recall',
        'sqlite_limit': 56,
        'chroma_limit': 22,
        'rerank_limit': 40,
        'enabled': True,
        'description': 'Hybrid SQLite + embeddings, then local reranking for normal Assistant memory.',
    },
    'deep': {
        'label': 'Deep recall',
        'sqlite_limit': 90,
        'chroma_limit': 42,
        'rerank_limit': 64,
        'enabled': True,
        'description': 'Larger hybrid recall and stricter reranking for repo/debug/implementation tasks.',
    },
}

_STOPWORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'but', 'by', 'can', 'do', 'for', 'from', 'had',
    'has', 'have', 'how', 'i', 'if', 'in', 'into', 'is', 'it', 'its', 'me', 'my', 'of', 'on',
    'or', 'our', 'so', 'that', 'the', 'their', 'this', 'to', 'use', 'we', 'what', 'when', 'where',
    'with', 'you', 'your', 'bro', 'now', 'phase', 'implement', 'need', 'needs', 'able', 'also',
}


_DEBUG_TERMS = {
    'bug', 'fix', 'error', 'traceback', 'failed', 'failure', 'issue', 'crash', 'debug', 'validator',
    'workflow', 'route', 'patch', 'implementation', 'repo', 'extension', 'manifest', 'ui', 'tab', 'memory',
}


def _clean(value: Any, limit: int = 4000) -> str:
    return ' '.join(str(value or '').split())[:limit].strip()


def tokenize(text: Any) -> list[str]:
    tokens = re.findall(r"[a-z0-9_./\\-]+", str(text or '').lower())
    return [token for token in tokens if token and token not in _STOPWORDS and len(token) > 1]


def _bigrams(tokens: list[str]) -> set[tuple[str, str]]:
    return set(zip(tokens, tokens[1:])) if len(tokens) > 1 else set()


def _tf(tokens: list[str]) -> Counter[str]:
    return Counter(tokens)


def _cosine_from_counts(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(float(a[t] * b[t]) for t in common)
    norm_a = math.sqrt(sum(float(v * v) for v in a.values()))
    norm_b = math.sqrt(sum(float(v * v) for v in b.values()))
    if not norm_a or not norm_b:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def _phrase_bonus(query_text: str, document: str) -> float:
    q = _clean(query_text, 1200).lower()
    d = _clean(document, 4000).lower()
    if not q or not d:
        return 0.0
    # Boost exact short phrases from the user request without needing a heavy cross encoder.
    chunks = [chunk.strip() for chunk in re.split(r"[\n,;:.!?()\[\]{}]+", q) if len(chunk.strip()) >= 8]
    hits = 0
    for chunk in chunks[:10]:
        if chunk in d:
            hits += 1
    return min(0.24, hits * 0.06)


def _metadata_bonus(query_tokens: set[str], metadata: dict[str, Any]) -> float:
    bonus = 0.0
    for key, weight in (
        ('chunk_type', 0.08),
        ('entity_type', 0.05),
        ('component', 0.09),
        ('file_path', 0.12),
        ('source_ref', 0.08),
        ('tags', 0.08),
    ):
        value_tokens = set(tokenize(metadata.get(key)))
        if value_tokens and query_tokens & value_tokens:
            bonus += weight
    return min(0.28, bonus)


def _source_confidence(item: dict[str, Any]) -> float:
    source = str(item.get('source') or '').strip().lower()
    if source == 'chroma':
        distance = item.get('distance')
        if isinstance(distance, (int, float)):
            return max(0.0, min(0.18, 0.18 - (float(distance) * 0.04)))
        return 0.08
    if source == 'sqlite_chunk':
        return 0.05
    return 0.02


def resolve_retrieval_profile(lane: str, scope: dict[str, Any] | None = None, requested: str = '') -> str:
    clean = str(requested or '').strip().lower()
    if clean in RERANK_PROFILES:
        return clean
    scope = scope if isinstance(scope, dict) else {}
    scope_mode = ' '.join(str(scope.get(k) or '') for k in ('mode', 'active_tab', 'component', 'implementation_goal', 'workflow'))
    queryish = scope_mode.lower()
    if str(lane or '').strip().lower() == 'neo_project':
        return 'deep'
    if any(term in queryish for term in _DEBUG_TERMS):
        return 'deep'
    return 'smart'


def rerank_candidates(
    *,
    lane: str,
    query_text: str,
    scope: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    profile: str = 'smart',
) -> list[dict[str, Any]]:
    """Local fallback-safe reranker.

    This is intentionally dependency-light. It improves the first-pass rank with
    lexical coverage, short phrase hits, metadata/file-path matches, and source
    confidence. If a future cross-encoder reranker is added, this module is the
    seam to swap it in without touching Assistant chat code.
    """
    if not candidates:
        return []
    profile_config = RERANK_PROFILES.get(profile, RERANK_PROFILES['smart'])
    if not bool(profile_config.get('enabled')):
        return candidates

    q_tokens = tokenize(query_text)
    q_set = set(q_tokens)
    q_counts = _tf(q_tokens)
    q_bigrams = _bigrams(q_tokens)
    scope = scope if isinstance(scope, dict) else {}
    cross_reranked = rerank_with_cross_encoder(query_text, candidates)
    if cross_reranked is not None:
        for item in cross_reranked:
            diagnostics = item.get('diagnostics') if isinstance(item.get('diagnostics'), dict) else {}
            diagnostics.setdefault('retrieval_profile', profile)
            item['diagnostics'] = diagnostics
        return cross_reranked

    out: list[dict[str, Any]] = []

    for idx, item in enumerate(candidates):
        metadata = item.get('metadata') if isinstance(item.get('metadata'), dict) else {}
        document = str(item.get('document') or '')
        doc_tokens = tokenize(document)
        doc_set = set(doc_tokens)
        doc_counts = _tf(doc_tokens)
        doc_bigrams = _bigrams(doc_tokens)

        first_pass = float(item.get('score') or 0.0)
        coverage = (len(q_set & doc_set) / max(1, len(q_set))) if q_set else 0.0
        cosine = _cosine_from_counts(q_counts, doc_counts)
        bigram = (len(q_bigrams & doc_bigrams) / max(1, len(q_bigrams))) if q_bigrams else 0.0
        phrase = _phrase_bonus(query_text, document)
        metadata = metadata if isinstance(metadata, dict) else {}
        meta = _metadata_bonus(q_set, metadata)
        source = _source_confidence(item)

        # Keep the original retrieval score as the backbone, but let the reranker
        # demote weak semantic/keyword matches before context budgeting.
        rerank_score = (
            first_pass * 0.72
            + coverage * 0.60
            + cosine * 0.42
            + bigram * 0.26
            + phrase
            + meta
            + source
            - (idx * 0.002)
        )
        diagnostics = item.get('diagnostics') if isinstance(item.get('diagnostics'), dict) else {}
        diagnostics = {
            **diagnostics,
            'reranker': RERANKER_NAME,
            'retrieval_profile': profile,
            'first_pass_score': first_pass,
            'rerank_coverage': coverage,
            'rerank_cosine': cosine,
            'rerank_bigram': bigram,
            'rerank_phrase_bonus': phrase,
            'rerank_metadata_bonus': meta,
            'rerank_source_bonus': source,
            'rerank_score': rerank_score,
        }
        out.append({**item, 'first_pass_score': first_pass, 'score': rerank_score, 'diagnostics': diagnostics})

    out.sort(key=lambda row: (float(row.get('score') or 0.0), float((row.get('metadata') or {}).get('importance') or 0.0)), reverse=True)
    return out


def get_reranker_status() -> dict[str, Any]:
    model_status = get_assistant_model_status()
    settings = model_status.get('settings') if isinstance(model_status.get('settings'), dict) else {}
    active_backend = str(settings.get('reranker_backend') or 'local_hybrid').strip() or 'local_hybrid'
    return {
        'name': active_backend if active_backend == 'cross_encoder_local' else RERANKER_NAME,
        'type': active_backend,
        'external_dependency': active_backend == 'cross_encoder_local',
        'ready': bool(model_status.get('reranker_ready')),
        'profiles': RERANK_PROFILES,
        'model_runtime': model_status,
        'summary': 'Cross-encoder reranker is used when configured and available; otherwise Neo falls back to local hybrid reranking.',
    }
