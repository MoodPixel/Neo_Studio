from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import hashlib
import json

from ..contracts.roleplay_v2_memory_records import build_runtime_bundle_record
from ..contracts.roleplay_v2_mode_model import normalize_mode_model
from ..contracts.roleplay_v2_records import get_entity_spec
from ..contracts.roleplay_v2_scene_state import build_scene_state
from .roleplay_v2_canon_compiler import get_canon_record
from .roleplay_v2_package_store import load_saved_record, save_record
from .roleplay_v2_memory_compiler import compile_memory_from_builder_record
from .roleplay_v2_retrieval import query_memory
from .roleplay_v2_sqlite_store import select_rp2_runtime_memory_rows, select_rp2_hybrid_runtime_memory_rows, persist_rp2_retrieval_trace, fetch_rp2_relationship_state_rows, fetch_rp2_shared_relationship_state_rows, fetch_rp2_shared_continuity_rows, fetch_rp2_retrieval_trace_rows, fetch_rp2_turn_summary_debug_rows, fetch_rp2_post_turn_memory_debug_rows, fetch_rp2_recurrence_map, persist_rp2_recurrence_rows, fetch_rp2_memory_control_map, fetch_rp2_sqlite_overview, fetch_rp2_chroma_status
from .roleplay_v2_foundation import (
    ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR,
    ROLEPLAY_V2_RELATIONSHIPS_DIR,
    ROLEPLAY_V2_RUNTIME_BUNDLES_DIR,
    ROLEPLAY_V2_SHARED_MEMORIES_DIR,
)
from .roleplay_v2_snapshot_store import load_story_snapshot, normalize_memory_scope, normalize_promotion_scope
from .storage_io import read_json_object


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _bundle_path(bundle_id: str):
    return ROLEPLAY_V2_RUNTIME_BUNDLES_DIR / f'{str(bundle_id or "").strip()}.json'



def _parse_iso(value: Any):
    text = str(value or '').strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00'))
    except Exception:
        return None



def _fingerprint_payload(value: Any) -> str:
    try:
        payload = json.dumps(value or {}, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        payload = str(value or '')
    return hashlib.sha1(payload.encode('utf-8')).hexdigest()[:12]



def _iso_newer(left: Any, right: Any) -> bool:
    left_dt = _parse_iso(left)
    right_dt = _parse_iso(right)
    if not left_dt or not right_dt:
        return False
    return left_dt > right_dt



def _load_runtime_input_row(memory_id: str) -> dict[str, Any] | None:
    clean_id = str(memory_id or '').strip()
    if not clean_id:
        return None
    for root in (ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR, ROLEPLAY_V2_SHARED_MEMORIES_DIR):
        row = read_json_object(root / f'{clean_id}.json', None)
        if isinstance(row, dict):
            return row
    return None



def _resolve_runtime_input_id(row: dict[str, Any] | None = None) -> str:
    item = row if isinstance(row, dict) else {}
    for candidate in [
        item.get('memory_id'),
        item.get('shared_memory_id'),
        item.get('memory_fragment_id'),
        item.get('source_memory_id'),
        item.get('source_row_id'),
        item.get('id'),
    ]:
        clean_id = str(candidate or '').strip()
        if clean_id and isinstance(_load_runtime_input_row(clean_id), dict):
            return clean_id
    return ''



def _runtime_bundle_freshness(row: dict[str, Any] | None = None) -> dict[str, Any]:
    bundle = row if isinstance(row, dict) else {}
    meta = bundle.get('meta') if isinstance(bundle.get('meta'), dict) else {}
    runtime_inputs = meta.get('runtime_inputs') if isinstance(meta.get('runtime_inputs'), dict) else {}
    bundle_updated_at = str(meta.get('updated_at') or meta.get('created_at') or '').strip()
    source_record_id = ''
    if str(bundle.get('source_scope') or '').strip() == 'builder_record':
        source_record_id = str(bundle.get('source_id') or '').strip()
    if not source_record_id:
        selected_entities = [str(item or '').strip() for item in (bundle.get('selected_entity_ids') or []) if str(item or '').strip()]
        source_record_id = selected_entities[0] if selected_entities else ''
    source_record = load_saved_record('entity_record', source_record_id) if source_record_id else None
    source_meta = source_record.get('meta') if isinstance(source_record, dict) and isinstance(source_record.get('meta'), dict) else {}
    source_updated_at = str(source_meta.get('updated_at') or '').strip()
    source_memory_compiled_at = str(source_meta.get('memory_compiled_at') or '').strip()
    source_fingerprint = _fingerprint_payload(source_record) if isinstance(source_record, dict) else ''
    saved_source_fingerprint = str(runtime_inputs.get('source_record_fingerprint') or '').strip()
    saved_selected_fingerprints = runtime_inputs.get('selected_input_fingerprints') if isinstance(runtime_inputs.get('selected_input_fingerprints'), dict) else {}
    reasons: list[str] = []
    latest_input_at = bundle_updated_at
    if source_updated_at and (not latest_input_at or _iso_newer(source_updated_at, latest_input_at)):
        latest_input_at = source_updated_at
    if source_memory_compiled_at and (not latest_input_at or _iso_newer(source_memory_compiled_at, latest_input_at)):
        latest_input_at = source_memory_compiled_at
    if bundle_updated_at:
        if _iso_newer(source_updated_at, bundle_updated_at):
            reasons.append('source_record_updated')
        if _iso_newer(source_memory_compiled_at, bundle_updated_at):
            reasons.append('memory_compiled_after_bundle')
    if saved_source_fingerprint and source_fingerprint and saved_source_fingerprint != source_fingerprint:
        reasons.append('source_record_changed')
    missing_inputs = 0
    updated_inputs = 0
    changed_inputs = 0
    for memory_id in [str(item or '').strip() for item in (bundle.get('selected_memory_ids') or []) if str(item or '').strip()]:
        input_row = _load_runtime_input_row(memory_id)
        if not isinstance(input_row, dict):
            missing_inputs += 1
            continue
        updated_at = str(((input_row.get('meta') or {}).get('updated_at') or '')).strip()
        if updated_at and (not latest_input_at or _iso_newer(updated_at, latest_input_at)):
            latest_input_at = updated_at
        if bundle_updated_at and _iso_newer(updated_at, bundle_updated_at):
            updated_inputs += 1
        current_fingerprint = _fingerprint_payload(input_row)
        saved_fingerprint = str(saved_selected_fingerprints.get(memory_id) or '').strip()
        if saved_fingerprint and current_fingerprint and saved_fingerprint != current_fingerprint:
            changed_inputs += 1
    if missing_inputs:
        reasons.append('selected_memory_missing')
    if updated_inputs:
        reasons.append('selected_memory_updated')
    if changed_inputs:
        reasons.append('selected_memory_changed')
    # preserve order while removing duplicates
    reasons = list(dict.fromkeys(reasons))
    status = 'needs_rebuild' if reasons else 'fresh'
    return {
        'status': status,
        'is_stale': bool(reasons),
        'stale_reasons': reasons,
        'source_record_id': source_record_id,
        'source_record_label': str((source_record or {}).get('label') or (source_record or {}).get('display_label') or source_record_id).strip(),
        'source_record_updated_at': source_updated_at,
        'source_record_memory_compiled_at': source_memory_compiled_at,
        'latest_input_at': latest_input_at,
        'missing_input_count': missing_inputs,
        'updated_input_count': updated_inputs,
        'changed_input_count': changed_inputs,
        'bundle_updated_at': bundle_updated_at,
    }


def _tokenize_runtime_query(text: str) -> set[str]:
    clean = str(text or '').strip().lower()
    if not clean:
        return set()
    raw = clean.replace('-', ' ').replace('_', ' ').replace('/', ' ').replace(':', ' ').replace(',', ' ').replace('.', ' ')
    tokens = {part for part in raw.split() if len(part) >= 2}
    stop_words = {'the', 'and', 'for', 'with', 'that', 'this', 'from', 'into', 'over', 'under', 'then', 'than', 'when', 'what', 'where', 'which', 'while', 'your', 'their', 'there', 'here', 'have', 'has', 'had', 'were', 'was', 'are', 'but', 'not', 'you'}
    return {token for token in tokens if token not in stop_words}


def _runtime_bucket_for_meta(memory_type: str) -> str:
    clean = str(memory_type or '').strip().lower()
    return {
        'semantic_fact': 'world_facts',
        'episodic_memory': 'episodic_memories',
        'canon_guard': 'canon_guards',
        'callback_anchor': 'callback_anchors',
        'thread_state': 'callback_anchors',
        'relationship_belief': 'relationship_beliefs',
        'shared_memory': 'shared_memories',
    }.get(clean, 'episodic_memories')


def _runtime_score_row(*, query_tokens: set[str] | None = None, title: str = '', summary: str = '', text: str = '', salience: float = 0.0) -> float:
    tokens = set(query_tokens or set())
    haystack = _tokenize_runtime_query(' '.join([str(title or ''), str(summary or ''), str(text or '')]))
    overlap = len(tokens & haystack)
    token_score = 0.0
    if tokens:
        token_score = min(1.0, overlap / max(len(tokens), 1))
    title_bonus = 0.0
    lower_title = str(title or '').strip().lower()
    if tokens and any(token in lower_title for token in tokens):
        title_bonus = 0.12
    text_bonus = 0.04 if str(text or '').strip() and len(str(text or '').strip()) >= 80 else 0.0
    return round((token_score * 0.72) + (float(salience or 0.0) * 0.28) + title_bonus + text_bonus, 6)


def _continuity_recovery_bias(*, query_tokens: set[str] | None = None, memory_type: str = '', title: str = '', summary: str = '', text: str = '', source_ref: str = '') -> tuple[float, list[str]]:
    tokens = set(query_tokens or set())
    joined = ' '.join([str(title or ''), str(summary or ''), str(text or ''), str(source_ref or '')]).lower()
    recovery_tags: list[str] = []
    bias = 0.0
    clean_type = str(memory_type or '').strip().lower()
    keyword_map = {
        'callback_anchor': [('callback', 0.12), ('anchor', 0.08), ('remember', 0.08), ('return', 0.08), ('promise', 0.1)],
        'thread_state': [('unresolved', 0.14), ('pending', 0.1), ('thread', 0.1), ('later', 0.08), ('owed', 0.08)],
        'relationship_belief': [('trust', 0.08), ('betray', 0.1), ('bond', 0.08), ('love', 0.08), ('hate', 0.08), ('tension', 0.1)],
        'episodic_memory': [('before', 0.05), ('again', 0.05), ('earlier', 0.06), ('last', 0.04)],
        'canon_guard': [('canon', 0.08), ('rule', 0.06), ('must', 0.04), ('cannot', 0.05)],
        'semantic_fact': [('world', 0.04), ('history', 0.04), ('kingdom', 0.04), ('city', 0.04)],
        'shared_memory': [('shared', 0.04), ('together', 0.05), ('group', 0.05)],
    }
    for keyword, amount in keyword_map.get(clean_type, []):
        if keyword in joined:
            bias += amount
            tag = keyword.replace(' ', '_')
            if tag not in recovery_tags:
                recovery_tags.append(tag)
    if clean_type == 'thread_state' or 'unresolved' in joined or 'pending' in joined:
        if 'unresolved_thread' not in recovery_tags:
            recovery_tags.append('unresolved_thread')
        bias += 0.12
    if clean_type in {'callback_anchor', 'thread_state'}:
        if 'callback_recovery' not in recovery_tags:
            recovery_tags.append('callback_recovery')
        bias += 0.06
    if clean_type == 'relationship_belief':
        if 'relationship_recovery' not in recovery_tags:
            recovery_tags.append('relationship_recovery')
        bias += 0.06
    if tokens:
        matched = [token for token in tokens if token in joined]
        if matched:
            bias += min(0.18, 0.04 * len(matched))
            if len(matched) >= 2 and 'query_overlap' not in recovery_tags:
                recovery_tags.append('query_overlap')
    if 'callback' in joined and 'unresolved' in joined and 'callback_unresolved' not in recovery_tags:
        recovery_tags.append('callback_unresolved')
    return round(min(bias, 0.42), 6), recovery_tags[:6]


def _scope_filters(*, source_snapshot_id: str = '', canon_snapshot_id: str = '', sandbox_id: str = '', storyline_id: str = '', session_id: str = '', checkpoint_id: str = '', branch_id: str = '', memory_scope: str = '', promotion_scope: str = '') -> dict[str, str]:
    raw = {
        'source_snapshot_id': str(source_snapshot_id or '').strip(),
        'canon_snapshot_id': str(canon_snapshot_id or '').strip(),
        'sandbox_id': str(sandbox_id or '').strip(),
        'storyline_id': str(storyline_id or '').strip(),
        'session_id': str(session_id or '').strip(),
        'checkpoint_id': str(checkpoint_id or '').strip(),
        'branch_id': str(branch_id or '').strip(),
        'memory_scope': normalize_memory_scope(memory_scope, 'sandbox') if str(memory_scope or '').strip() else '',
        'promotion_scope': normalize_promotion_scope(promotion_scope, 'sandbox_only') if str(promotion_scope or '').strip() else '',
    }
    return {key: value for key, value in raw.items() if value}


def _storyline_shared_scope(storyline_id: str = '') -> dict[str, str]:
    clean_storyline_id = str(storyline_id or '').strip()
    if not clean_storyline_id:
        return {}
    storyline = load_saved_record('storyline', clean_storyline_id)
    if not isinstance(storyline, dict):
        return {}
    linked_world_id = str(storyline.get('linked_world_id') or '').strip()
    linked_universe_id = str(storyline.get('linked_universe_id') or '').strip()
    out = {
        'storyline_id': clean_storyline_id,
        'linked_world_id': linked_world_id,
        'linked_universe_id': linked_universe_id,
    }
    return {key: value for key, value in out.items() if value}


def _row_scope_value(row: dict[str, Any], field_name: str) -> str:
    value = str(row.get(field_name) or '').strip()
    if not value:
        extra = row.get('extra') if isinstance(row.get('extra'), dict) else {}
        meta = row.get('meta') if isinstance(row.get('meta'), dict) else {}
        value = str(extra.get(field_name) or meta.get(field_name) or '').strip()
    if field_name == 'memory_scope' and value:
        return normalize_memory_scope(value, 'sandbox')
    if field_name == 'promotion_scope' and value:
        return normalize_promotion_scope(value, 'sandbox_only')
    return value


def _row_matches_scope(row: dict[str, Any], scope_filters: dict[str, str] | None = None) -> bool:
    filters = scope_filters if isinstance(scope_filters, dict) else {}
    for field_name, expected in filters.items():
        if _row_scope_value(row, field_name) != expected:
            return False
    return True


def _memory_rows(*, project_id: str = '', entity_id: str = '', memory_type: str = '', scope_filters: dict[str, str] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(ROLEPLAY_V2_MEMORY_FRAGMENTS_DIR.glob('*.json')):
        row = read_json_object(path, None)
        if not isinstance(row, dict):
            continue
        extra = row.get('extra') if isinstance(row.get('extra'), dict) else {}
        if project_id and str(extra.get('project_id') or '').strip() != str(project_id or '').strip():
            continue
        if entity_id and str(row.get('entity_id') or '').strip() != str(entity_id or '').strip():
            continue
        if memory_type and str(row.get('memory_type') or '').strip() != str(memory_type or '').strip():
            continue
        if not _row_matches_scope(row, scope_filters):
            continue
        rows.append(row)
    rows.sort(key=lambda item: float(item.get('salience') or 0.0), reverse=True)
    return rows


def _relationship_rows(entity_id: str, project_id: str = '', *, scope_filters: dict[str, str] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(ROLEPLAY_V2_RELATIONSHIPS_DIR.glob('*.json')):
        row = read_json_object(path, None)
        if not isinstance(row, dict):
            continue
        extra = row.get('extra') if isinstance(row.get('extra'), dict) else {}
        if project_id and str(extra.get('project_id') or '').strip() != str(project_id or '').strip():
            continue
        if entity_id and entity_id not in {str(row.get('source_entity_id') or '').strip(), str(row.get('target_entity_id') or '').strip()}:
            continue
        if not _row_matches_scope(row, scope_filters):
            continue
        rows.append(row)
    rows.sort(key=lambda item: (float(item.get('trust_level') or 0.0) + float(item.get('tension_level') or 0.0)), reverse=True)
    return rows


def _shared_rows(entity_id: str, project_id: str = '', *, scope_filters: dict[str, str] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(ROLEPLAY_V2_SHARED_MEMORIES_DIR.glob('*.json')):
        row = read_json_object(path, None)
        if not isinstance(row, dict):
            continue
        extra = row.get('extra') if isinstance(row.get('extra'), dict) else {}
        if project_id and str(extra.get('project_id') or '').strip() != str(project_id or '').strip():
            continue
        participants = {str(item or '').strip() for item in (row.get('participant_ids') or []) if str(item or '').strip()}
        if entity_id and entity_id not in participants:
            continue
        if not _row_matches_scope(row, scope_filters):
            continue
        rows.append(row)
    rows.sort(key=lambda item: float(item.get('salience') or 0.0), reverse=True)
    return rows


def _snapshot_row_text(row: dict[str, Any]) -> str:
    candidates = [
        row.get('summary'),
        row.get('text'),
        row.get('content'),
        row.get('canonical_text'),
        row.get('scene_ready_text'),
        row.get('description'),
        row.get('title'),
        row.get('label'),
        row.get('source_ref'),
    ]
    for item in candidates:
        text = str(item or '').strip()
        if text:
            return text
    return ''


def _snapshot_baseline_rows(*, source_snapshot_id: str = '', canon_snapshot_id: str = '', query: str = '', top_k: int = 8) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    query_tokens = set(str(token or '').strip() for token in str(query or '').lower().split() if str(token or '').strip())
    grouped: dict[str, list[dict[str, Any]]] = {
        'world_facts': [],
        'episodic_memories': [],
        'canon_guards': [],
        'callback_anchors': [],
        'relationship_beliefs': [],
        'shared_memories': [],
    }
    trace: dict[str, Any] = {
        'backend': 'story_snapshot_baseline',
        'source_snapshot_id': str(source_snapshot_id or '').strip(),
        'canon_snapshot_id': str(canon_snapshot_id or '').strip(),
        'candidate_count': 0,
    }

    def append_row(bucket: str, row_id: str, title: str, text: str, *, source_ref: str = '', salience: float = 0.65, memory_type: str = '', source_backend: str = 'source_snapshot', source_scope_id: str = '', canon_scope_id: str = '') -> None:
        if not bucket:
            return
        summary = str(text or '').strip()
        continuity_bias, recovery_tags = _continuity_recovery_bias(
            query_tokens=query_tokens,
            memory_type=memory_type or bucket.rstrip('s'),
            title=str(title or '').strip(),
            summary=summary,
            text=summary,
            source_ref=str(source_ref or '').strip(),
        )
        grouped.setdefault(bucket, []).append({
            'id': str(row_id or '').strip(),
            'memory_type': str(memory_type or '').strip(),
            'title': str(title or '').strip(),
            'text': summary[:600],
            'summary': summary[:360],
            'source_ref': str(source_ref or '').strip(),
            'salience': float(salience or 0.0),
            'score': round(_runtime_score_row(query_tokens=query_tokens, title=str(title or '').strip(), summary=summary[:220], text=summary[:600], salience=float(salience or 0.0)) + continuity_bias, 6),
            'continuity_bias': continuity_bias,
            'recovery_tags': recovery_tags,
            'source_backend': source_backend,
            'source_snapshot_id': str(source_scope_id or '').strip(),
            'canon_snapshot_id': str(canon_scope_id or '').strip(),
            'memory_scope': 'source',
            'promotion_scope': 'sandbox_only',
        })
        trace['candidate_count'] = int(trace.get('candidate_count') or 0) + 1

    source_snapshot = load_story_snapshot(source_snapshot_id) if str(source_snapshot_id or '').strip() else None
    if isinstance(source_snapshot, dict):
        records = source_snapshot.get('records') if isinstance(source_snapshot.get('records'), dict) else {}
        for doc in records.get('source_documents') or []:
            if not isinstance(doc, dict):
                continue
            append_row(
                'world_facts',
                str(doc.get('id') or doc.get('source_document_id') or doc.get('label') or '').strip(),
                str(doc.get('label') or doc.get('title') or 'Source document').strip(),
                _snapshot_row_text(doc),
                source_ref=str(doc.get('source_ref') or doc.get('id') or '').strip(),
                salience=0.78,
                memory_type='semantic_fact',
                source_scope_id=str(source_snapshot_id or '').strip(),
                canon_scope_id=str(canon_snapshot_id or '').strip(),
            )
        for row in records.get('source_memory_fragments') or []:
            if not isinstance(row, dict):
                continue
            memory_type_name = str(row.get('memory_type') or '').strip().lower()
            bucket = {
                'semantic_fact': 'world_facts',
                'episodic_memory': 'episodic_memories',
                'canon_guard': 'canon_guards',
                'callback_anchor': 'callback_anchors',
                'thread_state': 'callback_anchors',
                'relationship_belief': 'relationship_beliefs',
            }.get(memory_type_name)
            append_row(
                bucket or 'world_facts',
                str(row.get('id') or '').strip(),
                str(row.get('title') or row.get('source_ref') or 'Snapshot memory').strip(),
                str(row.get('title') or row.get('source_ref') or '').strip(),
                source_ref=str(row.get('source_ref') or '').strip(),
                salience=0.66,
                memory_type=memory_type_name or 'semantic_fact',
                source_scope_id=str(source_snapshot_id or '').strip(),
                canon_scope_id=str(canon_snapshot_id or '').strip(),
            )
        for entity in records.get('entities') or []:
            if not isinstance(entity, dict):
                continue
            append_row(
                'world_facts',
                str(entity.get('id') or '').strip(),
                str(entity.get('label') or entity.get('display_label') or entity.get('id') or 'Entity').strip(),
                _snapshot_row_text(entity.get('data') if isinstance(entity.get('data'), dict) else entity),
                source_ref=str(entity.get('id') or '').strip(),
                salience=0.58,
                memory_type='semantic_fact',
                source_scope_id=str(source_snapshot_id or '').strip(),
                canon_scope_id=str(canon_snapshot_id or '').strip(),
            )
    canon_snapshot = load_story_snapshot(canon_snapshot_id) if str(canon_snapshot_id or '').strip() else None
    if isinstance(canon_snapshot, dict):
        records = canon_snapshot.get('records') if isinstance(canon_snapshot.get('records'), dict) else {}
        for row in records.get('canon_records') or []:
            if not isinstance(row, dict):
                continue
            append_row(
                'canon_guards',
                str(row.get('id') or row.get('canon_id') or '').strip(),
                str(row.get('label') or row.get('title') or 'Canon record').strip(),
                _snapshot_row_text(row.get('data') if isinstance(row.get('data'), dict) else row),
                source_ref=str(row.get('scope_id') or row.get('id') or '').strip(),
                salience=0.82,
                memory_type='canon_guard',
                source_scope_id=str(source_snapshot_id or '').strip(),
                canon_scope_id=str(canon_snapshot_id or '').strip(),
            )
    for bucket_name, rows in grouped.items():
        rows.sort(key=lambda item: (float(item.get('score') or 0.0), float(item.get('salience') or 0.0)), reverse=True)
        grouped[bucket_name] = rows[:max(2, min(int(top_k or 8), 8))]
    trace['results'] = {key: list(value)[:4] for key, value in grouped.items() if value}
    return grouped, trace


RUNTIME_PACKET_BUDGETS: dict[str, int] = {
    'world_facts': 4,
    'episodic_memories': 6,
    'canon_guards': 3,
    'callback_anchors': 3,
    'relationship_beliefs': 3,
    'shared_memories': 4,
}

SOURCE_RERANK_WEIGHTS: dict[str, float] = {
    'sqlite_bridge': 1.0,
    'chroma_bridge': 0.88,
    'shared_continuity': 0.92,
    'file_index': 0.72,
    'file_store': 0.72,
}

MODE_PACKET_PROFILES: dict[str, dict[str, Any]] = {
    'roleplay': {
        'key': 'roleplay',
        'budgets': {'world_facts': 2, 'episodic_memories': 6, 'canon_guards': 2, 'callback_anchors': 4, 'relationship_beliefs': 4, 'shared_memories': 4},
        'source_weights': {'sqlite_bridge': 1.04, 'chroma_bridge': 0.9, 'shared_continuity': 0.96, 'file_index': 0.68, 'file_store': 0.7},
        'focus': 'dialogue_continuity',
        'bucket_weights': {'world_facts': 0.92, 'episodic_memories': 1.0, 'canon_guards': 0.96, 'callback_anchors': 1.16, 'relationship_beliefs': 1.14, 'shared_memories': 1.08},
    },
    'short_story': {
        'key': 'short_story',
        'budgets': {'world_facts': 3, 'episodic_memories': 5, 'canon_guards': 2, 'callback_anchors': 3, 'relationship_beliefs': 3, 'shared_memories': 3},
        'source_weights': {'sqlite_bridge': 1.0, 'chroma_bridge': 0.9, 'shared_continuity': 0.94, 'file_index': 0.72, 'file_store': 0.72},
        'focus': 'balanced_scene_prose',
        'bucket_weights': {'world_facts': 1.0, 'episodic_memories': 1.04, 'canon_guards': 0.98, 'callback_anchors': 1.04, 'relationship_beliefs': 1.02, 'shared_memories': 1.0},
    },
    'novel': {
        'key': 'novel',
        'budgets': {'world_facts': 4, 'episodic_memories': 7, 'canon_guards': 3, 'callback_anchors': 4, 'relationship_beliefs': 4, 'shared_memories': 4},
        'source_weights': {'sqlite_bridge': 1.06, 'chroma_bridge': 0.94, 'shared_continuity': 0.98, 'file_index': 0.78, 'file_store': 0.76},
        'focus': 'long_form_continuity',
        'bucket_weights': {'world_facts': 1.02, 'episodic_memories': 1.08, 'canon_guards': 1.0, 'callback_anchors': 1.08, 'relationship_beliefs': 1.12, 'shared_memories': 1.08},
    },
    'cinematic': {
        'key': 'cinematic',
        'budgets': {'world_facts': 4, 'episodic_memories': 5, 'canon_guards': 2, 'callback_anchors': 4, 'relationship_beliefs': 2, 'shared_memories': 3},
        'source_weights': {'sqlite_bridge': 0.98, 'chroma_bridge': 0.96, 'shared_continuity': 0.97, 'file_index': 0.74, 'file_store': 0.72},
        'focus': 'visual_staging_callbacks',
        'bucket_weights': {'world_facts': 1.08, 'episodic_memories': 1.0, 'canon_guards': 0.98, 'callback_anchors': 1.14, 'relationship_beliefs': 0.94, 'shared_memories': 1.0},
    },
}



def _apply_phase14_cleanup_weights(active_source_weights: dict[str, float] | None = None) -> tuple[dict[str, float], dict[str, Any]]:
    weights = dict(active_source_weights or SOURCE_RERANK_WEIGHTS)
    sqlite_overview = fetch_rp2_sqlite_overview()
    chroma_status = fetch_rp2_chroma_status()
    sqlite_ready = int(sqlite_overview.get('entity_count') or 0) > 0 and int(sqlite_overview.get('memory_fragment_count') or 0) > 0
    chroma_ready = bool(chroma_status.get('chroma_ready')) and sqlite_ready
    cleanup = {
        'sqlite_ready': sqlite_ready,
        'chroma_ready': chroma_ready,
        'legacy_file_index_downgraded': False,
        'legacy_file_store_downgraded': False,
        'notes': [],
    }
    if sqlite_ready:
        weights['file_index'] = round(float(weights.get('file_index', SOURCE_RERANK_WEIGHTS.get('file_index', 0.7))) * 0.82, 4)
        weights['file_store'] = round(float(weights.get('file_store', SOURCE_RERANK_WEIGHTS.get('file_store', 0.7))) * 0.84, 4)
        weights['sqlite_bridge'] = round(float(weights.get('sqlite_bridge', SOURCE_RERANK_WEIGHTS.get('sqlite_bridge', 1.0))) + 0.05, 4)
        cleanup['legacy_file_index_downgraded'] = True
        cleanup['legacy_file_store_downgraded'] = True
        cleanup['notes'].append('Phase 14 cleanup: SQLite backfill exists, so local file fallback is down-weighted.')
    if chroma_ready:
        weights['file_index'] = round(float(weights.get('file_index', 0.7)) * 0.78, 4)
        weights['file_store'] = round(float(weights.get('file_store', 0.7)) * 0.8, 4)
        weights['chroma_bridge'] = round(float(weights.get('chroma_bridge', SOURCE_RERANK_WEIGHTS.get('chroma_bridge', 0.9))) + 0.05, 4)
        cleanup['notes'].append('Phase 14 cleanup: Chroma mirror is ready, so semantic recall is favored over the legacy file path.')
    cleanup['sqlite_overview'] = sqlite_overview
    cleanup['chroma_status'] = {'chroma_ready': chroma_status.get('chroma_ready'), 'collection': chroma_status.get('collection')}
    cleanup['source_weights'] = dict(weights)
    return weights, cleanup


def _mode_packet_profile(mode: str) -> dict[str, Any]:
    clean_mode = str(mode or 'roleplay').strip().lower()
    profile = MODE_PACKET_PROFILES.get(clean_mode) or MODE_PACKET_PROFILES['roleplay']
    return {
        'key': str(profile.get('key') or 'roleplay').strip(),
        'focus': str(profile.get('focus') or '').strip(),
        'budgets': dict(profile.get('budgets') or RUNTIME_PACKET_BUDGETS),
        'source_weights': dict(profile.get('source_weights') or SOURCE_RERANK_WEIGHTS),
        'bucket_weights': dict(profile.get('bucket_weights') or {}),
    }


def _runtime_row_fingerprint(row: dict[str, Any]) -> str:
    row_id = str(row.get('id') or '').strip()
    if row_id:
        return row_id
    title = str(row.get('title') or '').strip().lower()
    summary = str(row.get('summary') or row.get('text') or '').strip().lower()[:160]
    source_ref = str(row.get('source_ref') or '').strip().lower()
    return '|'.join([source_ref, title, summary])


def _budget_runtime_rows(
    source_rows: list[tuple[str, dict[str, list[dict[str, Any]]]]],
    *,
    limit_map: dict[str, int] | None = None,
    selection_policy: str = 'sqlite_chroma_file_reranked_budgeted',
    source_weights: dict[str, float] | None = None,
    bucket_weights: dict[str, float] | None = None,
    recurrence_map: dict[str, dict[str, Any]] | None = None,
    control_map: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    limits = dict(limit_map or RUNTIME_PACKET_BUDGETS)
    merged: dict[str, list[dict[str, Any]]] = {key: [] for key in limits.keys()}
    trace: dict[str, Any] = {
        'selection_policy': selection_policy,
        'rerank_backend': 'source_weighted_heuristic',
        'diversity_backend': 'greedy_repetition_dampening_v1',
        'recurrence_backend': 'cooldown_counter_v1',
        'control_backend': 'author_steering_controls_v1',
        'source_weights': dict(source_weights or SOURCE_RERANK_WEIGHTS),
        'bucket_weights': dict(bucket_weights or {}),
        'selected_by_source': {name: 0 for name, _rows in source_rows},
        'dropped_duplicates': 0,
        'dropped_overflow': 0,
        'bucket_details': {},
    }
    for key, limit in limits.items():
        ranked_candidates: list[dict[str, Any]] = []
        best_by_fingerprint: dict[str, dict[str, Any]] = {}
        for source_name, rows_by_bucket in source_rows:
            active_source_weights = trace.get('source_weights') if isinstance(trace.get('source_weights'), dict) else SOURCE_RERANK_WEIGHTS
            source_weight = float(active_source_weights.get(source_name, 0.55))
            for row in list(rows_by_bucket.get(key) or []):
                fingerprint = _runtime_row_fingerprint(row)
                base_score = float(row.get('score') or 0.0)
                salience = float(row.get('salience') or 0.0)
                continuity_bias = float(row.get('continuity_bias') or 0.0)
                active_bucket_weights = trace.get('bucket_weights') if isinstance(trace.get('bucket_weights'), dict) else {}
                bucket_weight = float(active_bucket_weights.get(key, 1.0))
                rerank_score = round(((source_weight * 1.0) + (base_score * 0.68) + (salience * 0.22) + (continuity_bias * 0.44)) * bucket_weight, 6)
                clean_row = dict(row)
                clean_row.setdefault('source_backend', source_name)
                clean_row['rerank_score'] = rerank_score
                clean_row['source_weight'] = source_weight
                clean_row['bucket_weight'] = bucket_weight
                existing = best_by_fingerprint.get(fingerprint)
                if existing is not None:
                    trace['dropped_duplicates'] += 1
                    if float(existing.get('rerank_score') or 0.0) >= rerank_score:
                        continue
                best_by_fingerprint[fingerprint] = clean_row
        ranked_candidates = sorted(
            list(best_by_fingerprint.values()),
            key=lambda item: (float(item.get('rerank_score') or 0.0), float(item.get('score') or 0.0), float(item.get('salience') or 0.0)),
            reverse=True,
        )
        selected: list[dict[str, Any]] = []
        remaining = list(ranked_candidates)
        selected_source_refs: dict[str, int] = {}
        selected_titles: dict[str, int] = {}
        selected_tags: dict[str, int] = {}
        while remaining and len(selected) < limit:
            best_index = 0
            best_score = None
            best_row = None
            for idx, candidate in enumerate(remaining):
                source_ref = str(candidate.get('source_ref') or '').strip().lower()
                title_key = str(candidate.get('title') or '').strip().lower()
                tags = [str(item or '').strip().lower() for item in (candidate.get('recovery_tags') or []) if str(item or '').strip()]
                repetition_penalty = 0.0
                if source_ref:
                    repetition_penalty += 0.16 * float(selected_source_refs.get(source_ref) or 0)
                if title_key:
                    repetition_penalty += 0.10 * float(selected_titles.get(title_key) or 0)
                for tag in tags[:3]:
                    repetition_penalty += 0.08 * float(selected_tags.get(tag) or 0)
                recurrence_penalty = 0.0
                recurrence_payload = (recurrence_map or {}).get(str(candidate.get('id') or '').strip(), {}) if isinstance(recurrence_map, dict) else {}
                if recurrence_payload:
                    recurrence_penalty += 0.03 * min(int(recurrence_payload.get('selected_count') or 0), 4)
                    cooldown_until = str(recurrence_payload.get('cooldown_until') or '').strip()
                    if cooldown_until:
                        try:
                            cooldown_dt = datetime.fromisoformat(cooldown_until.replace('Z', '+00:00'))
                            if cooldown_dt > datetime.now(timezone.utc):
                                recurrence_penalty += 0.22
                                candidate['cooldown_active'] = True
                        except Exception:
                            pass
                control_payload = (control_map or {}).get(str(candidate.get('id') or '').strip(), {}) if isinstance(control_map, dict) else {}
                if control_payload and bool(control_payload.get('is_suppressed')):
                    candidate['suppressed_by_author'] = True
                    continue
                if control_payload and bool(control_payload.get('is_resolved')) and str(candidate.get('memory_type') or '').strip() in {'thread_state', 'callback_anchor'}:
                    candidate['resolved_by_author'] = True
                    continue
                control_bonus = 0.0
                control_penalty = 0.0
                if control_payload and bool(control_payload.get('is_pinned')):
                    control_bonus += 0.28
                control_cooldown = str(control_payload.get('cooldown_until') or '').strip() if isinstance(control_payload, dict) else ''
                if control_cooldown:
                    try:
                        control_dt = datetime.fromisoformat(control_cooldown.replace('Z', '+00:00'))
                        if control_dt > datetime.now(timezone.utc):
                            control_penalty += 0.32
                            candidate['control_cooldown_active'] = True
                    except Exception:
                        pass
                diversity_score = round(float(candidate.get('rerank_score') or 0.0) + control_bonus - repetition_penalty - recurrence_penalty - control_penalty, 6)
                candidate['diversity_score'] = diversity_score
                candidate['repetition_penalty'] = round(repetition_penalty, 6)
                candidate['recurrence_penalty'] = round(recurrence_penalty, 6)
                candidate['recurrence_selected_count'] = int(recurrence_payload.get('selected_count') or 0) if isinstance(recurrence_payload, dict) else 0
                candidate['control_bonus'] = round(control_bonus, 6)
                candidate['control_penalty'] = round(control_penalty, 6)
                candidate['control_state'] = {
                    'is_pinned': bool(control_payload.get('is_pinned')) if isinstance(control_payload, dict) else False,
                    'is_suppressed': bool(control_payload.get('is_suppressed')) if isinstance(control_payload, dict) else False,
                    'is_resolved': bool(control_payload.get('is_resolved')) if isinstance(control_payload, dict) else False,
                    'cooldown_until': str(control_payload.get('cooldown_until') or '').strip() if isinstance(control_payload, dict) else '',
                }
                if best_score is None or diversity_score > best_score:
                    best_score = diversity_score
                    best_index = idx
                    best_row = candidate
            chosen = remaining.pop(best_index)
            selected.append(chosen)
            source_ref = str(chosen.get('source_ref') or '').strip().lower()
            title_key = str(chosen.get('title') or '').strip().lower()
            if source_ref:
                selected_source_refs[source_ref] = int(selected_source_refs.get(source_ref) or 0) + 1
            if title_key:
                selected_titles[title_key] = int(selected_titles.get(title_key) or 0) + 1
            for tag in [str(item or '').strip().lower() for item in (chosen.get('recovery_tags') or []) if str(item or '').strip()][:3]:
                selected_tags[tag] = int(selected_tags.get(tag) or 0) + 1
        overflow = max(0, len(ranked_candidates) - len(selected))
        trace['dropped_overflow'] += overflow
        for item in selected:
            source_name = str(item.get('source_backend') or '').strip()
            trace['selected_by_source'][source_name] = int(trace['selected_by_source'].get(source_name) or 0) + 1
        merged[key] = selected
        trace['bucket_details'][key] = {
            'budget': limit,
            'candidate_count': len(ranked_candidates),
            'selected': len(selected),
            'selected_ids': [str(item.get('id') or '').strip() for item in selected if str(item.get('id') or '').strip()],
            'selected_sources': [str(item.get('source_backend') or '').strip() for item in selected],
            'top_reranked': [
                {
                    'id': str(item.get('id') or '').strip(),
                    'title': str(item.get('title') or '').strip(),
                    'source_backend': str(item.get('source_backend') or '').strip(),
                    'rerank_score': float(item.get('rerank_score') or 0.0),
                    'diversity_score': float(item.get('diversity_score') or 0.0),
                    'repetition_penalty': float(item.get('repetition_penalty') or 0.0),
                    'recurrence_penalty': float(item.get('recurrence_penalty') or 0.0),
                    'recurrence_selected_count': int(item.get('recurrence_selected_count') or 0),
                    'control_bonus': float(item.get('control_bonus') or 0.0),
                    'control_penalty': float(item.get('control_penalty') or 0.0),
                    'control_state': item.get('control_state') if isinstance(item.get('control_state'), dict) else {},
                    'score': float(item.get('score') or 0.0),
                    'salience': float(item.get('salience') or 0.0),
                    'continuity_bias': float(item.get('continuity_bias') or 0.0),
                    'bucket_weight': float(item.get('bucket_weight') or 1.0),
                    'recovery_tags': list(item.get('recovery_tags') or []),
                }
                for item in ranked_candidates[: min(8, max(limit * 2, 4))]
            ],
            'diversity_selected_tags': selected_tags,
            'diversity_selected_source_refs': selected_source_refs,
            'recurrence_hits': len([item for item in selected if int(item.get('recurrence_selected_count') or 0) > 0]),
        }
    return merged, trace

def _entity_summary(entity_id: str) -> dict[str, Any]:
    entity = load_saved_record('entity_record', entity_id) or {}
    data = entity.get('data') if isinstance(entity.get('data'), dict) else {}
    links = entity.get('links') if isinstance(entity.get('links'), dict) else {}
    contract = entity.get('contract') if isinstance(entity.get('contract'), dict) else {}
    return {
        'id': str(entity.get('id') or entity_id).strip(),
        'label': str(entity.get('label') or '').strip(),
        'kind': str(entity.get('kind') or '').strip(),
        'data': data,
        'links': links,
        'contract': contract,
        'source_refs': list(entity.get('source_refs') or []),
    }


def _canon_scope(source_scope: str, source_id: str) -> dict[str, Any] | None:
    if str(source_scope or '').strip().lower() != 'canon_record' or not str(source_id or '').strip():
        return None
    return get_canon_record(source_id)



def _closed_loop_guardrails(*, project_id: str, entity_id: str, active_mode: str, source_ref: str = '', bucket_weights: dict[str, float] | None = None) -> dict[str, Any]:
    rows_payload = fetch_rp2_turn_summary_debug_rows(project_id=project_id, entity_id=entity_id, source_ref=source_ref, limit=18)
    rows = rows_payload.get('rows') if isinstance(rows_payload.get('rows'), list) else []
    mode_totals: dict[str, int] = {}
    focus_totals: dict[str, int] = {}
    promotion_totals: dict[str, dict[str, int]] = {}
    for row in rows:
        payload = row.get('summary_payload') if isinstance(row.get('summary_payload'), dict) else {}
        mode_profile = payload.get('mode_profile') if isinstance(payload.get('mode_profile'), dict) else {}
        mode_key = str(mode_profile.get('key') or row.get('mode') or 'roleplay').strip() or 'roleplay'
        mode_totals[mode_key] = int(mode_totals.get(mode_key) or 0) + 1
        focus_label = str(mode_profile.get('focus') or '').strip()
        if focus_label:
            focus_totals[focus_label] = int(focus_totals.get(focus_label) or 0) + 1
        promotion_report = payload.get('promotion_report') if isinstance(payload.get('promotion_report'), dict) else {}
        for kind, decision in promotion_report.items():
            if not isinstance(decision, dict):
                continue
            status = str(decision.get('promotion_status') or 'unknown').strip() or 'unknown'
            bucket = promotion_totals.setdefault(str(kind).strip() or 'unknown', {})
            bucket[status] = int(bucket.get(status) or 0) + 1
    dominant_mode = max(mode_totals.items(), key=lambda item: item[1])[0] if mode_totals else ''
    active_mode_clean = str(active_mode or 'roleplay').strip().lower() or 'roleplay'
    warnings: list[str] = []
    suggestions: list[str] = []
    mode_drift_detected = bool(dominant_mode and dominant_mode != active_mode_clean and int(mode_totals.get(dominant_mode) or 0) >= 2)
    if mode_drift_detected:
        warnings.append(f"Recent writeback rows skew toward {dominant_mode} while runtime retrieval is using {active_mode_clean}.")
        suggestions.append('Consider restoring the matching output preset before continuing, or rebalance writeback/retrieval tuning for this session.')
    active_bucket_weights = dict(bucket_weights or {})
    rel_durable = int(((promotion_totals.get('relationship_belief') or {}).get('durable') or 0))
    cb_durable = int(((promotion_totals.get('callback_anchor') or {}).get('durable') or 0))
    thread_durable = int(((promotion_totals.get('thread_state') or {}).get('durable') or 0))
    episodic_durable = int(((promotion_totals.get('episodic_memory') or {}).get('durable') or 0))
    if float(active_bucket_weights.get('relationship_beliefs', 1.0)) >= 1.08 and rel_durable == 0:
        suggestions.append('Relationship retrieval is emphasized, but recent durable relationship writeback is thin. Lower retrieval emphasis or promote relationship drift more aggressively.')
    if float(active_bucket_weights.get('callback_anchors', 1.0)) >= 1.08 and (cb_durable + thread_durable) == 0:
        suggestions.append('Callback/thread recovery is emphasized, but recent durable callback carry-forward is sparse. Raise callback/thread writeback confidence or reduce callback retrieval pressure.')
    if active_mode_clean == 'novel' and episodic_durable == 0:
        suggestions.append('Novel mode is active, but recent durable episodic continuity is sparse. Consider increasing episodic promotion bias for long-form continuity.')
    return {
        'recent_turn_summary_count': len(rows),
        'active_mode': active_mode_clean,
        'dominant_writeback_mode': dominant_mode,
        'mode_totals': mode_totals,
        'focus_totals': focus_totals,
        'promotion_totals': promotion_totals,
        'mode_drift_detected': mode_drift_detected,
        'warnings': warnings,
        'suggestions': suggestions,
    }



def _session_continuity_pressure(*, project_id: str, entity_id: str, mode: str) -> dict[str, Any]:
    relationship_rows = fetch_rp2_relationship_state_rows(entity_id=entity_id, project_id=project_id, limit=10).get('rows') or []
    post_turn_rows = fetch_rp2_post_turn_memory_debug_rows(entity_id=entity_id, limit=24).get('memory_fragments') or []
    unresolved_rows = [row for row in post_turn_rows if str(row.get('memory_type') or '').strip() == 'thread_state']
    high_tension = [row for row in relationship_rows if float(row.get('tension_level') or 0.0) >= 0.45 or float(row.get('drift_score') or 0.0) >= 0.12]
    durable_unresolved = [row for row in unresolved_rows if str(row.get('promotion_status') or '').strip() in {'durable', 'continuity'}]
    budget_add: dict[str, int] = {}
    bucket_add: dict[str, float] = {}
    source_add: dict[str, float] = {}
    focus_tags: list[str] = []
    suggestions: list[str] = []
    unresolved_count = len(durable_unresolved)
    relationship_pressure_count = len(high_tension)
    if unresolved_count >= 2:
        budget_add['callback_anchors'] = 1 if unresolved_count < 4 else 2
        bucket_add['callback_anchors'] = 0.08 if unresolved_count < 4 else 0.14
        bucket_add['episodic_memories'] = 0.04
        source_add['sqlite_bridge'] = 0.02
        source_add['chroma_bridge'] = 0.02
        focus_tags.append('unresolved_thread_pressure')
    if relationship_pressure_count >= 1:
        budget_add['relationship_beliefs'] = 1
        bucket_add['relationship_beliefs'] = 0.08 if relationship_pressure_count < 3 else 0.14
        bucket_add['shared_memories'] = 0.06 if relationship_pressure_count < 3 else 0.1
        source_add['sqlite_bridge'] = max(float(source_add.get('sqlite_bridge') or 0.0), 0.03)
        focus_tags.append('relationship_pressure')
    if str(mode or '').strip().lower() == 'novel' and unresolved_count >= 1:
        bucket_add['episodic_memories'] = float(bucket_add.get('episodic_memories') or 0.0) + 0.05
        focus_tags.append('long_form_pressure')
    if unresolved_count == 0 and relationship_pressure_count == 0:
        suggestions.append('No strong unresolved-thread or relationship pressure was detected in recent continuity rows.')
    return {
        'backend': 'session_long_pressure_v1',
        'mode': str(mode or 'roleplay').strip().lower() or 'roleplay',
        'unresolved_thread_count': unresolved_count,
        'relationship_pressure_count': relationship_pressure_count,
        'budget_add': budget_add,
        'bucket_weight_add': bucket_add,
        'source_weight_add': source_add,
        'focus_tags': focus_tags,
        'suggestions': suggestions,
    }


def _top_memory_slices(*, project_id: str, entity_id: str, query: str, top_k: int, mode: str = 'roleplay', source_snapshot_id: str = '', canon_snapshot_id: str = '', sandbox_id: str = '', storyline_id: str = '', session_id: str = '', checkpoint_id: str = '', branch_id: str = '', memory_scope: str = '', promotion_scope: str = '') -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    retrieval_trace: dict[str, Any] = {}
    mode_profile = _mode_packet_profile(mode)
    active_budgets = dict(mode_profile.get('budgets') or RUNTIME_PACKET_BUDGETS)
    active_source_weights = dict(mode_profile.get('source_weights') or SOURCE_RERANK_WEIGHTS)
    active_bucket_weights = dict(mode_profile.get('bucket_weights') or {})
    active_source_weights, migration_cleanup = _apply_phase14_cleanup_weights(active_source_weights)
    story_scope = _scope_filters(
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
    session_pressure_profile = _session_continuity_pressure(project_id=project_id, entity_id=entity_id, mode=str(mode_profile.get('key') or mode or 'roleplay').strip().lower())
    for bucket_name, extra in (session_pressure_profile.get('budget_add') or {}).items():
        active_budgets[bucket_name] = max(1, int(active_budgets.get(bucket_name, 0) or 0) + int(extra or 0))
    for bucket_name, extra in (session_pressure_profile.get('bucket_weight_add') or {}).items():
        active_bucket_weights[bucket_name] = float(active_bucket_weights.get(bucket_name, 1.0) or 1.0) + float(extra or 0.0)
    for source_name, extra in (session_pressure_profile.get('source_weight_add') or {}).items():
        active_source_weights[source_name] = float(active_source_weights.get(source_name, SOURCE_RERANK_WEIGHTS.get(source_name, 0.7)) or SOURCE_RERANK_WEIGHTS.get(source_name, 0.7)) + float(extra or 0.0)
    if source_snapshot_id or canon_snapshot_id:
        active_source_weights['source_snapshot'] = max(float(active_source_weights.get('source_snapshot') or 0.96), 0.96)
    shared_scope = _storyline_shared_scope(storyline_id)
    if shared_scope:
        active_source_weights['shared_continuity'] = max(float(active_source_weights.get('shared_continuity') or 0.92), 0.92)
    recurrence_map = fetch_rp2_recurrence_map(project_id=project_id, entity_id=entity_id)
    control_map = fetch_rp2_memory_control_map(project_id=project_id, entity_id=entity_id)
    if query:
        queried = query_memory(
            query=query,
            project_id=project_id,
            entity_id=entity_id,
            top_k=max(8, top_k),
            preview_k=max(12, top_k * 2),
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
        rows = queried.get('results') if isinstance(queried.get('results'), list) else []
        retrieval_trace = {
            'backend': 'hybrid_scaffold',
            'file_index': {
                'backend': str(queried.get('backend') or '').strip(),
                'reranker_backend': str(queried.get('reranker_backend') or '').strip(),
                'candidate_count': int(queried.get('candidate_count') or 0),
                'candidates': list(queried.get('candidates') or [])[:12],
                'reranked_candidates': list(queried.get('reranked_candidates') or [])[:12],
                'results': list(queried.get('results') or [])[:8],
                'diagnostics': queried.get('diagnostics') if isinstance(queried.get('diagnostics'), dict) else {},
            },
        }
    else:
        rows = []
        rows.extend(_memory_rows(project_id=project_id, entity_id=entity_id, memory_type='semantic_fact', scope_filters=story_scope)[:4])
        rows.extend(_memory_rows(project_id=project_id, entity_id=entity_id, memory_type='episodic_memory', scope_filters=story_scope)[:6])
        rows.extend(_memory_rows(project_id=project_id, entity_id=entity_id, memory_type='canon_guard', scope_filters=story_scope)[:3])
        rows.extend(_memory_rows(project_id=project_id, entity_id=entity_id, memory_type='callback_anchor', scope_filters=story_scope)[:3])
        rows.extend(_memory_rows(project_id=project_id, entity_id=entity_id, memory_type='relationship_belief', scope_filters=story_scope)[:3])
        retrieval_trace = {'backend': 'hybrid_scaffold', 'file_index': {'backend': 'file_fallback', 'candidate_count': len(rows)}}
    grouped = {
        'world_facts': [],
        'episodic_memories': [],
        'canon_guards': [],
        'callback_anchors': [],
        'relationship_beliefs': [],
    }
    for row in rows:
        row_type = str(row.get('memory_type') or '').strip()
        compact = {
            'id': str(row.get('id') or '').strip(),
            'memory_type': row_type,
            'title': str(row.get('title') or '').strip(),
            'text': str(row.get('scene_ready_text') or row.get('canonical_text') or row.get('document') or row.get('summary') or row.get('text') or '').strip(),
            'source_ref': str(row.get('source_ref') or '').strip(),
            'salience': float(row.get('salience') or 0.0),
            'tags': list(row.get('tags') or []),
            'score': float(row.get('score') or 0.0),
            'continuity_bias': float(row.get('continuity_bias') or 0.0),
            'recovery_tags': list(row.get('recovery_tags') or []),
            'source_backend': str(row.get('source_backend') or 'file_index').strip() or 'file_index',
            'source_snapshot_id': str(row.get('source_snapshot_id') or '').strip(),
            'canon_snapshot_id': str(row.get('canon_snapshot_id') or '').strip(),
            'sandbox_id': str(row.get('sandbox_id') or '').strip(),
            'storyline_id': str(row.get('storyline_id') or '').strip(),
            'session_id': str(row.get('session_id') or '').strip(),
            'checkpoint_id': str(row.get('checkpoint_id') or '').strip(),
            'branch_id': str(row.get('branch_id') or '').strip(),
            'memory_scope': str(row.get('memory_scope') or '').strip(),
            'promotion_scope': str(row.get('promotion_scope') or '').strip(),
        }
        if row_type == 'semantic_fact':
            grouped['world_facts'].append(compact)
        elif row_type == 'canon_guard':
            grouped['canon_guards'].append(compact)
        elif row_type == 'callback_anchor':
            grouped['callback_anchors'].append(compact)
        elif row_type == 'relationship_belief':
            grouped['relationship_beliefs'].append(compact)
        else:
            grouped['episodic_memories'].append(compact)
    if not grouped['relationship_beliefs']:
        fallback_beliefs = _memory_rows(project_id=project_id, entity_id=entity_id, memory_type='relationship_belief', scope_filters=story_scope)[:3]
        for row in fallback_beliefs:
            grouped['relationship_beliefs'].append({
                'id': str(row.get('id') or '').strip(),
                'memory_type': 'relationship_belief',
                'title': str(row.get('title') or '').strip(),
                'text': str(row.get('scene_ready_text') or row.get('canonical_text') or row.get('summary') or '').strip(),
                'source_ref': str(row.get('source_ref') or '').strip(),
                'salience': float(row.get('salience') or 0.0),
                'tags': list(row.get('tags') or []),
                'score': float(row.get('score') or 0.0),
                'continuity_bias': float(row.get('continuity_bias') or 0.0),
                'recovery_tags': list(row.get('recovery_tags') or []),
                'source_backend': str(row.get('source_backend') or 'file_index').strip() or 'file_index',
                'source_snapshot_id': str(row.get('source_snapshot_id') or '').strip(),
                'canon_snapshot_id': str(row.get('canon_snapshot_id') or '').strip(),
                'sandbox_id': str(row.get('sandbox_id') or '').strip(),
                'storyline_id': str(row.get('storyline_id') or '').strip(),
                'session_id': str(row.get('session_id') or '').strip(),
                'checkpoint_id': str(row.get('checkpoint_id') or '').strip(),
                'branch_id': str(row.get('branch_id') or '').strip(),
                'memory_scope': str(row.get('memory_scope') or '').strip(),
                'promotion_scope': str(row.get('promotion_scope') or '').strip(),
            })
    hybrid_bridge = select_rp2_hybrid_runtime_memory_rows(
        project_id=project_id,
        entity_id=entity_id,
        query=str(query or '').strip(),
        limit=max(max(active_budgets.values()), max(4, top_k)),
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
    sqlite_bridge = hybrid_bridge.get('sqlite_bridge') if isinstance(hybrid_bridge.get('sqlite_bridge'), dict) else {}
    chroma_bridge = hybrid_bridge.get('chroma_bridge') if isinstance(hybrid_bridge.get('chroma_bridge'), dict) else {}
    snapshot_grouped, snapshot_trace = _snapshot_baseline_rows(source_snapshot_id=source_snapshot_id, canon_snapshot_id=canon_snapshot_id, query=query, top_k=max(4, top_k))
    shared_bridge = fetch_rp2_shared_continuity_rows(
        project_id=project_id,
        entity_id=entity_id,
        query=str(query or '').strip(),
        limit=max(max(active_budgets.values()), max(4, top_k)),
        linked_world_id=shared_scope.get('linked_world_id', ''),
        linked_universe_id=shared_scope.get('linked_universe_id', ''),
        exclude_storyline_id=storyline_id,
    ) if shared_scope else {'results': {}, 'candidate_count': 0, 'selected_count': 0, 'backend': 'shared_continuity_bridge_disabled'}
    retrieval_trace['sqlite_bridge'] = {
        'backend': str(sqlite_bridge.get('backend') or '').strip(),
        'candidate_count': int(sqlite_bridge.get('candidate_count') or 0),
        'selected_count': int(sqlite_bridge.get('selected_count') or 0),
        'scope_filters': dict(sqlite_bridge.get('scope_filters') or {}),
        'results': dict(sqlite_bridge.get('results') or {}),
    }
    retrieval_trace['chroma_bridge'] = {
        'backend': str(chroma_bridge.get('backend') or '').strip(),
        'candidate_count': int(chroma_bridge.get('candidate_count') or 0),
        'selected_count': int(chroma_bridge.get('selected_count') or 0),
        'scope_filters': dict(chroma_bridge.get('scope_filters') or {}),
        'results': dict(chroma_bridge.get('results') or {}),
    }
    retrieval_trace['shared_continuity'] = {
        'backend': str(shared_bridge.get('backend') or '').strip(),
        'candidate_count': int(shared_bridge.get('candidate_count') or 0),
        'selected_count': int(shared_bridge.get('selected_count') or 0),
        'linked_world_id': str(shared_scope.get('linked_world_id') or '').strip(),
        'linked_universe_id': str(shared_scope.get('linked_universe_id') or '').strip(),
        'exclude_storyline_id': str(storyline_id or '').strip(),
        'results': dict(shared_bridge.get('results') or {}),
    }
    retrieval_trace['source_snapshot'] = dict(snapshot_trace or {})
    merged, budget_trace = _budget_runtime_rows([
        ('sqlite_bridge', sqlite_bridge.get('results') if isinstance(sqlite_bridge.get('results'), dict) else {}),
        ('chroma_bridge', chroma_bridge.get('results') if isinstance(chroma_bridge.get('results'), dict) else {}),
        ('shared_continuity', shared_bridge.get('results') if isinstance(shared_bridge.get('results'), dict) else {}),
        ('source_snapshot', snapshot_grouped),
        ('file_index', grouped),
    ], limit_map=active_budgets, selection_policy=f"{mode_profile.get('key') or 'roleplay'}_story_scope_sqlite_chroma_shared_snapshot_file_semantic_recovery_session_pressure_diversity_recurrence_author_controls_reranked_budgeted", source_weights=active_source_weights, bucket_weights=active_bucket_weights, recurrence_map=recurrence_map, control_map=control_map)
    flattened_results: list[dict[str, Any]] = []
    for key in ['world_facts', 'episodic_memories', 'canon_guards', 'callback_anchors', 'relationship_beliefs']:
        flattened_results.extend(list(merged.get(key) or []))
    retrieval_trace['selection_policy'] = f"{mode_profile.get('key') or 'roleplay'}_story_scope_sqlite_chroma_shared_snapshot_file_semantic_recovery_session_pressure_diversity_recurrence_author_controls_reranked_budgeted"
    retrieval_trace['budget_map'] = dict(active_budgets)
    retrieval_trace['budget_trace'] = budget_trace
    retrieval_trace['hybrid_rerank_backend'] = str(budget_trace.get('rerank_backend') or 'source_weighted_heuristic').strip()
    retrieval_trace['source_weights'] = dict(budget_trace.get('source_weights') or active_source_weights)
    retrieval_trace['bucket_weights'] = dict(budget_trace.get('bucket_weights') or active_bucket_weights)
    retrieval_trace['mode_profile'] = dict(mode_profile)
    retrieval_trace['migration_cleanup'] = dict(migration_cleanup or {})
    retrieval_trace['session_pressure_profile'] = dict(session_pressure_profile)
    retrieval_trace['story_scope'] = dict(story_scope)
    retrieval_trace['source_snapshot_loaded'] = bool(source_snapshot_id or canon_snapshot_id)
    retrieval_trace['recurrence_map_size'] = len(recurrence_map) if isinstance(recurrence_map, dict) else 0
    retrieval_trace['control_map_size'] = len(control_map) if isinstance(control_map, dict) else 0
    retrieval_trace['candidate_count'] = int(((retrieval_trace.get('file_index') or {}).get('candidate_count') or 0)) + int((retrieval_trace.get('sqlite_bridge') or {}).get('candidate_count') or 0) + int((retrieval_trace.get('chroma_bridge') or {}).get('candidate_count') or 0) + int((retrieval_trace.get('shared_continuity') or {}).get('candidate_count') or 0) + int((retrieval_trace.get('source_snapshot') or {}).get('candidate_count') or 0)
    retrieval_trace['result_count'] = len(flattened_results[:max(1, top_k)])
    retrieval_trace['results'] = flattened_results[:max(1, top_k)]
    retrieval_trace['candidates'] = list(((retrieval_trace.get('file_index') or {}).get('candidates') or []))[:12]
    retrieval_trace['reranked_candidates'] = list(((retrieval_trace.get('file_index') or {}).get('reranked_candidates') or []))[:12]
    retrieval_trace['reranker_backend'] = str(((retrieval_trace.get('file_index') or {}).get('reranker_backend') or 'hybrid_scaffold')).strip()
    retrieval_trace['diagnostics'] = {
        'project_id': project_id,
        'entity_id': entity_id,
        'query': str(query or '').strip(),
        'top_k': max(1, top_k),
        'story_scope': dict(story_scope),
        'bridge_backend': str(sqlite_bridge.get('backend') or '').strip(),
        'chroma_backend': str(chroma_bridge.get('backend') or '').strip(),
        'file_backend': str(((retrieval_trace.get('file_index') or {}).get('backend') or '')).strip(),
        'hybrid_rerank_backend': str(retrieval_trace.get('hybrid_rerank_backend') or '').strip(),
        'continuity_tuning_backend': 'semantic_continuity_recovery_v2_story_scope',
        'shared_continuity_backend': str(((retrieval_trace.get('shared_continuity') or {}).get('backend') or '')).strip(),
        'session_pressure_backend': str((session_pressure_profile.get('backend') or '')).strip(),
        'diversity_backend': str((budget_trace.get('diversity_backend') or '')).strip(),
        'recurrence_map_size': retrieval_trace.get('recurrence_map_size') or 0,
        'control_map_size': retrieval_trace.get('control_map_size') or 0,
    }
    return merged, retrieval_trace

def _saturation_guardrails(*, selected_results: list[dict[str, Any]], selected_by_bucket: dict[str, int], bucket_details: dict[str, Any], recovery_tag_counts: dict[str, int], session_pressure_profile: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    suggestions: list[str] = []
    unresolved_pressure = int(session_pressure_profile.get('unresolved_thread_count') or 0)
    relationship_pressure = int(session_pressure_profile.get('relationship_pressure_count') or 0)
    callback_budget = int(((bucket_details.get('callback_anchors') or {}).get('budget') or 0))
    relationship_budget = int(((bucket_details.get('relationship_beliefs') or {}).get('budget') or 0))
    callback_selected = int(selected_by_bucket.get('callback_anchors') or 0)
    relationship_selected = int(selected_by_bucket.get('relationship_beliefs') or 0)
    shared_selected = int(selected_by_bucket.get('shared_memories') or 0)
    callback_like = [row for row in selected_results if str(row.get('memory_type') or '').strip() in {'callback_anchor', 'thread_state'}]
    callback_source_counts: dict[str, int] = {}
    for row in callback_like:
        source_key = str(row.get('source_ref') or row.get('id') or '').strip() or 'callback'
        callback_source_counts[source_key] = int(callback_source_counts.get(source_key) or 0) + 1
    dominant_callback_span = max(callback_source_counts.values()) if callback_source_counts else 0
    total_recovery_tags = sum(int(v or 0) for v in recovery_tag_counts.values())
    dominant_tag = ''
    dominant_tag_ratio = 0.0
    if recovery_tag_counts:
        dominant_tag, dominant_value = max(recovery_tag_counts.items(), key=lambda item: item[1])
        dominant_tag_ratio = float(dominant_value) / float(total_recovery_tags or 1)
    if callback_budget and callback_selected >= callback_budget and unresolved_pressure <= 1:
        warnings.append('Callback recovery is at budget ceiling even though unresolved-thread pressure is not especially high.')
        suggestions.append('Consider lowering callback weight slightly or increasing episodic/relationship share to avoid over-focusing on one hanging beat.')
    if dominant_callback_span >= 2 and callback_selected >= 3:
        warnings.append('Multiple callback slots are being consumed by the same source thread, which risks recovery saturation.')
        suggestions.append('Add callback diversity guardrails so one source thread cannot dominate the callback bucket.')
    if relationship_budget and relationship_selected >= relationship_budget and relationship_pressure == 0:
        warnings.append('Relationship recovery is saturating its budget without strong carried-forward relationship pressure.')
        suggestions.append('Reduce relationship bucket weight slightly or require stronger drift pressure before filling all relationship slots.')
    if relationship_selected >= 2 and shared_selected == 0 and relationship_pressure >= 2:
        suggestions.append('Relationship pressure is high, but shared-memory support is thin. Consider lifting shared-memory share for pressure-heavy sessions.')
    if dominant_tag and dominant_tag_ratio >= 0.66 and total_recovery_tags >= 3:
        warnings.append(f'Recovery tags are dominated by {dominant_tag}, which may cause packet monotony.')
        suggestions.append('Cap single-tag dominance or boost complementary buckets when one recovery tag starts to dominate the packet.')
    return {
        'detected': bool(warnings),
        'dominant_recovery_tag': dominant_tag,
        'dominant_recovery_tag_ratio': round(dominant_tag_ratio, 4),
        'warnings': warnings,
        'suggestions': suggestions,
    }

def _evaluate_recovery_trace(trace: dict[str, Any]) -> dict[str, Any]:
    clean_trace = trace if isinstance(trace, dict) else {}
    budget_trace = clean_trace.get('budget_trace') if isinstance(clean_trace.get('budget_trace'), dict) else {}
    bucket_details = budget_trace.get('bucket_details') if isinstance(budget_trace.get('bucket_details'), dict) else {}
    selected_results = clean_trace.get('results') if isinstance(clean_trace.get('results'), list) else []
    selected_by_bucket = {bucket: int((detail or {}).get('selected') or 0) for bucket, detail in bucket_details.items()}
    recovery_tag_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    unresolved_hits = 0
    relationship_hits = 0
    callback_hits = 0
    for row in selected_results:
        source_name = str(row.get('source_backend') or '').strip() or 'unknown'
        source_counts[source_name] = int(source_counts.get(source_name) or 0) + 1
        memory_type = str(row.get('memory_type') or '').strip()
        if memory_type == 'thread_state':
            unresolved_hits += 1
        if memory_type == 'relationship_belief':
            relationship_hits += 1
        if memory_type in {'callback_anchor', 'thread_state'}:
            callback_hits += 1
        for tag in list(row.get('recovery_tags') or []):
            clean_tag = str(tag or '').strip()
            if clean_tag:
                recovery_tag_counts[clean_tag] = int(recovery_tag_counts.get(clean_tag) or 0) + 1
    near_misses: dict[str, list[dict[str, Any]]] = {}
    for bucket, detail in bucket_details.items():
        detail = detail if isinstance(detail, dict) else {}
        selected_ids = {str(item or '').strip() for item in detail.get('selected_ids') or [] if str(item or '').strip()}
        misses = []
        for item in detail.get('top_reranked') or []:
            if not isinstance(item, dict):
                continue
            if str(item.get('id') or '').strip() in selected_ids:
                continue
            misses.append({
                'id': str(item.get('id') or '').strip(),
                'title': str(item.get('title') or '').strip(),
                'source_backend': str(item.get('source_backend') or '').strip(),
                'rerank_score': float(item.get('rerank_score') or 0.0),
                'continuity_bias': float(item.get('continuity_bias') or 0.0),
                'recovery_tags': list(item.get('recovery_tags') or []),
            })
            if len(misses) >= 3:
                break
        near_misses[bucket] = misses
    suggestions: list[str] = []
    if selected_by_bucket.get('callback_anchors', 0) == 0 and near_misses.get('callback_anchors'):
        suggestions.append('Callback recovery has near-miss candidates but nothing selected. Consider raising callback bucket weight or callback source weights.')
    if selected_by_bucket.get('relationship_beliefs', 0) == 0 and near_misses.get('relationship_beliefs'):
        suggestions.append('Relationship recovery is missing from the final packet even though strong near misses exist. Consider lifting relationship bucket weight.')
    if unresolved_hits == 0 and any('unresolved_thread' in (item.get('recovery_tags') or []) for item in near_misses.get('callback_anchors') or []):
        suggestions.append('Unresolved-thread carry-forward is not landing in the final packet. Consider raising thread/callback continuity bias.')
    if int(source_counts.get('chroma_bridge') or 0) == 0 and clean_trace.get('chroma_bridge'):
        suggestions.append('Semantic bridge is present but not winning final slots. Consider increasing Chroma source weight for this mode or query family.')
    saturation_guardrails = _saturation_guardrails(
        selected_results=selected_results,
        selected_by_bucket=selected_by_bucket,
        bucket_details=bucket_details,
        recovery_tag_counts=recovery_tag_counts,
        session_pressure_profile=clean_trace.get('session_pressure_profile') if isinstance(clean_trace.get('session_pressure_profile'), dict) else {},
    )
    suggestions.extend([item for item in (saturation_guardrails.get('suggestions') or []) if item])
    return {
        'selection_policy': str(clean_trace.get('selection_policy') or '').strip(),
        'hybrid_rerank_backend': str(clean_trace.get('hybrid_rerank_backend') or '').strip(),
        'diversity_backend': str(((clean_trace.get('budget_trace') or {}).get('diversity_backend') if isinstance(clean_trace.get('budget_trace'), dict) else '') or '').strip(),
        'continuity_tuning_backend': str(((clean_trace.get('diagnostics') or {}).get('continuity_tuning_backend') if isinstance(clean_trace.get('diagnostics'), dict) else '') or '').strip(),
        'selected_by_bucket': selected_by_bucket,
        'selected_by_source': source_counts,
        'recovery_tag_counts': recovery_tag_counts,
        'unresolved_thread_hits': unresolved_hits,
        'relationship_hits': relationship_hits,
        'callback_hits': callback_hits,
        'near_misses': near_misses,
        'suggestions': suggestions,
        'session_pressure_profile': clean_trace.get('session_pressure_profile') if isinstance(clean_trace.get('session_pressure_profile'), dict) else {},
        'saturation_guardrails': saturation_guardrails,
    }


def build_runtime_recovery_eval(*, bundle_id: str = '', trace_id: str = '', project_id: str = '', entity_id: str = '', query: str = '', mode: str = 'roleplay', top_k: int = 8) -> dict[str, Any]:
    clean_bundle_id = str(bundle_id or '').strip()
    clean_trace_id = str(trace_id or '').strip()
    clean_project_id = str(project_id or '').strip()
    clean_entity_id = str(entity_id or '').strip()
    clean_query = str(query or '').strip()
    clean_mode = str(mode or 'roleplay').strip().lower() or 'roleplay'
    trace: dict[str, Any] = {}
    source = 'live_query'
    if clean_bundle_id:
        bundle_trace = get_runtime_bundle_trace(clean_bundle_id)
        if not bundle_trace:
            raise ValueError('Runtime bundle trace not found.')
        trace = bundle_trace.get('trace') if isinstance(bundle_trace.get('trace'), dict) else {}
        trace['bundle_id'] = clean_bundle_id
        source = 'runtime_bundle'
    elif clean_trace_id:
        rows = fetch_rp2_retrieval_trace_rows(trace_id=clean_trace_id, limit=1).get('rows') or []
        if not rows:
            raise ValueError('Retrieval history entry not found.')
        row = rows[0] if isinstance(rows[0], dict) else {}
        trace = row.get('trace') if isinstance(row.get('trace'), dict) else {}
        trace['trace_id'] = clean_trace_id
        trace['bundle_id'] = str(row.get('bundle_id') or '').strip()
        source = 'retrieval_history'
    else:
        if not (clean_project_id or clean_entity_id or clean_query):
            raise ValueError('A bundle id, trace id, or live recovery query context is required.')
        _rows, trace = _top_memory_slices(project_id=clean_project_id, entity_id=clean_entity_id, query=clean_query, top_k=max(1, int(top_k or 8)), mode=clean_mode)
    evaluation = _evaluate_recovery_trace(trace)
    return {
        'ok': True,
        'source': source,
        'bundle_id': clean_bundle_id or str(trace.get('bundle_id') or '').strip(),
        'trace_id': clean_trace_id or str(trace.get('trace_id') or '').strip(),
        'project_id': clean_project_id or str(((trace.get('diagnostics') or {}).get('project_id') if isinstance(trace.get('diagnostics'), dict) else '') or '').strip(),
        'entity_id': clean_entity_id or str(((trace.get('diagnostics') or {}).get('entity_id') if isinstance(trace.get('diagnostics'), dict) else '') or '').strip(),
        'query': clean_query or str(((trace.get('diagnostics') or {}).get('query') if isinstance(trace.get('diagnostics'), dict) else '') or '').strip(),
        'mode': clean_mode or str((trace.get('mode_profile') or {}).get('key') or 'roleplay').strip(),
        'evaluation': evaluation,
        'trace': trace,
    }



def _relationship_state(entity_id: str, project_id: str = '', *, source_snapshot_id: str = '', canon_snapshot_id: str = '', sandbox_id: str = '', storyline_id: str = '', session_id: str = '', checkpoint_id: str = '', branch_id: str = '', memory_scope: str = '', promotion_scope: str = '') -> list[dict[str, Any]]:
    story_scope = _scope_filters(
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
    sqlite_rows = fetch_rp2_relationship_state_rows(
        entity_id=entity_id,
        project_id=project_id,
        limit=6,
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
    shared_scope = _storyline_shared_scope(storyline_id)
    shared_rows = fetch_rp2_shared_relationship_state_rows(
        entity_id=entity_id,
        project_id=project_id,
        limit=6,
        linked_world_id=shared_scope.get('linked_world_id', ''),
        linked_universe_id=shared_scope.get('linked_universe_id', ''),
        exclude_storyline_id=storyline_id,
    ) if shared_scope else {'rows': []}
    out: list[dict[str, Any]] = []
    for row in (sqlite_rows.get('rows') or []) if isinstance(sqlite_rows, dict) else []:
        out.append({
            'id': str(row.get('relationship_state_id') or '').strip(),
            'source_entity_id': str(row.get('source_entity_id') or '').strip(),
            'target_entity_id': str(row.get('target_entity_id') or '').strip(),
            'relationship_type': str(row.get('relationship_label') or '').strip() or 'carry_forward',
            'summary': str(row.get('summary') or '').strip(),
            'trust_level': float(row.get('trust_level') or 0.0),
            'tension_level': float(row.get('tension_level') or 0.0),
            'bond_tags': ['carry_forward'] if row.get('carry_forward') else [],
            'source_backend': 'sqlite_relationship_state',
            'drift_score': float(row.get('drift_score') or 0.0),
            'source_snapshot_id': str(row.get('source_snapshot_id') or '').strip(),
            'canon_snapshot_id': str(row.get('canon_snapshot_id') or '').strip(),
            'sandbox_id': str(row.get('sandbox_id') or '').strip(),
            'storyline_id': str(row.get('storyline_id') or '').strip(),
            'session_id': str(row.get('session_id') or '').strip(),
            'checkpoint_id': str(row.get('checkpoint_id') or '').strip(),
            'branch_id': str(row.get('branch_id') or '').strip(),
            'memory_scope': str(row.get('memory_scope') or '').strip(),
            'promotion_scope': str(row.get('promotion_scope') or '').strip(),
        })
    seen_ids = {str(item.get('id') or '').strip() for item in out if str(item.get('id') or '').strip()}
    for row in (shared_rows.get('rows') or []) if isinstance(shared_rows, dict) else []:
        shared_id = str(row.get('relationship_state_id') or '').strip()
        if shared_id and shared_id in seen_ids:
            continue
        out.append({
            'id': shared_id,
            'source_entity_id': str(row.get('source_entity_id') or '').strip(),
            'target_entity_id': str(row.get('target_entity_id') or '').strip(),
            'relationship_type': str(row.get('relationship_label') or '').strip() or 'shared_continuity',
            'summary': str(row.get('summary') or '').strip(),
            'trust_level': float(row.get('trust_level') or 0.0),
            'tension_level': float(row.get('tension_level') or 0.0),
            'bond_tags': ['shared_continuity', 'carry_forward'] if row.get('carry_forward') else ['shared_continuity'],
            'source_backend': 'shared_continuity',
            'drift_score': float(row.get('drift_score') or 0.0),
            'source_snapshot_id': str(row.get('source_snapshot_id') or '').strip(),
            'canon_snapshot_id': str(row.get('canon_snapshot_id') or '').strip(),
            'sandbox_id': str(row.get('sandbox_id') or '').strip(),
            'storyline_id': str(row.get('storyline_id') or '').strip(),
            'session_id': str(row.get('session_id') or '').strip(),
            'checkpoint_id': str(row.get('checkpoint_id') or '').strip(),
            'branch_id': str(row.get('branch_id') or '').strip(),
            'memory_scope': str(row.get('memory_scope') or '').strip(),
            'promotion_scope': str(row.get('promotion_scope') or '').strip(),
        })
        if shared_id:
            seen_ids.add(shared_id)
    if out:
        return out[:6]
    rows = _relationship_rows(entity_id, project_id, scope_filters=story_scope)[:6]
    for row in rows:
        out.append({
            'id': str(row.get('id') or '').strip(),
            'source_entity_id': str(row.get('source_entity_id') or '').strip(),
            'target_entity_id': str(row.get('target_entity_id') or '').strip(),
            'relationship_type': str(row.get('relationship_type') or '').strip(),
            'summary': str(row.get('summary') or '').strip(),
            'trust_level': float(row.get('trust_level') or 0.0),
            'tension_level': float(row.get('tension_level') or 0.0),
            'bond_tags': list(row.get('bond_tags') or []),
            'source_snapshot_id': str(row.get('source_snapshot_id') or '').strip(),
            'canon_snapshot_id': str(row.get('canon_snapshot_id') or '').strip(),
            'sandbox_id': str(row.get('sandbox_id') or '').strip(),
            'storyline_id': str(row.get('storyline_id') or '').strip(),
            'session_id': str(row.get('session_id') or '').strip(),
            'checkpoint_id': str(row.get('checkpoint_id') or '').strip(),
            'branch_id': str(row.get('branch_id') or '').strip(),
            'memory_scope': str(row.get('memory_scope') or '').strip(),
            'promotion_scope': str(row.get('promotion_scope') or '').strip(),
        })
    return out


def _shared_memory_state(entity_id: str, project_id: str = '', query: str = '', mode: str = 'roleplay', *, source_snapshot_id: str = '', canon_snapshot_id: str = '', sandbox_id: str = '', storyline_id: str = '', session_id: str = '', checkpoint_id: str = '', branch_id: str = '', memory_scope: str = '', promotion_scope: str = '') -> list[dict[str, Any]]:
    story_scope = _scope_filters(
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
    rows = _shared_rows(entity_id, project_id, scope_filters=story_scope)[:4]
    shared_scope = _storyline_shared_scope(storyline_id)
    shared_bridge = fetch_rp2_shared_continuity_rows(
        project_id=project_id,
        entity_id=entity_id,
        query=str(query or '').strip(),
        limit=4,
        linked_world_id=shared_scope.get('linked_world_id', ''),
        linked_universe_id=shared_scope.get('linked_universe_id', ''),
        exclude_storyline_id=storyline_id,
    ) if shared_scope else {'results': {}}
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append({
            'id': str(row.get('id') or '').strip(),
            'title': str(row.get('title') or '').strip(),
            'summary': str(row.get('summary') or '').strip(),
            'participant_ids': list(row.get('participant_ids') or []),
            'salience': float(row.get('salience') or 0.0),
            'source_ref': str(row.get('source_ref') or '').strip(),
            'source_backend': 'file_store',
            'source_snapshot_id': str(row.get('source_snapshot_id') or '').strip(),
            'canon_snapshot_id': str(row.get('canon_snapshot_id') or '').strip(),
            'sandbox_id': str(row.get('sandbox_id') or '').strip(),
            'storyline_id': str(row.get('storyline_id') or '').strip(),
            'session_id': str(row.get('session_id') or '').strip(),
            'checkpoint_id': str(row.get('checkpoint_id') or '').strip(),
            'branch_id': str(row.get('branch_id') or '').strip(),
            'memory_scope': str(row.get('memory_scope') or '').strip(),
            'promotion_scope': str(row.get('promotion_scope') or '').strip(),
        })
    hybrid_bridge = select_rp2_hybrid_runtime_memory_rows(
        project_id=project_id,
        entity_id=entity_id,
        query=str(query or '').strip(),
        limit=4,
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
    sqlite_shared = (hybrid_bridge.get('sqlite_bridge') or {}).get('results', {}).get('shared_memories') if isinstance((hybrid_bridge.get('sqlite_bridge') or {}).get('results'), dict) else []
    chroma_shared = (hybrid_bridge.get('chroma_bridge') or {}).get('results', {}).get('shared_memories') if isinstance((hybrid_bridge.get('chroma_bridge') or {}).get('results'), dict) else []
    continuity_shared = (shared_bridge.get('results') or {}).get('shared_memories') if isinstance(shared_bridge.get('results'), dict) else []
    mode_profile = _mode_packet_profile(mode)
    merged, _shared_trace = _budget_runtime_rows([('sqlite_bridge', {'shared_memories': sqlite_shared}), ('chroma_bridge', {'shared_memories': chroma_shared}), ('shared_continuity', {'shared_memories': continuity_shared}), ('file_store', {'shared_memories': out})], limit_map={'shared_memories': int((mode_profile.get('budgets') or {}).get('shared_memories') or 4)}, selection_policy=f"{mode_profile.get('key') or 'roleplay'}_story_scope_sqlite_chroma_shared_file_semantic_recovery_session_pressure_diversity_recurrence_author_controls_reranked_budgeted", source_weights=dict(mode_profile.get('source_weights') or SOURCE_RERANK_WEIGHTS), bucket_weights=dict(mode_profile.get('bucket_weights') or {}), recurrence_map=fetch_rp2_recurrence_map(project_id=project_id, entity_id=entity_id), control_map=fetch_rp2_memory_control_map(project_id=project_id, entity_id=entity_id))
    return list(merged.get('shared_memories') or [])

def _continuity_guard(canon_record: dict[str, Any] | None, packet: dict[str, Any]) -> dict[str, Any]:
    canon_data = canon_record.get('data') if isinstance((canon_record or {}).get('data'), dict) else {}
    return {
        'canon_record_id': str((canon_record or {}).get('id') or '').strip(),
        'canon_label': str((canon_record or {}).get('label') or '').strip(),
        'source_refs': list((canon_record or {}).get('source_refs') or []),
        'scene_count': int(canon_data.get('scene_count') or 0),
        'active_guard_count': len(packet.get('canon_guards') or []),
        'note': 'Prefer approved canon, selected memories, and relationship state over ad-hoc invention.',
    }


def _linked_entity_ids(entity_focus: dict[str, Any]) -> list[str]:
    links = entity_focus.get('links') if isinstance(entity_focus.get('links'), dict) else {}
    scope = links.get('scope') if isinstance(links.get('scope'), dict) else {}
    related = links.get('related') if isinstance(links.get('related'), dict) else {}
    seen: list[str] = []
    for value in scope.values():
        clean = str(value or '').strip()
        if clean and clean not in seen:
            seen.append(clean)
    for values in related.values():
        for value in values or []:
            clean = str(value or '').strip()
            if clean and clean not in seen:
                seen.append(clean)
    return seen


def _related_entity_summaries(entity_focus: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entity_id in _linked_entity_ids(entity_focus):
        if entity_id == str(entity_focus.get('id') or '').strip():
            continue
        entity = _entity_summary(entity_id)
        if not entity or (not str(entity.get('kind') or '').strip() and not str(entity.get('label') or '').strip()):
            continue
        rows.append({
            'id': str(entity.get('id') or '').strip(),
            'label': str(entity.get('label') or entity.get('id') or '').strip(),
            'kind': str(entity.get('kind') or '').strip(),
            'summary': str(entity.get('data', {}).get('summary') or entity.get('summary') or '').strip(),
            'links': entity.get('links') if isinstance(entity.get('links'), dict) else {},
            'data': entity.get('data') if isinstance(entity.get('data'), dict) else {},
        })
        if len(rows) >= limit:
            break
    return rows


def _builder_graph_lines(entity_focus: dict[str, Any], related_entities: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for row in related_entities:
        label = str(row.get('label') or row.get('id') or '').strip()
        kind = str(row.get('kind') or '').strip()
        summary = str(row.get('summary') or '').strip()
        if label:
            line = f"{kind}: {label}" if kind else label
            if summary:
                line += f" — {summary[:160]}"
            lines.append(line)
    return lines[:8]


def _entity_identity_lines(entity: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if not entity:
        return lines
    label = str(entity.get('label') or entity.get('id') or '').strip()
    if label:
        lines.append(f'Focus entity: {label}')
    kind = str(entity.get('kind') or '').strip()
    if kind:
        lines.append(f'Kind: {kind}')
    data = entity.get('data') if isinstance(entity.get('data'), dict) else {}
    try:
        spec = get_entity_spec(kind)
    except Exception:
        spec = {'canonical_fields': []}
    shown_keys: list[str] = []
    for key in spec.get('canonical_fields') or []:
        if len(shown_keys) >= 10:
            break
        value = str(data.get(key) or '').strip()
        if value:
            shown_keys.append(key)
            lines.append(f'{key}: {value}')
    if len(shown_keys) < 5:
        for key in sorted(list(data.keys())):
            if key in shown_keys:
                continue
            value = str(data.get(key) or '').strip()
            if not value:
                continue
            lines.append(f'{key}: {value}')
            shown_keys.append(key)
            if len(shown_keys) >= 8:
                break
    return lines


def _render_context_blocks(packet: dict[str, Any]) -> dict[str, str]:
    entity = packet.get('entity_focus') if isinstance(packet.get('entity_focus'), dict) else {}
    lines_relationships = [f"- {row.get('relationship_type')}: {row.get('summary')}" for row in (packet.get('relationship_state') or []) if str(row.get('summary') or '').strip()]
    lines_world = [f"- {row.get('text') or row.get('title')}" for row in (packet.get('world_facts') or []) if str(row.get('text') or row.get('title') or '').strip()]
    lines_episodic = [f"- {row.get('text') or row.get('title')}" for row in (packet.get('episodic_memories') or []) if str(row.get('text') or row.get('title') or '').strip()]
    lines_shared = [f"- {row.get('summary') or row.get('title')}" for row in (packet.get('shared_memories') or []) if str(row.get('summary') or row.get('title') or '').strip()]
    lines_guards = [f"- {row.get('text') or row.get('title')}" for row in (packet.get('canon_guards') or []) if str(row.get('text') or row.get('title') or '').strip()]
    lines_related = [f"- {line}" for line in _builder_graph_lines(entity, packet.get('related_entities') or []) if str(line or '').strip()]
    return {
        'identity_block': '\n'.join(_entity_identity_lines(entity)).strip(),
        'relationship_block': '\n'.join(lines_relationships).strip(),
        'world_block': '\n'.join(lines_world).strip(),
        'episodic_block': '\n'.join(lines_episodic).strip(),
        'shared_block': '\n'.join(lines_shared).strip(),
        'guard_block': '\n'.join(lines_guards).strip(),
        'related_block': '\n'.join(lines_related).strip(),
    }


def _world_id_from_entity(entity_focus: dict[str, Any]) -> str:
    links = entity_focus.get('links') if isinstance(entity_focus.get('links'), dict) else {}
    scope = links.get('scope') if isinstance(links.get('scope'), dict) else {}
    data = entity_focus.get('data') if isinstance(entity_focus.get('data'), dict) else {}
    return str(scope.get('world_id') or data.get('current_world_id') or data.get('origin_world_id') or '').strip()


def _focus_stack(entity_focus: dict[str, Any], relationship_state: list[dict[str, Any]], related_entities: list[dict[str, Any]] | None = None) -> list[str]:
    items: list[str] = []
    focus_id = str(entity_focus.get('id') or '').strip()
    if focus_id:
        items.append(focus_id)
    links = entity_focus.get('links') if isinstance(entity_focus.get('links'), dict) else {}
    related_links = links.get('related') if isinstance(links.get('related'), dict) else {}
    for key in ('cast_character_ids', 'focus_character_ids', 'character_ids'):
        for value in related_links.get(key) or []:
            clean = str(value or '').strip()
            if clean and clean not in items:
                items.append(clean)
            if len(items) >= 6:
                return items
    for related in related_entities or []:
        clean = str(related.get('id') or '').strip()
        if clean and clean not in items:
            items.append(clean)
        if len(items) >= 6:
            return items
    for row in relationship_state:
        for key in ('target_entity_id', 'source_entity_id'):
            value = str(row.get(key) or '').strip()
            if value and value not in items:
                items.append(value)
            if len(items) >= 4:
                return items
    return items


def _scene_state_seed(
    *,
    project_id: str,
    source_scope: str,
    source_id: str,
    entity_focus: dict[str, Any],
    relationship_state: list[dict[str, Any]],
    packet: dict[str, Any],
    selected_memory_ids: list[str],
    related_entities: list[dict[str, Any]],
    output_preset: str = 'roleplay',
    interaction_mode: str = 'roleplay',
) -> dict[str, Any]:
    guard_ids = [str(row.get('id') or '').strip() for row in (packet.get('canon_guards') or []) if str(row.get('id') or '').strip()]
    mode_model = normalize_mode_model(output_preset=output_preset or packet.get('mode') or 'roleplay', interaction_mode=interaction_mode or packet.get('interaction_mode') or 'roleplay', prefer='output')
    return build_scene_state(
        active_world_id=_world_id_from_entity(entity_focus),
        active_scenario_id='',
        cast_entity_ids=[item for item in ([str(entity_focus.get('id') or '').strip()] + [str(item or '').strip() for item in (((entity_focus.get('links') or {}).get('related') or {}).get('cast_character_ids') or []) + (((entity_focus.get('links') or {}).get('related') or {}).get('focus_character_ids') or []) if str(item or '').strip()]) if item],
        focus_stack=_focus_stack(entity_focus, relationship_state, related_entities),
        narrator_posture='partner_focus',
        continuity_mode='runtime_anchored',
        runtime_bundle_id='',
        runtime_bundle_inputs={
            'source_scope': source_scope,
            'source_id': source_id,
            'project_id': project_id,
            'retrieval_query': str((packet.get('working_memory') or {}).get('retrieval_query') or '').strip(),
            'bundle_mode': str(packet.get('mode') or '').strip(),
        },
        memory_source_ids=selected_memory_ids,
        canon_guard_source_ids=guard_ids,
        source_container_id=project_id,
        scene_goal=str((packet.get('working_memory') or {}).get('retrieval_query') or '').strip(),
        output_preset=str(mode_model.get('output_preset') or 'roleplay').strip().lower(),
        interaction_mode=str(mode_model.get('interaction_mode') or 'roleplay').strip().lower(),
        scene_notes=str((packet.get('continuity_guard') or {}).get('note') or '').strip(),
    )



def build_runtime_bundle(*, mode: str = 'roleplay', interaction_mode: str = 'roleplay', source_scope: str = 'project', source_id: str = '', project_id: str = '', entity_id: str = '', query: str = '', top_k: int = 8, save_bundle: bool = True, source_snapshot_id: str = '', canon_snapshot_id: str = '', sandbox_id: str = '', storyline_id: str = '', session_id: str = '', checkpoint_id: str = '', branch_id: str = '', memory_scope: str = '', promotion_scope: str = '') -> dict[str, Any]:
    clean_source_scope = str(source_scope or 'project').strip().lower()
    clean_source_id = str(source_id or '').strip()
    clean_project_id = str(project_id or '').strip()
    clean_entity_id = str(entity_id or '').strip()
    story_scope_hint = {
        'storyline_id': str(storyline_id or '').strip(),
        'session_id': str(session_id or '').strip(),
        'checkpoint_id': str(checkpoint_id or '').strip(),
        'source_snapshot_id': str(source_snapshot_id or '').strip(),
        'canon_snapshot_id': str(canon_snapshot_id or '').strip(),
        'sandbox_id': str(sandbox_id or '').strip(),
        'branch_id': str(branch_id or '').strip(),
    }
    if not memory_scope and any(story_scope_hint.values()):
        memory_scope = 'sandbox'
    if not promotion_scope and any(story_scope_hint.values()):
        promotion_scope = 'sandbox_only'
    story_scope = _scope_filters(
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
    canon_record = _canon_scope(clean_source_scope, clean_source_id)
    if canon_record:
        clean_project_id = clean_project_id or str(canon_record.get('project_id') or '').strip()
        if not clean_entity_id:
            linked = canon_record.get('linked_entity_ids') if isinstance(canon_record.get('linked_entity_ids'), list) else []
            clean_entity_id = str(linked[0] if linked else '').strip()
    if clean_source_scope == 'builder_record' and clean_source_id and not clean_entity_id:
        clean_entity_id = clean_source_id
    if not clean_project_id and clean_source_scope == 'project':
        clean_project_id = clean_source_id
    if not clean_source_id:
        clean_source_id = clean_project_id or clean_entity_id or 'runtime_source'

    mode_model = normalize_mode_model(output_preset=mode, interaction_mode=interaction_mode, prefer='output')
    clean_mode = str(mode_model.get('output_preset') or 'roleplay').strip().lower()
    clean_interaction_mode = str(mode_model.get('interaction_mode') or 'roleplay').strip().lower()
    clean_mode_goal = str(mode_model.get('goal_key') or 'roleplay').strip().lower()

    entity_focus = _entity_summary(clean_entity_id) if clean_entity_id else {}
    if clean_source_scope == 'builder_record' and entity_focus and not clean_project_id:
        links = entity_focus.get('links') if isinstance(entity_focus.get('links'), dict) else {}
        clean_project_id = str(links.get('source_container_id') or '').strip()
    if clean_source_scope == 'builder_record' and clean_entity_id:
        try:
            compile_memory_from_builder_record(clean_entity_id)
        except Exception:
            pass
    slices, retrieval_trace = _top_memory_slices(
        project_id=clean_project_id,
        entity_id=clean_entity_id,
        query=str(query or '').strip(),
        top_k=max(1, int(top_k or 8)),
        mode=clean_mode,
        source_snapshot_id=story_scope.get('source_snapshot_id', ''),
        canon_snapshot_id=story_scope.get('canon_snapshot_id', ''),
        sandbox_id=story_scope.get('sandbox_id', ''),
        storyline_id=story_scope.get('storyline_id', ''),
        session_id=story_scope.get('session_id', ''),
        checkpoint_id=story_scope.get('checkpoint_id', ''),
        branch_id=story_scope.get('branch_id', ''),
        memory_scope=story_scope.get('memory_scope', ''),
        promotion_scope=story_scope.get('promotion_scope', ''),
    )
    relationship_state = _relationship_state(
        clean_entity_id,
        clean_project_id,
        source_snapshot_id=story_scope.get('source_snapshot_id', ''),
        canon_snapshot_id=story_scope.get('canon_snapshot_id', ''),
        sandbox_id=story_scope.get('sandbox_id', ''),
        storyline_id=story_scope.get('storyline_id', ''),
        session_id=story_scope.get('session_id', ''),
        checkpoint_id=story_scope.get('checkpoint_id', ''),
        branch_id=story_scope.get('branch_id', ''),
        memory_scope=story_scope.get('memory_scope', ''),
        promotion_scope=story_scope.get('promotion_scope', ''),
    )
    shared_state = _shared_memory_state(
        clean_entity_id,
        clean_project_id,
        str(query or '').strip(),
        mode=clean_mode,
        source_snapshot_id=story_scope.get('source_snapshot_id', ''),
        canon_snapshot_id=story_scope.get('canon_snapshot_id', ''),
        sandbox_id=story_scope.get('sandbox_id', ''),
        storyline_id=story_scope.get('storyline_id', ''),
        session_id=story_scope.get('session_id', ''),
        checkpoint_id=story_scope.get('checkpoint_id', ''),
        branch_id=story_scope.get('branch_id', ''),
        memory_scope=story_scope.get('memory_scope', ''),
        promotion_scope=story_scope.get('promotion_scope', ''),
    )
    related_entities = _related_entity_summaries(entity_focus, limit=8) if entity_focus else []
    packet = {
        'packet_schema_version': 3,
        'project_id': clean_project_id,
        'source_container_id': clean_project_id,
        'query': str(query or '').strip(),
        'mode': str(mode or 'roleplay').strip().lower(),
        'story_scope': dict(story_scope),
        'entity_focus': entity_focus,
        'world_facts': slices['world_facts'],
        'episodic_memories': slices['episodic_memories'],
        'canon_guards': slices['canon_guards'],
        'callback_anchors': slices['callback_anchors'],
        'relationship_beliefs': slices['relationship_beliefs'],
        'relationship_state': relationship_state,
        'shared_memories': shared_state,
        'related_entities': related_entities,
        'working_memory': {
            'top_k': max(1, int(top_k or 8)),
            'retrieval_query': str(query or '').strip(),
            'retrieved_at': _now_iso(),
            'source_scope': clean_source_scope,
            'source_id': clean_source_id,
            'story_scope': dict(story_scope),
            'retrieval_trace': retrieval_trace,
            'sqlite_bridge_selected': int(((retrieval_trace.get('sqlite_bridge') or {}).get('selected_count') or 0)),
            'chroma_bridge_selected': int(((retrieval_trace.get('chroma_bridge') or {}).get('selected_count') or 0)),
            'selection_policy': str(retrieval_trace.get('selection_policy') or 'roleplay_story_scope_sqlite_chroma_snapshot_file_reranked_budgeted').strip(),
            'migration_cleanup': dict(retrieval_trace.get('migration_cleanup') or {}),
            'mode_profile_key': str(((retrieval_trace.get('mode_profile') or {}).get('key') or str(mode or 'roleplay')).strip()),
            'packet_budgets': dict(retrieval_trace.get('budget_map') or RUNTIME_PACKET_BUDGETS),
            'closed_loop_guardrails': retrieval_trace.get('closed_loop_guardrails') if isinstance(retrieval_trace.get('closed_loop_guardrails'), dict) else {},
            'session_pressure_profile': retrieval_trace.get('session_pressure_profile') if isinstance(retrieval_trace.get('session_pressure_profile'), dict) else {},
            'saturation_guardrails': retrieval_trace.get('saturation_guardrails') if isinstance(retrieval_trace.get('saturation_guardrails'), dict) else {},
            'pressure_eval': retrieval_trace.get('pressure_eval') if isinstance(retrieval_trace.get('pressure_eval'), dict) else {},
            'recurrence_map_size': int(retrieval_trace.get('recurrence_map_size') or 0),
            'control_map_size': int(retrieval_trace.get('control_map_size') or 0),
        },
    }
    packet['continuity_guard'] = _continuity_guard(canon_record, packet)
    packet['context_blocks'] = _render_context_blocks(packet)
    selected_entity_ids = [clean_entity_id] if clean_entity_id else []
    selected_memory_ids: list[str] = []
    for key in ['world_facts', 'episodic_memories', 'canon_guards', 'callback_anchors', 'relationship_beliefs']:
        for row in packet.get(key) or []:
            item_id = _resolve_runtime_input_id(row)
            if item_id and item_id not in selected_memory_ids:
                selected_memory_ids.append(item_id)
    for row in shared_state:
        item_id = _resolve_runtime_input_id(row)
        if item_id and item_id not in selected_memory_ids:
            selected_memory_ids.append(item_id)
    recurrence_sync = persist_rp2_recurrence_rows(
        project_id=clean_project_id,
        entity_id=clean_entity_id,
        mode=clean_mode,
        selected_rows_by_bucket={
            'world_facts': packet.get('world_facts') or [],
            'episodic_memories': packet.get('episodic_memories') or [],
            'canon_guards': packet.get('canon_guards') or [],
            'callback_anchors': packet.get('callback_anchors') or [],
            'relationship_beliefs': packet.get('relationship_beliefs') or [],
            'shared_memories': shared_state or [],
        },
    )
    packet['scene_state_seed'] = _scene_state_seed(
        project_id=clean_project_id,
        source_scope=clean_source_scope,
        source_id=clean_source_id,
        entity_focus=entity_focus,
        relationship_state=relationship_state,
        packet=packet,
        selected_memory_ids=selected_memory_ids,
        related_entities=related_entities,
    )
    if isinstance(packet.get('scene_state_seed'), dict):
        packet['scene_state_seed']['story_scope'] = dict(story_scope)
    for row in related_entities:
        rid = str(row.get('id') or '').strip()
        if rid and rid not in selected_entity_ids:
            selected_entity_ids.append(rid)
    bundle = build_runtime_bundle_record(
        mode=clean_mode,
        source_scope=clean_source_scope,
        source_id=clean_source_id,
        selected_entity_ids=selected_entity_ids,
        selected_memory_ids=selected_memory_ids,
        packet=packet,
        meta={'status': 'compiled' if save_bundle else 'preview'},
    )
    if isinstance(bundle.get('packet'), dict) and isinstance(bundle['packet'].get('scene_state_seed'), dict):
        bundle['packet']['scene_state_seed']['runtime_bundle_id'] = str(bundle.get('id') or '').strip()
    if isinstance(bundle.get('meta'), dict):
        source_record = load_saved_record('entity_record', clean_entity_id or clean_source_id) if (clean_entity_id or clean_source_id) else None
        selected_input_fingerprints = {}
        for memory_id in selected_memory_ids:
            input_row = _load_runtime_input_row(memory_id)
            if isinstance(input_row, dict):
                selected_input_fingerprints[str(memory_id)] = _fingerprint_payload(input_row)
        bundle['meta']['story_scope'] = dict(story_scope)
        bundle['meta']['mode_model'] = dict(mode_model)
        bundle['meta']['runtime_inputs'] = {
            'source_record_id': clean_entity_id or clean_source_id,
            'source_record_fingerprint': _fingerprint_payload(source_record) if isinstance(source_record, dict) else '',
            'selected_memory_count': len(selected_memory_ids),
            'selected_entity_count': len(selected_entity_ids),
            'selected_input_fingerprints': selected_input_fingerprints,
        }
        bundle['meta']['freshness_status'] = 'fresh'
    retrieval_trace_sync: dict[str, Any] | None = None
    if save_bundle:
        ROLEPLAY_V2_RUNTIME_BUNDLES_DIR.mkdir(parents=True, exist_ok=True)
        save_record(bundle)
    try:
        retrieval_trace_sync = persist_rp2_retrieval_trace(
            bundle_id=str(bundle.get('id') or '').strip(),
            project_id=clean_project_id,
            entity_id=clean_entity_id,
            mode=clean_mode,
            source_scope=clean_source_scope,
            source_id=clean_source_id,
            session_id=story_scope.get('session_id', ''),
            checkpoint_id=story_scope.get('checkpoint_id', ''),
            source_snapshot_id=story_scope.get('source_snapshot_id', ''),
            canon_snapshot_id=story_scope.get('canon_snapshot_id', ''),
            sandbox_id=story_scope.get('sandbox_id', ''),
            storyline_id=story_scope.get('storyline_id', ''),
            branch_id=story_scope.get('branch_id', ''),
            memory_scope=story_scope.get('memory_scope', 'sandbox') or 'sandbox',
            promotion_scope=story_scope.get('promotion_scope', 'sandbox_only') or 'sandbox_only',
            query_text=str(query or '').strip(),
            selected_ids=selected_memory_ids,
            trace=retrieval_trace if isinstance(retrieval_trace, dict) else {},
            packet=packet if isinstance(packet, dict) else {},
        )
    except Exception:
        retrieval_trace_sync = {'ok': False}
    return {
        'bundle': bundle,
        'packet': packet,
        'saved': bool(save_bundle),
        'story_scope': dict(story_scope),
        'retrieval_trace_sync': retrieval_trace_sync,
        'recurrence_sync': recurrence_sync,
        'selected_counts': {
            'entities': len(selected_entity_ids),
            'memory_ids': len(selected_memory_ids),
            'relationship_state': len(relationship_state),
            'shared_memories': len(shared_state),
            'related_entities': len(related_entities),
        },
    }


def _normalize_runtime_bundle_mode_row(row: dict[str, Any] | None = None) -> dict[str, Any]:
    bundle = dict(row or {})
    packet = bundle.get('packet') if isinstance(bundle.get('packet'), dict) else {}
    scene_state_seed = packet.get('scene_state_seed') if isinstance(packet.get('scene_state_seed'), dict) else {}
    mode_model = normalize_mode_model(
        output_preset=bundle.get('mode') or packet.get('mode') or scene_state_seed.get('output_preset') or 'roleplay',
        interaction_mode=bundle.get('interaction_mode') or packet.get('interaction_mode') or scene_state_seed.get('interaction_mode') or 'roleplay',
        prefer='output',
    )
    bundle['mode'] = str(mode_model.get('output_preset') or 'roleplay').strip().lower()
    bundle['interaction_mode'] = str(mode_model.get('interaction_mode') or 'roleplay').strip().lower()
    bundle['mode_goal'] = str(bundle.get('mode_goal') or packet.get('mode_goal') or mode_model.get('goal_key') or 'roleplay').strip().lower()
    if isinstance(packet, dict):
        packet['mode'] = bundle['mode']
        packet['interaction_mode'] = bundle['interaction_mode']
        packet['mode_goal'] = bundle['mode_goal']
        packet['mode_model'] = dict(mode_model)
        if isinstance(scene_state_seed, dict):
            scene_state_seed['output_preset'] = bundle['mode']
            scene_state_seed['interaction_mode'] = bundle['interaction_mode']
        bundle['packet'] = packet
    meta = bundle.get('meta') if isinstance(bundle.get('meta'), dict) else {}
    meta['mode_model'] = dict(mode_model)
    bundle['meta'] = meta
    return bundle

def get_runtime_bundle(bundle_id: str) -> dict[str, Any] | None:
    row = read_json_object(_bundle_path(bundle_id), None)
    if not isinstance(row, dict):
        return None
    row = _normalize_runtime_bundle_mode_row(row)
    row['freshness'] = _runtime_bundle_freshness(row)
    return row



def get_runtime_bundle_trace(bundle_id: str) -> dict[str, Any] | None:
    row = get_runtime_bundle(bundle_id)
    if not isinstance(row, dict):
        return None
    packet = row.get('packet') if isinstance(row.get('packet'), dict) else {}
    working_memory = packet.get('working_memory') if isinstance(packet.get('working_memory'), dict) else {}
    retrieval_trace = working_memory.get('retrieval_trace') if isinstance(working_memory.get('retrieval_trace'), dict) else {}
    return {
        'bundle_id': str(row.get('id') or bundle_id).strip(),
        'mode': str(row.get('mode') or '').strip(),
        'source_scope': str(row.get('source_scope') or '').strip(),
        'source_id': str(row.get('source_id') or '').strip(),
        'query': str(working_memory.get('retrieval_query') or '').strip(),
        'selected_memory_ids': list(row.get('selected_memory_ids') or []),
        'freshness': _runtime_bundle_freshness(row),
        'trace': retrieval_trace,
    }

def list_project_runtime_bundles(project_id: str) -> dict[str, Any]:
    clean_project_id = str(project_id or '').strip()
    bundles: list[dict[str, Any]] = []
    for path in sorted(ROLEPLAY_V2_RUNTIME_BUNDLES_DIR.glob('*.json')):
        row = read_json_object(path, None)
        if not isinstance(row, dict):
            continue
        row = _normalize_runtime_bundle_mode_row(row)
        packet = row.get('packet') if isinstance(row.get('packet'), dict) else {}
        if clean_project_id and str(packet.get('project_id') or '').strip() != clean_project_id:
            continue
        scene_state_seed = packet.get('scene_state_seed') if isinstance(packet.get('scene_state_seed'), dict) else {}
        freshness = _runtime_bundle_freshness(row)
        bundles.append({
            'id': str(row.get('id') or '').strip(),
            'mode': str(row.get('mode') or '').strip(),
            'interaction_mode': str(row.get('interaction_mode') or '').strip(),
            'mode_goal': str(row.get('mode_goal') or '').strip(),
            'source_scope': str(row.get('source_scope') or '').strip(),
            'source_id': str(row.get('source_id') or '').strip(),
            'project_id': str(packet.get('project_id') or '').strip(),
            'query': str((packet.get('working_memory') or {}).get('retrieval_query') or '').strip(),
            'selected_entity_ids': list(row.get('selected_entity_ids') or []),
            'selected_memory_ids': list(row.get('selected_memory_ids') or []),
            'active_world_id': str(scene_state_seed.get('active_world_id') or '').strip(),
            'focus_stack': list(scene_state_seed.get('focus_stack') or []),
            'updated_at': str((row.get('meta') or {}).get('updated_at') or ''),
            'status': str((row.get('meta') or {}).get('status') or ''),
            'freshness_status': freshness.get('status') or 'fresh',
            'is_stale': bool(freshness.get('is_stale')),
            'stale_reasons': list(freshness.get('stale_reasons') or []),
            'latest_input_at': str(freshness.get('latest_input_at') or ''),
            'source_record_id': str(freshness.get('source_record_id') or ''),
            'source_record_label': str(freshness.get('source_record_label') or ''),
        })
    return {'project_id': clean_project_id, 'runtime_bundles': bundles, 'count': len(bundles)}
