from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from ..logging_utils import get_logger
from .sqlite_store import ensure_memory_foundation, get_memory_meta_value, set_memory_meta_value

logger = get_logger(__name__)

EMBEDDING_BACKEND_HASHING = 'hashing_local'
EMBEDDING_BACKEND_CHROMA_DEFAULT = 'chroma_default'
EMBEDDING_BACKEND_SENTENCE_TRANSFORMER = 'sentence_transformer_local'

RERANKER_BACKEND_LOCAL_HYBRID = 'local_hybrid'
RERANKER_BACKEND_CROSS_ENCODER = 'cross_encoder_local'

EMBEDDING_MODEL_PATH_META_KEY = 'assistant_embedding_model_path'
RERANKER_BACKEND_META_KEY = 'assistant_reranker_backend'
RERANKER_MODEL_PATH_META_KEY = 'assistant_reranker_model_path'
EMBEDDING_DEVICE_META_KEY = 'assistant_embedding_device'
RERANKER_DEVICE_META_KEY = 'assistant_reranker_device'


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _dep_status() -> dict[str, bool]:
    status: dict[str, bool] = {}
    try:
        import sentence_transformers  # type: ignore  # noqa: F401
        status['sentence_transformers'] = True
    except Exception:
        status['sentence_transformers'] = False
    try:
        import torch  # type: ignore  # noqa: F401
        status['torch'] = True
    except Exception:
        status['torch'] = False
    return status


def get_assistant_model_settings() -> dict[str, Any]:
    ensure_memory_foundation()
    return {
        'embedding_model_path': _clean(get_memory_meta_value(EMBEDDING_MODEL_PATH_META_KEY, '')),
        'embedding_device': _clean(get_memory_meta_value(EMBEDDING_DEVICE_META_KEY, 'auto')) or 'auto',
        'reranker_backend': _clean(get_memory_meta_value(RERANKER_BACKEND_META_KEY, RERANKER_BACKEND_LOCAL_HYBRID)) or RERANKER_BACKEND_LOCAL_HYBRID,
        'reranker_model_path': _clean(get_memory_meta_value(RERANKER_MODEL_PATH_META_KEY, '')),
        'reranker_device': _clean(get_memory_meta_value(RERANKER_DEVICE_META_KEY, 'auto')) or 'auto',
    }


def update_assistant_model_settings(*, embedding_model_path: str | None = None, embedding_device: str | None = None, reranker_backend: str | None = None, reranker_model_path: str | None = None, reranker_device: str | None = None) -> dict[str, Any]:
    ensure_memory_foundation()
    if embedding_model_path is not None:
        set_memory_meta_value(EMBEDDING_MODEL_PATH_META_KEY, _clean(embedding_model_path))
    if embedding_device is not None:
        device = _clean(embedding_device).lower() or 'auto'
        if device not in {'auto', 'cpu', 'cuda'}:
            raise ValueError('Embedding device must be auto, cpu, or cuda.')
        set_memory_meta_value(EMBEDDING_DEVICE_META_KEY, device)
    if reranker_backend is not None:
        backend = _clean(reranker_backend).lower() or RERANKER_BACKEND_LOCAL_HYBRID
        if backend not in {RERANKER_BACKEND_LOCAL_HYBRID, RERANKER_BACKEND_CROSS_ENCODER}:
            raise ValueError('Unknown reranker backend.')
        set_memory_meta_value(RERANKER_BACKEND_META_KEY, backend)
    if reranker_model_path is not None:
        set_memory_meta_value(RERANKER_MODEL_PATH_META_KEY, _clean(reranker_model_path))
    if reranker_device is not None:
        device = _clean(reranker_device).lower() or 'auto'
        if device not in {'auto', 'cpu', 'cuda'}:
            raise ValueError('Reranker device must be auto, cpu, or cuda.')
        set_memory_meta_value(RERANKER_DEVICE_META_KEY, device)
    clear_model_caches()
    return get_assistant_model_status()


def _device_arg(device: str) -> dict[str, str]:
    clean = _clean(device).lower()
    return {} if clean in {'', 'auto'} else {'device': clean}


@lru_cache(maxsize=2)
def _load_sentence_transformer(model_path: str, device: str = 'auto'):
    clean_path = _clean(model_path)
    if not clean_path:
        return None
    path = Path(clean_path)
    if not path.exists():
        return None
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception:
        logger.warning('sentence_transformers is not installed; local embedding model is unavailable.')
        return None
    try:
        return SentenceTransformer(str(path), **_device_arg(device))
    except TypeError:
        return SentenceTransformer(str(path))
    except Exception:
        logger.exception('Could not load local embedding model from %s', path)
        return None


@lru_cache(maxsize=2)
def _load_cross_encoder(model_path: str, device: str = 'auto'):
    clean_path = _clean(model_path)
    if not clean_path:
        return None
    path = Path(clean_path)
    if not path.exists():
        return None
    try:
        from sentence_transformers import CrossEncoder  # type: ignore
    except Exception:
        logger.warning('sentence_transformers is not installed; local cross-encoder reranker is unavailable.')
        return None
    try:
        return CrossEncoder(str(path), **_device_arg(device))
    except TypeError:
        return CrossEncoder(str(path))
    except Exception:
        logger.exception('Could not load local reranker model from %s', path)
        return None


def clear_model_caches() -> None:
    _load_sentence_transformer.cache_clear()
    _load_cross_encoder.cache_clear()


class LocalSentenceTransformerEmbeddingFunction:
    """Chroma-compatible local embedding function backed by sentence-transformers."""

    def __init__(self, model_path: str, device: str = 'auto'):
        self.model_path = _clean(model_path)
        self.device = _clean(device).lower() or 'auto'

    def name(self) -> str:
        stem = Path(self.model_path).name if self.model_path else 'missing'
        return f'sentence_transformer_local_{stem}'

    def __call__(self, input: Any) -> list[list[float]]:
        docs = input if isinstance(input, list) else [str(input or '')]
        docs = [str(item or '') for item in docs]
        model = _load_sentence_transformer(self.model_path, self.device)
        if model is None:
            raise RuntimeError('Local sentence-transformer embedding model is not available.')
        vectors = model.encode(docs, normalize_embeddings=True)
        return [[float(value) for value in row] for row in vectors]

    def embed_documents(self, input: Any) -> list[list[float]]:
        return self(input)

    def embed_query(self, input: Any) -> list[list[float]]:
        return self(input)


def get_sentence_transformer_embedding_function():
    settings = get_assistant_model_settings()
    path = settings.get('embedding_model_path') or ''
    if not path:
        return None
    return LocalSentenceTransformerEmbeddingFunction(str(path), str(settings.get('embedding_device') or 'auto'))


def embed_query_with_local_model(text: str) -> list[float] | None:
    settings = get_assistant_model_settings()
    fn = get_sentence_transformer_embedding_function()
    if fn is None:
        return None
    try:
        return fn([text])[0]
    except Exception:
        logger.exception('Local embedding query failed.')
        return None


def rerank_with_cross_encoder(query_text: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    settings = get_assistant_model_settings()
    if str(settings.get('reranker_backend') or '').strip().lower() != RERANKER_BACKEND_CROSS_ENCODER:
        return None
    model = _load_cross_encoder(str(settings.get('reranker_model_path') or ''), str(settings.get('reranker_device') or 'auto'))
    if model is None:
        return None
    pairs: list[tuple[str, str]] = []
    for item in candidates:
        metadata = item.get('metadata') if isinstance(item.get('metadata'), dict) else {}
        title = str(metadata.get('title') or metadata.get('source_ref') or metadata.get('file_path') or '').strip()
        doc = str(item.get('document') or '').strip()
        pairs.append((query_text, f'{title}\n{doc}'.strip()))
    try:
        scores = model.predict(pairs)
    except Exception:
        logger.exception('Local cross-encoder rerank failed.')
        return None
    out: list[dict[str, Any]] = []
    for item, score in zip(candidates, scores):
        base = float(item.get('score') or 0.0)
        cross_score = float(score)
        diagnostics = item.get('diagnostics') if isinstance(item.get('diagnostics'), dict) else {}
        enriched = {
            **item,
            'first_pass_score': base,
            'score': base + cross_score,
            'diagnostics': {
                **diagnostics,
                'reranker': RERANKER_BACKEND_CROSS_ENCODER,
                'cross_encoder_score': cross_score,
                'rerank_score': base + cross_score,
            },
        }
        out.append(enriched)
    out.sort(key=lambda row: float(row.get('score') or 0.0), reverse=True)
    return out


def get_assistant_model_status() -> dict[str, Any]:
    settings = get_assistant_model_settings()
    deps = _dep_status()
    embedding_path = _clean(settings.get('embedding_model_path'))
    reranker_path = _clean(settings.get('reranker_model_path'))
    embedding_exists = bool(embedding_path and Path(embedding_path).exists())
    reranker_exists = bool(reranker_path and Path(reranker_path).exists())
    embedding_ready = bool(deps.get('sentence_transformers') and embedding_exists)
    reranker_ready = str(settings.get('reranker_backend') or '') == RERANKER_BACKEND_LOCAL_HYBRID or bool(deps.get('sentence_transformers') and reranker_exists)
    return {
        'settings': settings,
        'dependencies': deps,
        'paths': {
            'embedding_model_path': embedding_path,
            'embedding_model_exists': embedding_exists,
            'reranker_model_path': reranker_path,
            'reranker_model_exists': reranker_exists,
        },
        'embedding_ready': embedding_ready,
        'reranker_ready': reranker_ready,
        'available_embedding_backends': [EMBEDDING_BACKEND_HASHING, EMBEDDING_BACKEND_CHROMA_DEFAULT, EMBEDDING_BACKEND_SENTENCE_TRANSFORMER],
        'available_rerankers': [RERANKER_BACKEND_LOCAL_HYBRID, RERANKER_BACKEND_CROSS_ENCODER],
        'summary': 'Local model runtime is optional. Hashing local remains the fallback when model paths or dependencies are unavailable.',
    }
