from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np

from .roleplay_v2_foundation import ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR, ROLEPLAY_V2_ROOT
from .roleplay_v2_snapshot_store import normalize_memory_scope, normalize_promotion_scope
from .storage_io import atomic_write_json, read_json_object

RETRIEVAL_DIR = ROLEPLAY_V2_ROOT / 'retrieval'
RETRIEVAL_INDEX_PATH = RETRIEVAL_DIR / 'memory_index.json'
RETRIEVAL_SETTINGS_PATH = RETRIEVAL_DIR / 'settings.json'


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", str(text or '').lower())


def _clean(value: Any, *, lower: bool = False) -> str:
    text = str(value or '').strip()
    return text.lower() if lower else text


def default_retrieval_settings() -> dict[str, Any]:
    return {
        'schema_version': 1,
        'record_type': 'roleplay_v2_retrieval_settings',
        'backend': 'hashing_local',
        'embedding_model_path': '',
        'reranker_backend': 'token_overlap',
        'reranker_model_path': '',
        'top_k': 8,
        'preview_k': 16,
        'last_indexed_at': '',
    }


def load_retrieval_settings() -> dict[str, Any]:
    RETRIEVAL_DIR.mkdir(parents=True, exist_ok=True)
    row = read_json_object(RETRIEVAL_SETTINGS_PATH, None)
    if not isinstance(row, dict):
        row = default_retrieval_settings()
        atomic_write_json(RETRIEVAL_SETTINGS_PATH, row)
    return row


def save_retrieval_settings(settings: dict[str, Any]) -> dict[str, Any]:
    merged = default_retrieval_settings()
    merged.update(settings if isinstance(settings, dict) else {})
    RETRIEVAL_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(RETRIEVAL_SETTINGS_PATH, merged)
    return merged


def _memory_document(row: dict[str, Any]) -> str:
    parts = [
        str(row.get('title') or '').strip(),
        str(row.get('canonical_text') or '').strip(),
        str(row.get('scene_ready_text') or '').strip(),
        ' '.join([str(item).strip() for item in (row.get('tags') or []) if str(item).strip()]),
    ]
    return ' '.join([part for part in parts if part]).strip()


def _maybe_embed_documents(settings: dict[str, Any], entries: list[dict[str, Any]]) -> tuple[list[list[float]] | None, str]:
    backend = str(settings.get('backend') or 'hashing_local').strip().lower()
    if backend != 'sentence_transformer_local':
        return None, 'hashing_only'
    model_path = str(settings.get('embedding_model_path') or '').strip()
    if not model_path:
        return None, 'embedding_model_path_missing'
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception:
        return None, 'sentence_transformers_not_installed'
    model = SentenceTransformer(model_path)
    embeddings = model.encode([entry['document'] for entry in entries], normalize_embeddings=True)
    return np.asarray(embeddings).tolist(), 'sentence_transformer_local'


def rebuild_memory_index(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    RETRIEVAL_DIR.mkdir(parents=True, exist_ok=True)
    active_settings = settings if isinstance(settings, dict) else load_retrieval_settings()
    entries: list[dict[str, Any]] = []
    for path in sorted(ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR.glob('*.json')):
        row = read_json_object(path, None)
        if not isinstance(row, dict):
            continue
        extra = row.get('extra') if isinstance(row.get('extra'), dict) else {}
        document = _memory_document(row)
        tokens = _tokenize(document)
        entries.append({
            'id': _clean(row.get('id')),
            'memory_type': _clean(row.get('memory_type')),
            'entity_id': _clean(row.get('entity_id')),
            'project_id': _clean(extra.get('project_id')),
            'builder_record_id': _clean(extra.get('builder_record_id')),
            'canon_id': _clean(extra.get('canon_id')),
            'source_ref': _clean(row.get('source_ref')),
            'title': _clean(row.get('title')),
            'document': document,
            'tokens': tokens,
            'salience': float(row.get('salience') or 0.0),
            'tags': list(row.get('tags') or []),
            'source_snapshot_id': _clean(row.get('source_snapshot_id') or extra.get('source_snapshot_id')),
            'canon_snapshot_id': _clean(row.get('canon_snapshot_id') or extra.get('canon_snapshot_id')),
            'sandbox_id': _clean(row.get('sandbox_id') or extra.get('sandbox_id')),
            'storyline_id': _clean(row.get('storyline_id') or extra.get('storyline_id')),
            'session_id': _clean(row.get('session_id') or extra.get('session_id')),
            'checkpoint_id': _clean(row.get('checkpoint_id') or extra.get('checkpoint_id')),
            'branch_id': _clean(row.get('branch_id') or extra.get('branch_id')),
            'memory_scope': normalize_memory_scope(row.get('memory_scope') or extra.get('memory_scope') or 'source'),
            'promotion_scope': normalize_promotion_scope(row.get('promotion_scope') or extra.get('promotion_scope') or 'sandbox_only'),
        })
    embeddings, embedding_status = _maybe_embed_documents(active_settings, entries)
    index = {
        'schema_version': 2,
        'record_type': 'roleplay_v2_memory_index',
        'entry_count': len(entries),
        'embedding_status': embedding_status,
        'entries': entries,
        'embeddings': embeddings,
    }
    atomic_write_json(RETRIEVAL_INDEX_PATH, index)
    active_settings = dict(active_settings)
    active_settings['last_indexed_at'] = __import__('datetime').datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
    save_retrieval_settings(active_settings)
    return index


def load_memory_index() -> dict[str, Any]:
    row = read_json_object(RETRIEVAL_INDEX_PATH, None)
    if not isinstance(row, dict):
        return rebuild_memory_index()
    return row
