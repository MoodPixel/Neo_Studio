from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from ..logging_utils import get_logger
from .chroma_store import ASSISTANT_COLLECTION, NEO_PROJECT_COLLECTION, ROLEPLAY_COLLECTION, query_memory
from .sqlite_store import fetch_memory_chunk_status_map, sqlite_conn
from .reranker import RERANK_PROFILES, rerank_candidates, resolve_retrieval_profile
try:
    from ..assistant_import_types import RETRIEVAL_LIMIT_BY_IMPORT_TYPE, RETRIEVAL_WEIGHT_BY_IMPORT_TYPE
except Exception:  # keep retriever resilient during partial installs
    RETRIEVAL_LIMIT_BY_IMPORT_TYPE = {}
    RETRIEVAL_WEIGHT_BY_IMPORT_TYPE = {}
try:
    from ..assistant_chunk_types import (
        ASSISTANT_CHUNK_TYPE_LIMITS,
        ASSISTANT_CHUNK_TYPE_WEIGHTS,
        normalize_metadata_chunk_type,
    )
except Exception:  # keep retriever resilient during partial installs
    ASSISTANT_CHUNK_TYPE_LIMITS = {}
    ASSISTANT_CHUNK_TYPE_WEIGHTS = {}
    def normalize_metadata_chunk_type(metadata):
        return dict(metadata or {})

try:
    from ..assistant_canon_priority import apply_priority_metadata, priority_bonus
except Exception:  # keep retriever resilient during partial installs
    def apply_priority_metadata(metadata):
        return dict(metadata or {})
    def priority_bonus(metadata):
        return 0.0


try:
    from ..assistant_memory_sandbox import sandbox_filter_items, is_memory_allowed_for_scope, normalize_chunk_scope_metadata
    from ..assistant_source_aware_retrieval import (
        resolve_source_aware_retrieval_mode,
        source_aware_filter_items,
        build_source_disclosure_summary,
    )
except Exception:  # keep retriever resilient during partial installs
    def sandbox_filter_items(items, scope):
        return list(items or []), []
    def is_memory_allowed_for_scope(metadata, scope):
        class _D:
            allowed = True
            reason = 'sandbox_unavailable'
            def to_dict(self):
                return {'allowed': True, 'reason': self.reason}
        return _D()
    def normalize_chunk_scope_metadata(metadata):
        return dict(metadata or {})
    def resolve_source_aware_retrieval_mode(*, scope=None, query_text='', requested_mode=''):
        return str(requested_mode or (scope or {}).get('retrieval_mode') or 'project_active' if (scope or {}).get('project_id') else 'global_safe')
    def source_aware_filter_items(items, scope, retrieval_mode):
        return sandbox_filter_items(items, scope)
    def build_source_disclosure_summary(items):
        return {'required': False, 'labels': [], 'project_ids': [], 'instruction': ''}

try:
    from ..assistant_retrieval_authority import authority_metadata
except Exception:  # keep retriever resilient during partial installs
    def authority_metadata(scope=None, query_text='', requested_mode=''):
        return {'authority_mode': 'assistant_balanced'}

logger = get_logger(__name__)

ASSISTANT_TYPE_WEIGHTS = {
    'preference': 1.18,
    'style_shift': 1.15,
    'workflow': 1.08,
    'project_fact': 1.0,
    'example_output': 0.9,
    'summary': 0.72,
    'action_log': 0.86,
    'task_memory': 1.06,
    'tool_result': 0.92,
    'patch_result': 1.12,
    'validation_result': 0.98,
    'failed_attempt': 1.04,
    'decision_record': 1.12,
    # Global assistant import types. These are used when uploaded project knowledge
    # has not been mapped to a narrower memory type yet.
    'json_schema': 1.18,
    'markdown_structured': 1.08,
    'raw_creative_lore': 1.05,
    'client_project_data': 1.14,
    'email_or_message_data': 1.12,
    'project_docs': 1.12,
    'code_or_config': 1.04,
    'conversation_notes': 1.03,
    'raw_reference_text': 0.96,
}
ASSISTANT_TYPE_WEIGHTS.update(RETRIEVAL_WEIGHT_BY_IMPORT_TYPE)
ASSISTANT_TYPE_WEIGHTS.update(ASSISTANT_CHUNK_TYPE_WEIGHTS)
NEO_PROJECT_TYPE_WEIGHTS = {
    'guardrail': 1.24,
    'implementation_decision': 1.20,
    'extension_contract': 1.16,
    'workflow_rule': 1.14,
    'fix_pattern': 1.12,
    'bug_history': 1.10,
    'repo_fact': 1.04,
    'system_record': 1.02,
    'validation_result': 1.0,
    'failed_attempt': 0.96,
    'todo': 0.90,
    'summary': 0.72,
}
ROLEPLAY_TYPE_WEIGHTS = {
    'relationship_shift': 1.18,
    'unresolved_thread': 1.16,
    'event': 1.08,
    'world_fact': 1.03,
    'character_fact': 1.0,
    'callback': 0.96,
    'summary': 0.72,
}

ASSISTANT_TYPE_LIMITS = {'preference': 2, 'style_shift': 1, 'workflow': 2, 'project_fact': 2, 'example_output': 1, 'summary': 1, 'action_log': 2, 'task_memory': 2, 'tool_result': 2, 'patch_result': 2, 'validation_result': 2, 'failed_attempt': 2, 'decision_record': 2, 'json_schema': 5, 'markdown_structured': 5, 'raw_creative_lore': 5, 'client_project_data': 5, 'email_or_message_data': 4, 'project_docs': 5, 'code_or_config': 4, 'conversation_notes': 4, 'raw_reference_text': 3, 'text': 4, 'txt': 4, 'md': 4, 'markdown': 4}
ASSISTANT_TYPE_LIMITS.update(RETRIEVAL_LIMIT_BY_IMPORT_TYPE)
ASSISTANT_TYPE_LIMITS.update(ASSISTANT_CHUNK_TYPE_LIMITS)
NEO_PROJECT_TYPE_LIMITS = {'guardrail': 3, 'implementation_decision': 3, 'extension_contract': 3, 'workflow_rule': 3, 'fix_pattern': 3, 'bug_history': 2, 'repo_fact': 4, 'system_record': 3, 'validation_result': 2, 'failed_attempt': 2, 'todo': 1, 'summary': 2}
ROLEPLAY_TYPE_LIMITS = {'relationship_shift': 2, 'unresolved_thread': 2, 'event': 2, 'world_fact': 2, 'character_fact': 2, 'callback': 1, 'summary': 1}

ASSISTANT_MAX_ITEMS = 8
NEO_PROJECT_MAX_ITEMS = 8
ROLEPLAY_MAX_ITEMS = 6
ASSISTANT_MAX_CHARS = 3600
NEO_PROJECT_MAX_CHARS = 4200
ROLEPLAY_MAX_CHARS = 3000


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", str(text or '').lower())


def _clean(text: Any, limit: int = 900) -> str:
    return ' '.join(str(text or '').split())[:limit].strip()


def _iso_to_dt(value: str) -> datetime | None:
    raw = str(value or '').strip()
    if not raw:
        return None
    try:
        if raw.endswith('Z'):
            raw = raw[:-1] + '+00:00'
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _recency_bonus(created_at: str) -> float:
    dt = _iso_to_dt(created_at)
    if not dt:
        return 0.0
    age_days = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)
    if age_days <= 3:
        return 0.18
    if age_days <= 14:
        return 0.12
    if age_days <= 45:
        return 0.06
    return 0.0


def _overlap_score(query_text: str, candidate_text: str) -> float:
    q = set(_tokenize(query_text))
    if not q:
        return 0.0
    c = set(_tokenize(candidate_text))
    if not c:
        return 0.0
    overlap = len(q & c)
    return min(1.0, overlap / max(3, len(q)))


def _lane_config(lane: str) -> dict[str, Any]:
    clean = str(lane or '').strip().lower()
    if clean == 'neo_project':
        return {
            'collection': NEO_PROJECT_COLLECTION,
            'weights': NEO_PROJECT_TYPE_WEIGHTS,
            'type_limits': NEO_PROJECT_TYPE_LIMITS,
            'max_items': NEO_PROJECT_MAX_ITEMS,
            'max_chars': NEO_PROJECT_MAX_CHARS,
        }
    if clean == 'roleplay':
        return {
            'collection': ROLEPLAY_COLLECTION,
            'weights': ROLEPLAY_TYPE_WEIGHTS,
            'type_limits': ROLEPLAY_TYPE_LIMITS,
            'max_items': ROLEPLAY_MAX_ITEMS,
            'max_chars': ROLEPLAY_MAX_CHARS,
        }
    return {
        'collection': ASSISTANT_COLLECTION,
        'weights': ASSISTANT_TYPE_WEIGHTS,
        'type_limits': ASSISTANT_TYPE_LIMITS,
        'max_items': ASSISTANT_MAX_ITEMS,
        'max_chars': ASSISTANT_MAX_CHARS,
    }


def _scope_match_bonus(lane: str, metadata: dict[str, Any], scope: dict[str, Any]) -> float:
    bonus = 0.0
    entity_id = str(metadata.get('entity_id') or '').strip()
    scope_type = str(metadata.get('scope_type') or '').strip()
    scope_id = str(metadata.get('scope_id') or '').strip()
    if lane == 'assistant':
        project_id = str(scope.get('project_id') or '').strip()
        session_id = str(scope.get('session_id') or '').strip()
        if project_id and str(metadata.get('project_id') or '') == project_id:
            bonus += 0.26
        if scope_type == 'project' and scope_id and scope_id == project_id:
            bonus += 0.12
        if session_id and entity_id == session_id:
            bonus += 0.18
        if scope_type == 'session' and scope_id == session_id:
            bonus += 0.08
        if scope_type == 'profile':
            bonus += 0.05
    elif lane == 'neo_project':
        project_id = str(scope.get('project_id') or 'neo_studio').strip() or 'neo_studio'
        component = str(scope.get('component') or scope.get('active_tab') or '').strip().lower()
        file_path = str(scope.get('file_path') or '').strip().lower()
        if project_id and str(metadata.get('project_id') or '') == project_id:
            bonus += 0.22
        if scope_type == 'project' and scope_id == project_id:
            bonus += 0.10
        meta_component = str(metadata.get('component') or '').strip().lower()
        if component and meta_component and component == meta_component:
            bonus += 0.18
        meta_file = str(metadata.get('file_path') or '').strip().lower()
        if file_path and meta_file and (file_path == meta_file or file_path in meta_file or meta_file in file_path):
            bonus += 0.20
        if scope_type in {'global', 'project'}:
            bonus += 0.04
    else:
        story_id = str(scope.get('story_id') or '').strip()
        part_id = str(scope.get('part_id') or '').strip()
        campaign_id = str(scope.get('campaign_id') or story_id).strip()
        if campaign_id and str(metadata.get('campaign_id') or '') == campaign_id:
            bonus += 0.24
        if story_id and scope_id == story_id:
            bonus += 0.14
        if part_id and entity_id == part_id:
            bonus += 0.16
        if scope_type == 'part' and scope_id == part_id:
            bonus += 0.08
    return bonus


def _query_text_for_scope(lane: str, scope: dict[str, Any], query_text: str) -> str:
    bits = [_clean(query_text, 1200)]
    if lane == 'assistant':
        for key in ('thread_instruction', 'context_note', 'mode', 'project_title', 'project_brief'):
            bits.append(_clean(scope.get(key), 600))
    elif lane == 'neo_project':
        for key in ('project_title', 'project_brief', 'active_tab', 'component', 'file_path', 'workflow', 'implementation_goal'):
            bits.append(_clean(scope.get(key), 700))
    else:
        for key in ('scenario', 'scene_notes', 'memory_notes', 'author_note', 'story_scope_notes', 'chapter_scope_notes', 'part_scope_notes', 'story_title', 'part_title', 'partner_name', 'user_name'):
            bits.append(_clean(scope.get(key), 600))
    return '\n'.join(bit for bit in bits if bit)


def _load_sqlite_chunk_candidates(lane: str, scope: dict[str, Any], query_text: str, limit: int = 40) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    project_id = str(scope.get('project_id') or '').strip()
    session_id = str(scope.get('session_id') or '').strip()
    story_id = str(scope.get('story_id') or '').strip()
    part_id = str(scope.get('part_id') or '').strip()

    clauses = ['lane=?', 'is_deleted=0', 'is_suppressed=0']
    params: list[Any] = [lane]
    scope_or: list[str] = []
    if lane == 'assistant':
        source_aware_mode = str(scope.get('_source_aware_retrieval_mode') or scope.get('retrieval_mode') or '').strip().lower()
        if source_aware_mode in {'creative_reference', 'cross_project_search', 'admin_debug'}:
            # Intentional broader candidate load. Source-aware filtering below still
            # blocks private/client/quarantine data and marks project lore for disclosure.
            scope_or.append("(scope_type IN ('profile','global','project') OR project_id!='' OR (project_id='' AND scope_type=''))")
        elif project_id:
            scope_or.append('(project_id=?)')
            params.append(project_id)
            scope_or.append("(scope_type IN ('profile','global') OR (project_id='' AND scope_type=''))")
        else:
            scope_or.append("(scope_type IN ('profile','global') OR (project_id='' AND scope_type=''))")
        if session_id:
            scope_or.append('(entity_id=?)')
            params.append(session_id)
            scope_or.append('(scope_type=? AND scope_id=?)')
            params.extend(['session', session_id])
        scope_or.append('(scope_type=?)')
        params.append('profile')
    elif lane == 'neo_project':
        neo_project_id = str(scope.get('project_id') or 'neo_studio').strip() or 'neo_studio'
        scope_or.append('(project_id=?)')
        params.append(neo_project_id)
        scope_or.append('(scope_type=?)')
        params.append('global')
        component = str(scope.get('component') or scope.get('active_tab') or '').strip()
        if component:
            scope_or.append('(metadata_json LIKE ?)')
            params.append(f'%"component": "{component}"%')
        file_path = str(scope.get('file_path') or '').strip()
        if file_path:
            scope_or.append('(metadata_json LIKE ? OR source_ref LIKE ?)')
            params.extend([f'%{file_path}%', f'%{file_path}%'])
    else:
        campaign_id = str(scope.get('campaign_id') or story_id).strip()
        if campaign_id:
            scope_or.append('(campaign_id=?)')
            params.append(campaign_id)
        if story_id:
            scope_or.append('(scope_id=?)')
            params.append(story_id)
        if part_id:
            scope_or.append('(entity_id=?)')
            params.append(part_id)
            scope_or.append('(scope_type=? AND scope_id=?)')
            params.extend(['part', part_id])
        scope_or.append('(scope_type=?)')
        params.append('snapshot')
    if scope_or:
        clauses.append('(' + ' OR '.join(scope_or) + ')')

    sql = f'''
        SELECT chunk_id, chunk_type, entity_type, entity_id, scope_type, scope_id,
               project_id, campaign_id, source_ref, importance, document,
               metadata_json, created_at, updated_at
        FROM memory_chunks
        WHERE {' AND '.join(clauses)}
        ORDER BY importance DESC, updated_at DESC, created_at DESC
        LIMIT ?
    '''
    params.append(max(1, int(limit or 40)))
    with sqlite_conn() as conn:
        for row in conn.execute(sql, tuple(params)):
            metadata = {}
            try:
                metadata = json.loads(row['metadata_json'] or '{}') if row['metadata_json'] else {}
            except Exception:
                metadata = {}
            metadata = metadata if isinstance(metadata, dict) else {}
            metadata.setdefault('chunk_type', row['chunk_type'])
            metadata.setdefault('entity_type', row['entity_type'])
            metadata.setdefault('entity_id', row['entity_id'])
            metadata.setdefault('scope_type', row['scope_type'])
            metadata.setdefault('scope_id', row['scope_id'])
            metadata.setdefault('project_id', row['project_id'])
            metadata.setdefault('campaign_id', row['campaign_id'])
            metadata.setdefault('source_ref', row['source_ref'])
            metadata.setdefault('importance', row['importance'])
            metadata.setdefault('created_at', row['created_at'])
            metadata.setdefault('updated_at', row['updated_at'])
            metadata = normalize_chunk_scope_metadata(apply_priority_metadata(normalize_metadata_chunk_type(metadata)))
            candidates.append({
                'id': row['chunk_id'],
                'document': row['document'],
                'metadata': metadata,
                'distance': None,
                'rank': len(candidates),
                'source': 'sqlite_chunk',
            })

        if candidates:
            return candidates

        # fallback for older Wave 2 data that does not have memory_chunks yet
        summary_sql = '''
            SELECT summary_record_id AS chunk_id, scope_type, scope_id, summary_type, content, source_ref, created_at, updated_at
            FROM summary_records
            WHERE lane=?
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ?
        '''
        for row in conn.execute(summary_sql, (lane, max(1, int(limit or 40)))):
            content = str(row['content'] or '').strip()
            if not content:
                continue
            metadata = {
                'chunk_type': 'summary',
                'entity_type': row['scope_type'],
                'entity_id': row['scope_id'],
                'scope_type': row['scope_type'],
                'scope_id': row['scope_id'],
                'project_id': project_id if lane == 'assistant' else '',
                'campaign_id': story_id if lane == 'roleplay' else '',
                'source_ref': row['source_ref'],
                'importance': 0.5,
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
            }
            metadata = apply_priority_metadata(normalize_metadata_chunk_type(metadata))
            candidates.append({
                'id': row['chunk_id'],
                'document': content,
                'metadata': metadata,
                'distance': None,
                'rank': len(candidates),
                'source': 'sqlite_summary',
            })
    return candidates


def _rank_candidates(lane: str, query_text: str, scope: dict[str, Any], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    weights = _lane_config(lane)['weights']
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(candidates):
        metadata = normalize_chunk_scope_metadata(apply_priority_metadata(normalize_metadata_chunk_type(item.get('metadata') if isinstance(item.get('metadata'), dict) else {})))
        document = str(item.get('document') or '').strip()
        chunk_type = str(metadata.get('chunk_type') or 'summary').strip()
        importance = float(metadata.get('importance') or 0.0)
        tag_text = ' '.join(str(x) for x in (metadata.get('retrieval_tags') or [])[:64]) if isinstance(metadata.get('retrieval_tags'), list) else str(metadata.get('retrieval_tags') or '')
        overlap = _overlap_score(query_text, f'{document} {tag_text}')
        import_type = str(metadata.get('import_type') or '').strip()
        type_weight = float(weights.get(chunk_type, 1.0))
        import_weight = float(RETRIEVAL_WEIGHT_BY_IMPORT_TYPE.get(import_type, 1.0))
        base_score = (0.8 + importance) * type_weight * import_weight
        scope_bonus = _scope_match_bonus(lane, metadata, scope)
        overlap_bonus = overlap * 0.55
        recency_bonus = _recency_bonus(str(metadata.get('updated_at') or metadata.get('created_at') or ''))
        source_bonus = 0.0
        distance_bonus = 0.0
        if item.get('source') == 'chroma':
            source_bonus = max(0.02, 0.22 - (0.014 * idx))
            distance = item.get('distance')
            if isinstance(distance, (int, float)):
                distance_bonus = max(0.0, 0.16 - (float(distance) * 0.08))
        else:
            source_bonus = max(0.01, 0.10 - (0.01 * idx))
        pin_bonus = 0.28 if bool(metadata.get('is_pinned')) else 0.0
        metadata_quality_bonus = min(0.06, max(0.0, float(metadata.get('metadata_quality_score') or 0.0)) * 0.06)
        evidence_rank_bonus = min(0.08, max(0.0, float(metadata.get('evidence_rank') or 0.0)) / 120.0 * 0.08)
        truth_priority_bonus = priority_bonus(metadata)
        if metadata.get('freshness_policy') == 'stable_canon_over_recency' and truth_priority_bonus >= 0.08:
            recency_bonus = min(recency_bonus, 0.04)
        score = base_score + scope_bonus + overlap_bonus + recency_bonus + source_bonus + distance_bonus + pin_bonus + metadata_quality_bonus + evidence_rank_bonus + truth_priority_bonus
        enriched = {
            **item,
            'metadata': metadata,
            'score': score,
            'overlap': overlap,
            'diagnostics': {
                'chunk_type': chunk_type,
                'type_weight': type_weight,
                'import_type': import_type,
                'import_weight': import_weight,
                'importance': importance,
                'base_score': base_score,
                'scope_bonus': scope_bonus,
                'overlap_bonus': overlap_bonus,
                'recency_bonus': recency_bonus,
                'source_bonus': source_bonus,
                'distance_bonus': distance_bonus,
                'pin_bonus': pin_bonus,
                'metadata_quality_bonus': metadata_quality_bonus,
                'evidence_rank_bonus': evidence_rank_bonus,
                'truth_priority_bonus': truth_priority_bonus,
                'truth_priority_rank': metadata.get('truth_priority_rank'),
                'evidence_tier': metadata.get('evidence_tier'),
                'conflict_policy': metadata.get('conflict_policy'),
                'final_score': score,
            },
        }
        out.append(enriched)
    out.sort(key=lambda row: (float(row.get('score') or 0.0), float((row.get('metadata') or {}).get('importance') or 0.0)), reverse=True)
    return out


def _budget_and_dedupe(lane: str, ranked: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    config = _lane_config(lane)
    type_limits = dict(config['type_limits'])
    max_items = int(config['max_items'])
    max_chars = int(config['max_chars'])
    used_types: dict[str, int] = {}
    seen_keys: set[str] = set()
    selected: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    char_count = 0
    for item in ranked:
        metadata = normalize_chunk_scope_metadata(apply_priority_metadata(normalize_metadata_chunk_type(item.get('metadata') if isinstance(item.get('metadata'), dict) else {})))
        chunk_type = str(metadata.get('chunk_type') or 'summary').strip()
        import_type = str(metadata.get('import_type') or '').strip()
        doc = _clean(item.get('document'), 780)
        drop_reason = ''
        if not doc:
            drop_reason = 'empty_document'
        dedupe_key = f"{chunk_type}::{doc[:180].lower()}"
        if not drop_reason and dedupe_key in seen_keys:
            drop_reason = 'duplicate'
        limit = int(type_limits.get(chunk_type, RETRIEVAL_LIMIT_BY_IMPORT_TYPE.get(import_type, 2)))
        if not drop_reason and used_types.get(chunk_type, 0) >= limit:
            drop_reason = 'type_limit'
        extra = len(doc) + 24
        if not drop_reason and selected and char_count + extra > max_chars:
            drop_reason = 'budget_limit'
        if drop_reason:
            dropped.append({**item, 'metadata': metadata, 'document': doc, 'drop_reason': drop_reason})
            continue
        selected.append({**item, 'metadata': metadata, 'document': doc})
        seen_keys.add(dedupe_key)
        used_types[chunk_type] = used_types.get(chunk_type, 0) + 1
        char_count += extra
        if len(selected) >= max_items:
            dropped.extend([{**rest, 'document': _clean(rest.get('document'), 780), 'drop_reason': 'max_items'} for rest in ranked[len(selected):len(ranked)]])
            break
    return selected, dropped


def _format_item(label: str, document: str) -> str:
    return f'[{label}] {document}'


def _summary_from_items(lane: str, items: list[dict[str, Any]]) -> str:
    if not items:
        return ''
    lines: list[str] = []
    for item in items:
        metadata = normalize_chunk_scope_metadata(apply_priority_metadata(normalize_metadata_chunk_type(item.get('metadata') if isinstance(item.get('metadata'), dict) else {})))
        chunk_type = str(metadata.get('chunk_type') or 'summary').replace('_', ' ').strip().title()
        disclosure = str(metadata.get('source_disclosure_label') or '').strip() if bool(metadata.get('source_disclosure_required')) else ''
        label = f'{disclosure} · {chunk_type}' if disclosure else chunk_type
        document = _clean(item.get('document'), 720)
        if not document:
            continue
        lines.append(_format_item(label, document))
    if lane == 'assistant':
        header = 'Retrieved adaptive memory:'
    elif lane == 'neo_project':
        header = 'Retrieved Neo project memory:'
    else:
        header = 'Retrieved continuity memory:'
    return header + '\n' + '\n'.join(lines)


def build_memory_pack(lane: str, scope: dict[str, Any] | None = None, query_text: str = '', retrieval_mode: str = '') -> dict[str, Any]:
    clean_lane = str(lane or 'assistant').strip().lower()
    scope = dict(scope) if isinstance(scope, dict) else {}
    source_aware_mode = resolve_source_aware_retrieval_mode(scope=scope, query_text=query_text, requested_mode=retrieval_mode) if clean_lane == 'assistant' else ''
    if source_aware_mode:
        scope['_source_aware_retrieval_mode'] = source_aware_mode
    requested_profile = str(retrieval_mode or scope.get('rerank_profile') or scope.get('memory_rerank_profile') or '').strip().lower()
    retrieval_profile = resolve_retrieval_profile(clean_lane, scope, requested_profile)
    profile_config = RERANK_PROFILES.get(retrieval_profile, RERANK_PROFILES['smart'])
    enriched_query = _query_text_for_scope(clean_lane, scope, query_text)

    sqlite_candidates = _load_sqlite_chunk_candidates(clean_lane, scope, enriched_query, limit=int(profile_config.get('sqlite_limit') or 48))
    chroma_candidates: list[dict[str, Any]] = []
    chroma_limit = int(profile_config.get('chroma_limit') or 0)
    if chroma_limit > 0:
        try:
            chroma_candidates = query_memory(_lane_config(clean_lane)['collection'], query_text=enriched_query, n_results=chroma_limit)
        except Exception:
            logger.exception('Memory pack Chroma query failed for lane %s', clean_lane)

    combined: list[dict[str, Any]] = []
    by_id: set[str] = set()
    for item in sqlite_candidates + chroma_candidates:
        chunk_id = str(item.get('id') or '').strip()
        if not chunk_id or chunk_id in by_id:
            continue
        combined.append(item)
        by_id.add(chunk_id)

    if clean_lane == 'assistant':
        sandbox_allowed, sandbox_denied = source_aware_filter_items(combined, scope, source_aware_mode)
    else:
        sandbox_allowed, sandbox_denied = sandbox_filter_items(combined, scope)

    status_map = fetch_memory_chunk_status_map([str(item.get('id') or '').strip() for item in sandbox_allowed])
    filtered: list[dict[str, Any]] = []
    for item in sandbox_allowed:
        chunk_id = str(item.get('id') or '').strip()
        status = status_map.get(chunk_id, {})
        if bool(status.get('is_deleted')) or bool(status.get('is_suppressed')):
            continue
        metadata = normalize_chunk_scope_metadata(apply_priority_metadata(normalize_metadata_chunk_type(item.get('metadata') if isinstance(item.get('metadata'), dict) else {})))
        merged = dict(metadata)
        if status:
            merged['is_pinned'] = bool(status.get('is_pinned'))
            merged['pin_note'] = str(status.get('pin_note') or '').strip()
            merged['is_suppressed'] = bool(status.get('is_suppressed'))
        filtered.append({**item, 'metadata': merged})

    first_pass_ranked = _rank_candidates(clean_lane, enriched_query, scope, filtered)
    rerank_limit = int(profile_config.get('rerank_limit') or len(first_pass_ranked) or 0)
    ranked = rerank_candidates(
        lane=clean_lane,
        query_text=enriched_query,
        scope=scope,
        candidates=first_pass_ranked[:rerank_limit],
        profile=retrieval_profile,
    )
    if len(first_pass_ranked) > rerank_limit:
        ranked.extend(first_pass_ranked[rerank_limit:])
    selected, dropped = _budget_and_dedupe(clean_lane, ranked)
    source_disclosure = build_source_disclosure_summary(selected) if clean_lane == 'assistant' else {'required': False, 'labels': [], 'project_ids': [], 'instruction': ''}
    summary = _summary_from_items(clean_lane, selected)
    if source_disclosure.get('required') and summary:
        labels = '; '.join(source_disclosure.get('labels') or [])
        summary = 'Source note: using project/story memory as contextual reference, not global truth. ' + labels + '\n' + summary
    authority_memory_pack = {'items': selected, 'summary': summary, 'query_text': enriched_query}
    authority = authority_metadata(
        scope=scope,
        query_text=query_text,
        requested_mode=str(scope.get('authority_mode') or ''),
        memory_pack=authority_memory_pack,
    ) if clean_lane == 'assistant' else {'authority_mode': retrieval_profile}
    return {
        'lane': clean_lane,
        'query_text': enriched_query,
        'authority': authority,
        'items': selected,
        'summary': summary,
        'item_count': len(selected),
        'candidate_count': len(filtered),
        'sandbox_denied_count': len(sandbox_denied),
        'retrieval_mode': source_aware_mode if clean_lane == 'assistant' else retrieval_profile,
        'source_disclosure': source_disclosure if clean_lane == 'assistant' else {'required': False, 'labels': [], 'project_ids': [], 'instruction': ''},
        'diagnostics': {
            'config': {
                'max_items': int(_lane_config(clean_lane)['max_items']),
                'max_chars': int(_lane_config(clean_lane)['max_chars']),
                'type_limits': dict(_lane_config(clean_lane)['type_limits']),
                'retrieval_profile': retrieval_profile,
                'source_aware_retrieval_mode': source_aware_mode,
                'authority': authority,
                'profile_config': dict(profile_config),
                'reranker_enabled': bool(profile_config.get('enabled')),
                'sqlite_candidate_limit': int(profile_config.get('sqlite_limit') or 0),
                'chroma_candidate_limit': int(profile_config.get('chroma_limit') or 0),
                'rerank_candidate_limit': int(profile_config.get('rerank_limit') or 0),
            },
            'sandbox_denied': [
                {
                    'id': str(item.get('id') or '').strip(),
                    'source': str(item.get('source') or '').strip(),
                    'drop_reason': str(item.get('drop_reason') or '').strip(),
                    'metadata': item.get('metadata') if isinstance(item.get('metadata'), dict) else {},
                    'sandbox_decision': item.get('sandbox_decision') if isinstance(item.get('sandbox_decision'), dict) else {},
                    'source_aware_decision': item.get('source_aware_decision') if isinstance(item.get('source_aware_decision'), dict) else {},
                }
                for item in sandbox_denied[:24]
            ],
            'selected': [
                {
                    'id': str(item.get('id') or '').strip(),
                    'source': str(item.get('source') or '').strip(),
                    'drop_reason': '',
                    'metadata': item.get('metadata') if isinstance(item.get('metadata'), dict) else {},
                    'diagnostics': item.get('diagnostics') if isinstance(item.get('diagnostics'), dict) else {},
                }
                for item in selected
            ],
            'dropped': [
                {
                    'id': str(item.get('id') or '').strip(),
                    'source': str(item.get('source') or '').strip(),
                    'drop_reason': str(item.get('drop_reason') or '').strip(),
                    'metadata': item.get('metadata') if isinstance(item.get('metadata'), dict) else {},
                    'diagnostics': item.get('diagnostics') if isinstance(item.get('diagnostics'), dict) else {},
                }
                for item in dropped[:16]
            ],
        },
    }
