from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from .roleplay_v2_index_jobs import RETRIEVAL_INDEX_PATH, load_memory_index, load_retrieval_settings, rebuild_memory_index, save_retrieval_settings
from .roleplay_v2_rerank import rerank_results
from .roleplay_v2_foundation import ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR
from .roleplay_v2_snapshot_store import normalize_memory_scope, normalize_promotion_scope

SCOPE_FILTER_FIELDS: tuple[str, ...] = (
    'source_snapshot_id',
    'canon_snapshot_id',
    'sandbox_id',
    'storyline_id',
    'session_id',
    'checkpoint_id',
    'branch_id',
    'memory_scope',
    'promotion_scope',
)


def _clean(value: Any, *, lower: bool = False) -> str:
    text = str(value or '').strip()
    return text.lower() if lower else text


def _scope_filters(
    *,
    source_snapshot_id: str = '',
    canon_snapshot_id: str = '',
    sandbox_id: str = '',
    storyline_id: str = '',
    session_id: str = '',
    checkpoint_id: str = '',
    branch_id: str = '',
    memory_scope: str = '',
    promotion_scope: str = '',
) -> dict[str, str]:
    raw = {
        'source_snapshot_id': source_snapshot_id,
        'canon_snapshot_id': canon_snapshot_id,
        'sandbox_id': sandbox_id,
        'storyline_id': storyline_id,
        'session_id': session_id,
        'checkpoint_id': checkpoint_id,
        'branch_id': branch_id,
        'memory_scope': normalize_memory_scope(memory_scope, 'sandbox') if _clean(memory_scope) else '',
        'promotion_scope': normalize_promotion_scope(promotion_scope, 'sandbox_only') if _clean(promotion_scope) else '',
    }
    return {key: _clean(value, lower=key in {'memory_scope', 'promotion_scope'}) for key, value in raw.items() if _clean(value)}


def _entry_scope_value(entry: dict[str, Any], field_name: str) -> str:
    value = _clean(entry.get(field_name), lower=field_name in {'memory_scope', 'promotion_scope'})
    if value:
        return value
    extra = entry.get('extra') if isinstance(entry.get('extra'), dict) else {}
    return _clean(extra.get(field_name), lower=field_name in {'memory_scope', 'promotion_scope'})


def _entry_matches_scope(entry: dict[str, Any], scope_filters: dict[str, str]) -> bool:
    if not scope_filters:
        return True
    for field_name, expected in scope_filters.items():
        if _entry_scope_value(entry, field_name) != expected:
            return False
    return True


def _index_missing_scope_fields(index: dict[str, Any], scope_filters: dict[str, str]) -> bool:
    if not scope_filters:
        return False
    entries = index.get('entries') if isinstance(index.get('entries'), list) else []
    if not entries:
        return False
    first = entries[0] if isinstance(entries[0], dict) else {}
    for field_name in scope_filters:
        if field_name not in first:
            return True
    return int(index.get('schema_version') or 1) < 2



def _index_stale_for_memory_files(index: dict[str, Any]) -> bool:
    try:
        files = list(ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR.glob('*.json'))
    except Exception:
        files = []
    if int(index.get('entry_count') or 0) != len(files):
        return True
    try:
        index_mtime = RETRIEVAL_INDEX_PATH.stat().st_mtime if RETRIEVAL_INDEX_PATH.exists() else 0.0
    except Exception:
        index_mtime = 0.0
    if not index_mtime and files:
        return True
    for path in files:
        try:
            if path.stat().st_mtime > index_mtime:
                return True
        except Exception:
            continue
    return False


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", str(text or '').lower()))


def _score_hashing(query: str, entry: dict[str, Any]) -> float:
    query_tokens = _tokenize(query)
    doc_tokens = set(entry.get('tokens') or [])
    if not query_tokens or not doc_tokens:
        return 0.0
    overlap = len(query_tokens & doc_tokens)
    union = len(query_tokens | doc_tokens) or 1
    jaccard = overlap / union
    title_bonus = 0.1 if any(token in _tokenize(entry.get('title') or '') for token in query_tokens) else 0.0
    return jaccard + title_bonus


@lru_cache(maxsize=2)
def _load_embedding_model(model_path: str):
    clean_path = str(model_path or '').strip()
    if not clean_path:
        return None
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception:
        return None
    return SentenceTransformer(clean_path)


def _query_embedding(query: str, settings: dict[str, Any]) -> np.ndarray | None:
    if str(settings.get('backend') or '').strip().lower() != 'sentence_transformer_local':
        return None
    model_path = str(settings.get('embedding_model_path') or '').strip()
    if not model_path:
        return None
    model = _load_embedding_model(model_path)
    if model is None:
        return None
    try:
        return np.asarray(model.encode([query], normalize_embeddings=True))[0]
    except Exception:
        return None


def _score_embedding(query_vector: np.ndarray | None, entry_index: int, index: dict[str, Any], settings: dict[str, Any]) -> float | None:
    if query_vector is None:
        return None
    if str(settings.get('backend') or '').strip().lower() != 'sentence_transformer_local':
        return None
    embeddings = index.get('embeddings') if isinstance(index.get('embeddings'), list) else None
    if not embeddings or entry_index >= len(embeddings):
        return None
    try:
        doc_vec = np.asarray(embeddings[entry_index], dtype=float)
    except Exception:
        return None
    if doc_vec.size == 0:
        return None
    return float(np.dot(query_vector, doc_vec))


def _compact_result_row(row: dict[str, Any]) -> dict[str, Any]:
    extra = row.get('extra') if isinstance(row.get('extra'), dict) else {}
    compact = {
        'id': str(row.get('id') or '').strip(),
        'memory_type': str(row.get('memory_type') or '').strip(),
        'entity_id': str(row.get('entity_id') or '').strip(),
        'project_id': str(row.get('project_id') or '').strip() or str(extra.get('project_id') or '').strip(),
        'source_ref': str(row.get('source_ref') or '').strip(),
        'title': str(row.get('title') or '').strip(),
        'document': str(row.get('document') or '').strip(),
        'summary': str(row.get('scene_ready_text') or row.get('canonical_text') or row.get('document') or '').strip()[:320],
        'salience': float(row.get('salience') or 0.0),
        'tags': list(row.get('tags') or []),
        'score': float(row.get('score') or 0.0),
        'rerank_overlap': int(row.get('rerank_overlap') or 0),
        'cross_encoder_score': float(row.get('cross_encoder_score') or 0.0),
        'rerank_backend': str(row.get('rerank_backend') or '').strip(),
    }
    for field_name in SCOPE_FILTER_FIELDS:
        compact[field_name] = _entry_scope_value(row, field_name)
    return compact


def retrieval_status() -> dict[str, Any]:
    settings = load_retrieval_settings()
    backend = str(settings.get('backend') or 'hashing_local').strip().lower()
    embedding_model_path = str(settings.get('embedding_model_path') or '').strip()
    reranker_backend = str(settings.get('reranker_backend') or 'token_overlap').strip().lower()
    reranker_model_path = str(settings.get('reranker_model_path') or '').strip()
    dep_status = {'numpy': True}
    try:
        import sentence_transformers  # type: ignore
        dep_status['sentence_transformers'] = True
    except Exception:
        dep_status['sentence_transformers'] = False
    try:
        import transformers  # type: ignore
        dep_status['transformers'] = True
    except Exception:
        dep_status['transformers'] = False
    index = load_memory_index()
    embedding_exists = bool(embedding_model_path and Path(embedding_model_path).exists())
    reranker_exists = bool(reranker_model_path and Path(reranker_model_path).exists())
    return {
        'settings': settings,
        'backend_ready': backend == 'hashing_local' or (backend == 'sentence_transformer_local' and dep_status['sentence_transformers'] and embedding_exists),
        'reranker_ready': reranker_backend == 'token_overlap' or (reranker_backend == 'cross_encoder_local' and dep_status['sentence_transformers'] and reranker_exists),
        'dependencies': dep_status,
        'paths': {
            'embedding_model_path': embedding_model_path,
            'embedding_model_exists': embedding_exists,
            'reranker_model_path': reranker_model_path,
            'reranker_model_exists': reranker_exists,
        },
        'index': {
            'entry_count': int(index.get('entry_count') or 0),
            'embedding_status': str(index.get('embedding_status') or ''),
            'last_indexed_at': str(settings.get('last_indexed_at') or '').strip(),
            'schema_version': int(index.get('schema_version') or 1),
        },
        'available_backends': ['hashing_local', 'sentence_transformer_local'],
        'available_rerankers': ['token_overlap', 'cross_encoder_local'],
    }


def update_retrieval_settings(*, backend: str = '', embedding_model_path: str = '', reranker_backend: str = '', reranker_model_path: str = '', top_k: int | None = None, preview_k: int | None = None) -> dict[str, Any]:
    current = load_retrieval_settings()
    if backend:
        current['backend'] = str(backend).strip().lower()
    if embedding_model_path is not None:
        current['embedding_model_path'] = str(embedding_model_path or '').strip()
    if reranker_backend:
        current['reranker_backend'] = str(reranker_backend).strip().lower()
    if reranker_model_path is not None:
        current['reranker_model_path'] = str(reranker_model_path or '').strip()
    if top_k is not None:
        current['top_k'] = max(1, min(50, int(top_k)))
    if preview_k is not None:
        current['preview_k'] = max(4, min(100, int(preview_k)))
    return save_retrieval_settings(current)


def query_memory(
    *,
    query: str,
    project_id: str = '',
    entity_id: str = '',
    memory_type: str = '',
    top_k: int | None = None,
    preview_k: int | None = None,
    source_snapshot_id: str = '',
    canon_snapshot_id: str = '',
    sandbox_id: str = '',
    storyline_id: str = '',
    session_id: str = '',
    checkpoint_id: str = '',
    branch_id: str = '',
    memory_scope: str = '',
    promotion_scope: str = '',
) -> dict[str, Any]:
    clean_query = str(query or '').strip()
    if not clean_query:
        raise ValueError('Query is required.')
    settings = load_retrieval_settings()
    scope_filters = _scope_filters(
        source_snapshot_id=source_snapshot_id,
        canon_snapshot_id=canon_snapshot_id,
        sandbox_id=sandbox_id,
        storyline_id=storyline_id,
        session_id=session_id,
        checkpoint_id=checkpoint_id,
        branch_id=branch_id,
        memory_scope=memory_scope,
        promotion_scope=promotion_scope,
    )
    index = load_memory_index()
    if _index_missing_scope_fields(index, scope_filters) or _index_stale_for_memory_files(index):
        index = rebuild_memory_index(settings)
    entries = index.get('entries') if isinstance(index.get('entries'), list) else []
    query_vector = _query_embedding(clean_query, settings)
    rows: list[dict[str, Any]] = []
    for idx, entry in enumerate(entries):
        if project_id and str(entry.get('project_id') or '').strip() != str(project_id or '').strip():
            continue
        if entity_id and str(entry.get('entity_id') or '').strip() != str(entity_id or '').strip():
            continue
        if memory_type and str(entry.get('memory_type') or '').strip() != str(memory_type or '').strip():
            continue
        if not _entry_matches_scope(entry, scope_filters):
            continue
        score = _score_embedding(query_vector, idx, index, settings)
        score_source = 'embedding' if score is not None else 'hashing'
        if score is None:
            score = _score_hashing(clean_query, entry)
        if score <= 0:
            continue
        row = dict(entry)
        row['score'] = round(float(score), 6)
        row['score_source'] = score_source
        rows.append(row)
    rows.sort(key=lambda item: float(item.get('score') or 0.0), reverse=True)
    final_top_k = max(1, top_k or int(settings.get('top_k') or 8))
    preview_limit = max(final_top_k, preview_k or int(settings.get('preview_k') or 16))
    candidate_rows = rows[:preview_limit]
    reranked_rows = rerank_results(clean_query, candidate_rows, settings)
    final_rows = reranked_rows[:final_top_k]
    return {
        'query': clean_query,
        'backend': str(settings.get('backend') or 'hashing_local').strip().lower(),
        'reranker_backend': str(settings.get('reranker_backend') or 'token_overlap').strip().lower(),
        'result_count': len(final_rows),
        'candidate_count': len(candidate_rows),
        'results': [_compact_result_row(row) for row in final_rows],
        'candidates': [_compact_result_row(row) for row in candidate_rows],
        'reranked_candidates': [_compact_result_row(row) for row in reranked_rows],
        'diagnostics': {
            'query_vector_used': query_vector is not None,
            'index_embedding_status': str(index.get('embedding_status') or ''),
            'index_schema_version': int(index.get('schema_version') or 1),
            'entry_count': int(index.get('entry_count') or 0),
            'preview_k': preview_limit,
            'top_k': final_top_k,
            'project_id': str(project_id or '').strip(),
            'entity_id': str(entity_id or '').strip(),
            'memory_type': str(memory_type or '').strip(),
            'scope_filters': dict(scope_filters),
        },
    }


def rebuild_retrieval(settings_updates: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = load_retrieval_settings()
    if isinstance(settings_updates, dict):
        settings.update(settings_updates)
        settings = save_retrieval_settings(settings)
    index = rebuild_memory_index(settings)
    return {'settings': settings, 'index': index}
