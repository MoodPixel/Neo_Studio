from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from ..library_constants import DEFAULT_ROOT
from ..logging_utils import get_logger
from .sqlite_store import get_memory_meta_value, set_memory_meta_value, sqlite_conn

logger = get_logger(__name__)

ASSISTANT_COLLECTION = 'assistant_memory'
ROLEPLAY_COLLECTION = 'roleplay_memory'
ROLEPLAY_V2_COLLECTION = 'roleplay_v2_memory'
CHROMA_ROOT = DEFAULT_ROOT / 'memory' / 'chroma'
EMBEDDING_BACKEND_DEFAULT = 'hashing_local'
EMBEDDING_BACKEND_META_KEY = 'embedding_backend'

try:
    import chromadb  # type: ignore
    CHROMA_AVAILABLE = True
    _CHROMA_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - depends on environment
    chromadb = None  # type: ignore
    CHROMA_AVAILABLE = False
    _CHROMA_IMPORT_ERROR = exc

_CLIENT = None
_COLLECTIONS: dict[str, Any] = {}
_WARNED_UNAVAILABLE = False


class HashingEmbeddingFunction:
    """Deterministic offline embedding.

    This avoids first-run model downloads and keeps Neo usable offline.
    It is not semantically strong, but it gives us a stable local vector layer
    until a better embedding backend is added later.
    """

    def __init__(self, dims: int = 96):
        self.dims = max(32, int(dims or 96))

    def name(self) -> str:
        return f'hashing_offline_{self.dims}d'

    def __call__(self, input: Any) -> list[list[float]]:
        # Keep this exact signature for Chroma >= 0.4.16 validation.
        # Chroma checks that __call__ exposes only (self, input).
        documents = input if isinstance(input, list) else [str(input or '')]
        return [self._embed(str(doc or '')) for doc in documents]

    def embed_documents(self, input: Any) -> list[list[float]]:
        # Chroma calls this with the modern keyword name input.
        # Keep the signature strict to avoid newer Chroma interface validation failures.
        return self(input)

    def embed_query(self, input: Any) -> list[list[float]]:
        # Chroma may call embed_query(input=[...]) internally. It expects a batch
        # of embeddings, not a single flat vector, otherwise the Rust query layer
        # raises: float object cannot be converted to Sequence.
        return self(input)

    def _embed(self, text: str) -> list[float]:
        tokens = re.findall(r"[\w']+", str(text or '').lower())
        vec = [0.0] * self.dims
        if not tokens:
            return vec
        for token in tokens:
            digest = hashlib.sha256(token.encode('utf-8')).digest()
            bucket = int.from_bytes(digest[:4], 'big') % self.dims
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            weight = 1.0 + ((digest[5] % 7) / 10.0)
            vec[bucket] += sign * weight
        norm = math.sqrt(sum(value * value for value in vec)) or 1.0
        return [value / norm for value in vec]


_HASHING_EMBEDDING_FUNCTION = HashingEmbeddingFunction()


def _warn_unavailable_once() -> None:
    global _WARNED_UNAVAILABLE
    if _WARNED_UNAVAILABLE:
        return
    _WARNED_UNAVAILABLE = True
    logger.warning('Chroma is not available in this environment. Memory chunks will stay in SQLite only. Import error: %s', _CHROMA_IMPORT_ERROR)


def list_embedding_backends() -> list[dict[str, Any]]:
    return [
        {
            'key': 'hashing_local',
            'label': 'Hashing local',
            'available': True,
            'needs_download': False,
            'description': 'Stable fully local hashing-based embeddings. No model downloads. Best for long-term reliability.',
        },
        {
            'key': 'chroma_default',
            'label': 'Chroma default',
            'available': bool(CHROMA_AVAILABLE),
            'needs_download': True,
            'description': 'Lets Chroma use its default embedding stack. Better semantic quality, but first use may download model/tokenizer assets depending on the environment.',
        },
    ]


def _backend_map() -> dict[str, dict[str, Any]]:
    return {row['key']: row for row in list_embedding_backends()}


def get_active_embedding_backend() -> str:
    clean = str(get_memory_meta_value(EMBEDDING_BACKEND_META_KEY, EMBEDDING_BACKEND_DEFAULT) or EMBEDDING_BACKEND_DEFAULT).strip() or EMBEDDING_BACKEND_DEFAULT
    backend = _backend_map().get(clean)
    if not backend or not backend.get('available'):
        clean = EMBEDDING_BACKEND_DEFAULT
        set_memory_meta_value(EMBEDDING_BACKEND_META_KEY, clean)
    return clean


def set_active_embedding_backend(backend_key: str) -> dict[str, Any]:
    global _COLLECTIONS
    clean = str(backend_key or '').strip() or EMBEDDING_BACKEND_DEFAULT
    backend = _backend_map().get(clean)
    if not backend:
        raise ValueError('Unknown embedding backend.')
    if not backend.get('available'):
        raise ValueError(f'Embedding backend "{clean}" is not available in this environment.')
    set_memory_meta_value(EMBEDDING_BACKEND_META_KEY, clean)
    _COLLECTIONS = {}
    return backend


def _embedding_function_for_backend(backend_key: str):
    if backend_key == 'hashing_local':
        return _HASHING_EMBEDDING_FUNCTION
    return None


def _resolved_collection_name(base_name: str, backend_key: str | None = None) -> str:
    clean_base = str(base_name or '').strip()
    clean_backend = str(backend_key or get_active_embedding_backend()).strip() or EMBEDDING_BACKEND_DEFAULT
    return f'{clean_base}__{clean_backend}'


def _client():
    global _CLIENT
    if not CHROMA_AVAILABLE:
        _warn_unavailable_once()
        return None
    if _CLIENT is None:
        CHROMA_ROOT.mkdir(parents=True, exist_ok=True)
        _CLIENT = chromadb.PersistentClient(path=str(CHROMA_ROOT))
    return _CLIENT


def get_embedding_backend_status() -> dict[str, Any]:
    active_backend = get_active_embedding_backend()
    backend = _backend_map().get(active_backend, {})
    chroma_available = bool(CHROMA_AVAILABLE)
    resolved_collections = {
        'assistant': _resolved_collection_name(ASSISTANT_COLLECTION, active_backend),
        'roleplay': _resolved_collection_name(ROLEPLAY_COLLECTION, active_backend),
        'roleplay_v2': _resolved_collection_name(ROLEPLAY_V2_COLLECTION, active_backend),
    }

    if not chroma_available:
        state = 'sqlite_only'
        tone = 'warning'
        reason = 'chroma_unavailable'
        storage_mode = 'sqlite_only'
        storage_mode_label = 'SQLite only'
        summary = 'Chroma is unavailable in this environment, so memory stays durable in SQLite only.'
        ui_message = 'Saved memory still persists locally, but mirror sync and semantic lookup stay offline until Chroma is available again.'
    elif active_backend == 'hashing_local':
        state = 'ready'
        tone = 'ok'
        reason = ''
        storage_mode = 'sqlite_and_chroma'
        storage_mode_label = 'SQLite + Chroma mirror'
        summary = 'Hashing local keeps memory fully local and stable while the Chroma mirror stays available for semantic lookup.'
        ui_message = 'Stable local mode: no external embedding download is required. Semantic lookup works through the local hashing mirror.'
    else:
        state = 'ready'
        tone = 'ok'
        reason = ''
        storage_mode = 'sqlite_and_chroma'
        storage_mode_label = 'SQLite + Chroma mirror'
        summary = 'Chroma default is active, so semantic lookup can use the Chroma mirror with the default embedding stack.'
        ui_message = 'Semantic lookup is available. Depending on the environment, first use may download embedding assets.'

    downloads_note = 'No external model downloads.' if active_backend == 'hashing_local' else 'May download model assets on first semantic use.'

    return {
        'active_backend': active_backend,
        'active_backend_label': str(backend.get('label') or active_backend),
        'backends': list_embedding_backends(),
        'chroma_available': chroma_available,
        'state': state,
        'tone': tone,
        'reason': reason,
        'storage_mode': storage_mode,
        'storage_mode_label': storage_mode_label,
        'mirror_available': chroma_available,
        'semantic_search_available': chroma_available,
        'summary': summary,
        'ui_message': ui_message,
        'downloads_note': downloads_note,
        'resolved_collections': resolved_collections,
    }


def ensure_chroma_foundation() -> bool:
    client = _client()
    if client is None:
        return False
    get_collection(ASSISTANT_COLLECTION)
    get_collection(ROLEPLAY_COLLECTION)
    get_collection(ROLEPLAY_V2_COLLECTION)
    return True


def get_collection(name: str):
    backend_key = get_active_embedding_backend()
    resolved_name = _resolved_collection_name(name, backend_key)
    if resolved_name in _COLLECTIONS:
        return _COLLECTIONS[resolved_name]
    client = _client()
    if client is None:
        return None
    embedding_function = _embedding_function_for_backend(backend_key)
    if embedding_function is not None:
        collection = client.get_or_create_collection(name=resolved_name, embedding_function=embedding_function)
    else:
        collection = client.get_or_create_collection(name=resolved_name)
    _COLLECTIONS[resolved_name] = collection
    return collection


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if isinstance(value, (str, int, float, bool)):
            out[str(key)] = value
        elif value is None:
            out[str(key)] = ''
        else:
            out[str(key)] = str(value)
    out.setdefault('embedding_backend', get_active_embedding_backend())
    return out


def upsert_memory_chunks(collection_name: str, chunks: list[dict[str, Any]]) -> bool:
    if not chunks:
        return True
    collection = get_collection(collection_name)
    if collection is None:
        return False
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    for item in chunks:
        chunk_id = str(item.get('id') or '').strip()
        document = str(item.get('document') or '').strip()
        if not chunk_id or not document:
            continue
        ids.append(chunk_id)
        documents.append(document)
        metadatas.append(_sanitize_metadata(item.get('metadata') if isinstance(item.get('metadata'), dict) else {}))
    if not ids:
        return True
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    return True


def query_memory(collection_name: str, *, query_text: str, n_results: int = 12) -> list[dict[str, Any]]:
    clean_query = str(query_text or '').strip()
    if not clean_query:
        return []
    collection = get_collection(collection_name)
    if collection is None:
        return []
    try:
        response = collection.query(
                query_embeddings=[_HASHING_EMBEDDING_FUNCTION._embed(clean_query)],
                n_results=max(1, int(n_results or 12)),
                include=['documents', 'metadatas', 'distances'],
            ) if get_active_embedding_backend() == 'hashing_local' else collection.query(
                query_texts=[clean_query],
                n_results=max(1, int(n_results or 12)),
                include=['documents', 'metadatas', 'distances'],
            )
    except Exception:
        logger.exception('Chroma query failed for collection %s', collection_name)
        return []
    ids = (response.get('ids') or [[]])[0] if isinstance(response, dict) else []
    documents = (response.get('documents') or [[]])[0] if isinstance(response, dict) else []
    metadatas = (response.get('metadatas') or [[]])[0] if isinstance(response, dict) else []
    distances = (response.get('distances') or [[]])[0] if isinstance(response, dict) else []
    out: list[dict[str, Any]] = []
    for idx, chunk_id in enumerate(ids or []):
        meta = metadatas[idx] if idx < len(metadatas or []) and isinstance(metadatas[idx], dict) else {}
        meta = dict(meta)
        meta.setdefault('embedding_backend', get_active_embedding_backend())
        out.append({
            'id': str(chunk_id or '').strip(),
            'document': str(documents[idx] or '').strip() if idx < len(documents or []) else '',
            'metadata': meta,
            'distance': float(distances[idx]) if idx < len(distances or []) and distances[idx] is not None else None,
            'rank': idx,
            'source': 'chroma',
        })
    return out


def delete_memory_chunks_for_entity(collection_name: str, *, entity_id: str) -> bool:
    collection = get_collection(collection_name)
    if collection is None:
        return False
    clean_id = str(entity_id or '').strip()
    if not clean_id:
        return True
    collection.delete(where={'entity_id': clean_id})
    return True



def delete_memory_chunks_for_scope(collection_name: str, *, entity_id: str = '', builder_record_id: str = '', canon_id: str = '', source_ref: str = '') -> bool:
    """Delete Chroma mirror rows for a compile scope before re-indexing.

    Chroma upsert does not remove old ids, and compile ids can change when text
    changes. Deleting by metadata scope prevents stale compiled facts from being
    retrieved after a recompile.
    """
    collection = get_collection(collection_name)
    if collection is None:
        return False
    deleted_any = False
    for key, value in (
        ('builder_record_id', builder_record_id),
        ('canon_id', canon_id),
        ('source_ref', source_ref),
        ('entity_id', entity_id),
    ):
        clean = str(value or '').strip()
        if not clean:
            continue
        try:
            collection.delete(where={key: clean})
            deleted_any = True
        except Exception:
            logger.exception('Chroma scoped delete failed for %s=%s in %s', key, clean, collection_name)
    return True if deleted_any else True


def delete_memory_chunk_ids(collection_name: str, chunk_ids: list[str]) -> bool:
    collection = get_collection(collection_name)
    if collection is None:
        return False
    ids = [str(item or '').strip() for item in (chunk_ids or []) if str(item or '').strip()]
    if not ids:
        return True
    collection.delete(ids=ids)
    return True


def reindex_active_backend_from_sqlite(*, lane: str = '') -> dict[str, Any]:
    if _client() is None:
        return {'ok': False, 'indexed': 0, 'reason': 'chroma_unavailable', 'active_backend': get_active_embedding_backend()}
    clean_lane = str(lane or '').strip().lower()
    clauses = ['is_deleted=0', 'is_suppressed=0']
    params: list[Any] = []
    if clean_lane:
        clauses.append('lane=?')
        params.append(clean_lane)
    sql = f'''
        SELECT chunk_id, lane, document, metadata_json
        FROM memory_chunks
        WHERE {' AND '.join(clauses)}
        ORDER BY updated_at DESC, importance DESC, created_at DESC
    '''
    grouped: dict[str, list[dict[str, Any]]] = {'assistant': [], 'roleplay': []}
    with sqlite_conn() as conn:
        for row in conn.execute(sql, tuple(params)):
            lane_key = str(row['lane'] or '').strip().lower()
            if lane_key not in grouped:
                continue
            try:
                metadata = json.loads(row['metadata_json'] or '{}') if row['metadata_json'] else {}
            except Exception:
                metadata = {}
            metadata = metadata if isinstance(metadata, dict) else {}
            grouped[lane_key].append({
                'id': str(row['chunk_id'] or '').strip(),
                'document': str(row['document'] or '').strip(),
                'metadata': metadata,
            })
    indexed = 0
    per_lane: dict[str, int] = {}
    if grouped['assistant']:
        upsert_memory_chunks(ASSISTANT_COLLECTION, grouped['assistant'])
        per_lane['assistant'] = len(grouped['assistant'])
        indexed += len(grouped['assistant'])
    if grouped['roleplay']:
        upsert_memory_chunks(ROLEPLAY_COLLECTION, grouped['roleplay'])
        per_lane['roleplay'] = len(grouped['roleplay'])
        indexed += len(grouped['roleplay'])
    return {'ok': True, 'indexed': indexed, 'per_lane': per_lane, 'active_backend': get_active_embedding_backend()}
