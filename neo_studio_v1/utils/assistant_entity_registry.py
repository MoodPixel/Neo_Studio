from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from .assistant_project_profiles import resolve_project_profile
from .assistant_store import load_project
from .memory_service.sqlite_store import ensure_memory_foundation, sqlite_conn

ENTITY_REGISTRY_VERSION = 'assistant_entity_registry_v1'

UNIVERSE_ENTITY_KINDS = {
    'universe', 'world', 'region', 'kingdom', 'city', 'location', 'organization',
    'faction', 'creature', 'character', 'event', 'timeline_event', 'rule', 'relic',
    'faith', 'species', 'hidden_realm', 'dragon', 'document', 'record',
    'lore_source_record', 'concept', 'law_or_rule', 'capability', 'limitation',
    'bond_or_relationship', 'event_or_history', 'myth_or_misconception',
    'condition', 'ritual_or_marker', 'failure_mode', 'lore_note'
}

RELATIONSHIP_ALIASES = {
    'world_ids': ('contains', 'world'),
    'region_ids': ('contains', 'region'),
    'kingdom_ids': ('contains', 'kingdom'),
    'city_ids': ('contains', 'city'),
    'location_ids': ('contains', 'location'),
    'organization_ids': ('references', 'organization'),
    'faction_ids': ('references', 'faction'),
    'character_ids': ('references', 'character'),
    'creature_ids': ('references', 'creature'),
    'legend_ids': ('references', 'legend'),
    'cycle_ids': ('references', 'cycle'),
    'event_ids': ('references', 'event'),
}

CANON_ORDER = {
    'primary_canon': 100,
    'active': 90,
    'secondary_canon': 80,
    'draft': 50,
    'speculative': 35,
    'disputed': 25,
    'deprecated': 10,
    'archived': 5,
    'contradicted': 0,
}


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def _clean(value: Any, limit: int = 4000) -> str:
    return ' '.join(str(value or '').replace('\r', '\n').split())[:max(40, limit)].strip()


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)
    except Exception:
        return '{}'


def _load_json(text: str, fallback: Any) -> Any:
    try:
        return json.loads(text or '')
    except Exception:
        return fallback


def _slug(value: str, fallback: str = 'entity') -> str:
    clean = re.sub(r'[^a-zA-Z0-9._:-]+', '-', str(value or '').strip()).strip('-._:')
    return (clean or fallback)[:180]


def _normalize_kind(value: Any, project_type: str = '') -> str:
    raw = str(value or '').strip().lower().replace(' ', '_').replace('-', '_').replace('/', '_')
    if raw.endswith('_ids'):
        raw = raw[:-4]
    if raw.endswith('_id'):
        raw = raw[:-3]
    if raw.endswith('s') and raw[:-1] in UNIVERSE_ENTITY_KINDS:
        raw = raw[:-1]
    if project_type == 'universe' and raw in {'kingdom_or_region', 'great_region'}:
        return 'region'
    return raw or 'record'


def _entity_key(project_id: str, entity_id: str, label: str, kind: str) -> str:
    if entity_id:
        return _slug(entity_id)
    base = f'{kind}:{label}'.lower()
    return _slug(base, f'{kind}_{uuid4().hex[:8]}')


def ensure_entity_registry_foundation() -> None:
    ensure_memory_foundation()
    with sqlite_conn() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS assistant_entities (
                entity_uid TEXT PRIMARY KEY,
                project_id TEXT NOT NULL DEFAULT '',
                entity_id TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'record',
                label TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                canon_status TEXT NOT NULL DEFAULT 'draft',
                visibility TEXT NOT NULL DEFAULT 'project_private',
                source_ref TEXT NOT NULL DEFAULT '',
                source_filename TEXT NOT NULL DEFAULT '',
                import_id TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                is_deleted INTEGER NOT NULL DEFAULT 0
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_assistant_entities_project_kind ON assistant_entities(project_id, kind, is_deleted)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_assistant_entities_project_label ON assistant_entities(project_id, label)')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS assistant_entity_relationships (
                relationship_uid TEXT PRIMARY KEY,
                project_id TEXT NOT NULL DEFAULT '',
                source_uid TEXT NOT NULL DEFAULT '',
                source_entity_id TEXT NOT NULL DEFAULT '',
                relationship_type TEXT NOT NULL DEFAULT 'references',
                target_uid TEXT NOT NULL DEFAULT '',
                target_entity_id TEXT NOT NULL DEFAULT '',
                target_kind TEXT NOT NULL DEFAULT '',
                target_label TEXT NOT NULL DEFAULT '',
                canon_status TEXT NOT NULL DEFAULT 'draft',
                source_ref TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                is_deleted INTEGER NOT NULL DEFAULT 0
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_assistant_entity_relationships_project ON assistant_entity_relationships(project_id, source_uid, target_uid, is_deleted)')


def _upsert_entity(conn, *, project_id: str, entity_id: str, kind: str, label: str, summary: str = '', canon_status: str = 'draft', visibility: str = 'project_private', source_ref: str = '', source_filename: str = '', import_id: str = '', metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _now_iso()
    kind = _normalize_kind(kind)
    label = _clean(label or entity_id or kind, 240) or 'Entity'
    entity_id = _clean(entity_id, 240)
    entity_uid = f'{project_id}::{_entity_key(project_id, entity_id, label, kind)}'
    existing = conn.execute('SELECT * FROM assistant_entities WHERE entity_uid=?', (entity_uid,)).fetchone()
    existing_meta = _load_json(existing['metadata_json'], {}) if existing else {}
    merged_meta = {**(existing_meta if isinstance(existing_meta, dict) else {}), **(metadata or {})}
    existing_rank = CANON_ORDER.get(str(existing['canon_status'] if existing else '').strip(), -1)
    new_rank = CANON_ORDER.get(str(canon_status or '').strip(), 50)
    final_canon = str(canon_status or 'draft').strip() if new_rank >= existing_rank else str(existing['canon_status'] or 'draft')
    final_summary = _clean(summary, 3000) or (str(existing['summary']) if existing else '')
    final_visibility = str(visibility or (existing['visibility'] if existing else '') or 'project_private').strip()
    created_at = str(existing['created_at']) if existing else now
    conn.execute('''
        INSERT INTO assistant_entities(entity_uid, project_id, entity_id, kind, label, summary, canon_status, visibility, source_ref, source_filename, import_id, metadata_json, created_at, updated_at, is_deleted)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        ON CONFLICT(entity_uid) DO UPDATE SET
            kind=excluded.kind,
            label=excluded.label,
            summary=excluded.summary,
            canon_status=excluded.canon_status,
            visibility=excluded.visibility,
            source_ref=excluded.source_ref,
            source_filename=excluded.source_filename,
            import_id=excluded.import_id,
            metadata_json=excluded.metadata_json,
            updated_at=excluded.updated_at,
            is_deleted=0
    ''', (entity_uid, project_id, entity_id, kind, label, final_summary, final_canon, final_visibility, source_ref, source_filename, import_id, _safe_json(merged_meta), created_at, now))
    return {'entity_uid': entity_uid, 'project_id': project_id, 'entity_id': entity_id, 'kind': kind, 'label': label, 'canon_status': final_canon, 'visibility': final_visibility, 'summary': final_summary}


def _upsert_relationship(conn, *, project_id: str, source: dict[str, Any], target: dict[str, Any], relationship_type: str = 'references', canon_status: str = 'draft', source_ref: str = '', metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _now_iso()
    source_uid = str(source.get('entity_uid') or '')
    target_uid = str(target.get('entity_uid') or '')
    if not source_uid or not target_uid or source_uid == target_uid:
        return {}
    relationship_type = _normalize_kind(relationship_type) or 'references'
    rel_uid = f'{project_id}::{_slug(source_uid)}::{relationship_type}::{_slug(target_uid)}'
    conn.execute('''
        INSERT INTO assistant_entity_relationships(relationship_uid, project_id, source_uid, source_entity_id, relationship_type, target_uid, target_entity_id, target_kind, target_label, canon_status, source_ref, metadata_json, created_at, updated_at, is_deleted)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        ON CONFLICT(relationship_uid) DO UPDATE SET
            relationship_type=excluded.relationship_type,
            target_kind=excluded.target_kind,
            target_label=excluded.target_label,
            canon_status=excluded.canon_status,
            source_ref=excluded.source_ref,
            metadata_json=excluded.metadata_json,
            updated_at=excluded.updated_at,
            is_deleted=0
    ''', (
        rel_uid, project_id, source_uid, str(source.get('entity_id') or ''), relationship_type,
        target_uid, str(target.get('entity_id') or ''), str(target.get('kind') or ''), str(target.get('label') or ''),
        canon_status, source_ref, _safe_json(metadata or {}), now, now,
    ))
    return {'relationship_uid': rel_uid, 'relationship_type': relationship_type, 'source_uid': source_uid, 'target_uid': target_uid}


def _summary_from_structured_record(data: dict[str, Any]) -> str:
    bits = []
    for key in ('summary', 'description', 'tagline'):
        if data.get(key):
            bits.append(str(data.get(key)))
    fields = data.get('fields') if isinstance(data.get('fields'), dict) else {}
    for path in (('identity', 'tagline'), ('identity', 'symbolic_identity'), ('cosmology', 'cosmology_summary'), ('rich_authoring', 'atmosphere')):
        cur: Any = fields
        for part in path:
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur:
            bits.append(str(cur))
    return _clean('\n'.join(bits), 3000)


def _entities_from_json(data: Any, *, project_type: str, fallback_filename: str = '') -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return entities
    root_id = _clean(data.get('id') or '', 240)
    root_kind = _normalize_kind(data.get('kind') or 'record', project_type)
    root_label = _clean(data.get('display_label') or data.get('label') or root_id or fallback_filename or 'Structured record', 240)
    entities.append({
        'entity_id': root_id,
        'kind': root_kind,
        'label': root_label,
        'summary': _summary_from_structured_record(data),
        'metadata': {'schema_version': data.get('schema_version'), 'source': 'json_root'},
    })
    links = data.get('links') if isinstance(data.get('links'), dict) else {}
    related = links.get('related') if isinstance(links.get('related'), dict) else {}
    for rel_key, values in related.items() if isinstance(related, dict) else []:
        rel_type, kind_hint = RELATIONSHIP_ALIASES.get(str(rel_key), ('references', str(rel_key).rstrip('s')))
        if isinstance(values, list):
            for value in values:
                clean = _clean(value, 240)
                if clean:
                    entities.append({'entity_id': clean, 'kind': _normalize_kind(kind_hint, project_type), 'label': clean, 'summary': '', 'metadata': {'source': f'links.related.{rel_key}', 'root_relationship': rel_type}})
    scope = links.get('scope') if isinstance(links.get('scope'), dict) else {}
    for key, value in scope.items() if isinstance(scope, dict) else []:
        clean = _clean(value, 240)
        if not clean:
            continue
        kind = _normalize_kind(str(key).replace('primary_', '').replace('_id', ''), project_type)
        entities.append({'entity_id': clean, 'kind': kind, 'label': clean, 'summary': '', 'metadata': {'source': f'links.scope.{key}', 'root_relationship': 'scoped_to'}})
    return entities


def _entities_from_text(text: str, *, project_type: str, filename: str = '') -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    if not text:
        return entities
    patterns = [
        (r'^\s*World Name:\s*(.+)$', 'world'),
        (r'^\s*Universe(?: Name)?:\s*(.+)$', 'universe'),
        (r'^\s*(Kingdom|Region|City|Location|Organization|Faction|Creature|Character|Event|Faith|Species):\s*(.+)$', ''),
    ]
    for pattern, fixed_kind in patterns:
        for match in re.finditer(pattern, text, flags=re.I | re.M):
            if fixed_kind:
                kind = fixed_kind
                label = match.group(1)
            else:
                kind = match.group(1).lower()
                label = match.group(2)
            label_clean = _clean(label.split('—')[0].strip(), 240)
            if label_clean:
                entities.append({'entity_id': '', 'kind': _normalize_kind(kind, project_type), 'label': label_clean, 'summary': '', 'metadata': {'source': 'text_pattern', 'filename': filename}})
    if project_type == 'universe' and not entities and filename:
        entities.append({'entity_id': '', 'kind': 'document', 'label': filename, 'summary': '', 'metadata': {'source': 'text_fallback'}})
    return entities




def _entities_from_structured_records(records: Any, *, project_type: str) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    if not isinstance(records, list):
        return entities
    for record in records:
        if not isinstance(record, dict):
            continue
        record_id = _clean(record.get('id') or '', 240)
        label = _clean(record.get('label') or record_id, 240)
        if not (record_id or label):
            continue
        summary = _clean(record.get('summary') or '', 3000)
        metadata = {
            'source': 'structured_record_builder',
            'assistant_domain': record.get('assistant_domain') or '',
            'import_type': record.get('import_type') or '',
            'aliases': record.get('aliases') if isinstance(record.get('aliases'), list) else [],
            'tags': record.get('tags') if isinstance(record.get('tags'), list) else [],
            'source_section_indexes': record.get('source_section_indexes') if isinstance(record.get('source_section_indexes'), list) else [],
            'links': record.get('links') if isinstance(record.get('links'), dict) else {},
        }
        entities.append({
            'entity_id': record_id,
            'kind': _normalize_kind(record.get('kind') or 'record', project_type),
            'label': label or record_id,
            'summary': summary,
            'metadata': metadata,
        })
    return entities

def build_entities_from_import(*, project_id: str, parsed: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    clean_project_id = str(project_id or '').strip()
    if not clean_project_id:
        return {'ok': False, 'error': 'missing_project_id'}
    ensure_entity_registry_foundation()
    project = load_project(clean_project_id) or {}
    profile = resolve_project_profile(project)
    project_type = str(parsed.get('project_type') or profile.get('project_type') or project.get('project_type') or 'general').strip()
    filename = str(parsed.get('filename') or report.get('filename') or '').strip()
    source_ref = str(report.get('source_ref') or '').strip()
    source_canon = report.get('source_canon') if isinstance(report.get('source_canon'), dict) else (parsed.get('source_canon') if isinstance(parsed.get('source_canon'), dict) else {})
    import_id = str(report.get('import_id') or '').strip()
    canon_status = str(report.get('canon_status') or 'draft').strip()
    visibility = str(report.get('visibility') or 'project_private').strip()
    parsed_json = parsed.get('parsed_json')
    raw_text = str(parsed.get('text') or '')
    raw_entities = []
    raw_entities.extend(_entities_from_json(parsed_json, project_type=project_type, fallback_filename=filename))
    raw_entities.extend(_entities_from_text(raw_text, project_type=project_type, filename=filename))
    raw_entities.extend(_entities_from_structured_records(parsed.get('structured_records'), project_type=project_type))
    for item in parsed.get('entities') or []:
        if isinstance(item, dict):
            raw_entities.append({'entity_id': item.get('id') or '', 'kind': item.get('kind') or 'record', 'label': item.get('label') or item.get('id') or '', 'summary': '', 'metadata': {'source': 'phase16_report'}})
    seen: set[tuple[str, str, str]] = set()
    created: list[dict[str, Any]] = []
    with sqlite_conn() as conn:
        for item in raw_entities:
            key = (_normalize_kind(item.get('kind'), project_type), _clean(item.get('entity_id'), 240), _clean(item.get('label'), 240).lower())
            if key in seen or not (key[1] or key[2]):
                continue
            seen.add(key)
            created.append(_upsert_entity(
                conn,
                project_id=clean_project_id,
                entity_id=item.get('entity_id') or '',
                kind=item.get('kind') or 'record',
                label=item.get('label') or item.get('entity_id') or '',
                summary=item.get('summary') or '',
                canon_status=canon_status,
                visibility=visibility,
                source_ref=source_ref,
                source_filename=filename,
                import_id=import_id,
                metadata={**(item.get('metadata') if isinstance(item.get('metadata'), dict) else {}), 'source_doc_id': source_canon.get('source_doc_id') or '', 'source_hash_sha256': source_canon.get('source_hash_sha256') or '', 'source_snapshot_path': source_canon.get('snapshot_path') or ''},
            ))
        root = created[0] if created else None
        rels: list[dict[str, Any]] = []
        if root:
            by_entity_id = {str(item.get('entity_id') or ''): item for item in created if str(item.get('entity_id') or '')}
            for target in created[1:]:
                meta = target.get('metadata') if isinstance(target.get('metadata'), dict) else {}
                links = meta.get('links') if isinstance(meta.get('links'), dict) else {}
                parent_id = str(links.get('parent_record_id') or '')
                source = by_entity_id.get(parent_id) or root
                if parent_id:
                    rel_type = 'derived_from'
                else:
                    rel_type = 'contains' if str(source.get('kind')) == 'universe' and str(target.get('kind')) in {'world', 'region', 'city', 'location'} else 'references'
                rel = _upsert_relationship(conn, project_id=clean_project_id, source=source, target=target, relationship_type=rel_type, canon_status=canon_status, source_ref=source_ref, metadata={'import_id': import_id, 'parent_record_id': parent_id, 'source_doc_id': source_canon.get('source_doc_id') or '', 'source_hash_sha256': source_canon.get('source_hash_sha256') or ''})
                if rel:
                    rels.append(rel)
    return {'ok': True, 'entity_count': len(created), 'relationship_count': len(rels), 'entities': created[:80], 'relationships': rels[:120]}


def fetch_project_entities(project_id: str, *, kind: str = '', q: str = '', limit: int = 80) -> list[dict[str, Any]]:
    ensure_entity_registry_foundation()
    clean_project_id = str(project_id or '').strip()
    where = ['project_id=?', 'is_deleted=0']
    params: list[Any] = [clean_project_id]
    if kind:
        where.append('kind=?')
        params.append(_normalize_kind(kind))
    if q:
        where.append('(LOWER(label) LIKE ? OR LOWER(entity_id) LIKE ? OR LOWER(summary) LIKE ?)')
        needle = f'%{str(q).strip().lower()}%'
        params.extend([needle, needle, needle])
    sql = 'SELECT * FROM assistant_entities WHERE ' + ' AND '.join(where) + ' ORDER BY CASE canon_status WHEN "primary_canon" THEN 0 WHEN "active" THEN 1 WHEN "secondary_canon" THEN 2 WHEN "draft" THEN 3 ELSE 4 END, updated_at DESC LIMIT ?'
    params.append(max(1, min(int(limit or 80), 500)))
    with sqlite_conn() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_to_entity(row) for row in rows]


def fetch_project_relationships(project_id: str, *, entity_uid: str = '', limit: int = 120) -> list[dict[str, Any]]:
    ensure_entity_registry_foundation()
    clean_project_id = str(project_id or '').strip()
    where = ['project_id=?', 'is_deleted=0']
    params: list[Any] = [clean_project_id]
    if entity_uid:
        where.append('(source_uid=? OR target_uid=?)')
        params.extend([entity_uid, entity_uid])
    sql = 'SELECT * FROM assistant_entity_relationships WHERE ' + ' AND '.join(where) + ' ORDER BY updated_at DESC LIMIT ?'
    params.append(max(1, min(int(limit or 120), 500)))
    with sqlite_conn() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_to_relationship(row) for row in rows]


def _row_to_entity(row) -> dict[str, Any]:
    return {
        'entity_uid': row['entity_uid'],
        'project_id': row['project_id'],
        'entity_id': row['entity_id'],
        'kind': row['kind'],
        'label': row['label'],
        'summary': row['summary'],
        'canon_status': row['canon_status'],
        'visibility': row['visibility'],
        'source_ref': row['source_ref'],
        'source_filename': row['source_filename'],
        'import_id': row['import_id'],
        'metadata': _load_json(row['metadata_json'], {}),
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
    }


def _row_to_relationship(row) -> dict[str, Any]:
    return {
        'relationship_uid': row['relationship_uid'],
        'project_id': row['project_id'],
        'source_uid': row['source_uid'],
        'source_entity_id': row['source_entity_id'],
        'relationship_type': row['relationship_type'],
        'target_uid': row['target_uid'],
        'target_entity_id': row['target_entity_id'],
        'target_kind': row['target_kind'],
        'target_label': row['target_label'],
        'canon_status': row['canon_status'],
        'source_ref': row['source_ref'],
        'metadata': _load_json(row['metadata_json'], {}),
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
    }


def project_entity_graph_summary(project_id: str, *, q: str = '', limit: int = 60) -> dict[str, Any]:
    entities = fetch_project_entities(project_id, q=q, limit=limit)
    relationships = fetch_project_relationships(project_id, limit=limit * 2)
    counts_by_kind: dict[str, int] = {}
    counts_by_canon: dict[str, int] = {}
    for entity in entities:
        counts_by_kind[entity['kind']] = counts_by_kind.get(entity['kind'], 0) + 1
        counts_by_canon[entity['canon_status']] = counts_by_canon.get(entity['canon_status'], 0) + 1
    conflicts = detect_project_canon_warnings(project_id, entities=entities)
    return {
        'ok': True,
        'project_id': str(project_id or '').strip(),
        'version': ENTITY_REGISTRY_VERSION,
        'entity_count': len(entities),
        'relationship_count': len(relationships),
        'counts_by_kind': counts_by_kind,
        'counts_by_canon': counts_by_canon,
        'entities': entities[:limit],
        'relationships': relationships[:limit * 2],
        'warnings': conflicts,
    }


def detect_project_canon_warnings(project_id: str, *, entities: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rows = entities if isinstance(entities, list) else fetch_project_entities(project_id, limit=300)
    warnings: list[dict[str, Any]] = []
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for entity in rows:
        key = (str(entity.get('kind') or '').strip(), str(entity.get('entity_id') or entity.get('label') or '').strip().lower())
        if key[1]:
            by_key.setdefault(key, []).append(entity)
    for key, group in by_key.items():
        canon_set = {str(item.get('canon_status') or '').strip() for item in group if str(item.get('canon_status') or '').strip()}
        labels = {str(item.get('label') or '').strip() for item in group if str(item.get('label') or '').strip()}
        if len(canon_set) > 1:
            warnings.append({'type': 'mixed_canon_status', 'kind': key[0], 'entity_key': key[1], 'canon_statuses': sorted(canon_set), 'labels': sorted(labels)[:6]})
        if len(labels) > 1 and any(item.get('entity_id') for item in group):
            warnings.append({'type': 'label_variant', 'kind': key[0], 'entity_key': key[1], 'labels': sorted(labels)[:8]})
    return warnings[:40]


def format_entity_graph_context(project_id: str, *, q: str = '', limit: int = 16) -> str:
    summary = project_entity_graph_summary(project_id, q=q, limit=limit)
    entities = summary.get('entities') or []
    if not entities:
        return ''
    lines = [f"Project entity graph: {summary.get('entity_count')} matched entities, {summary.get('relationship_count')} relationships."]
    for entity in entities[:limit]:
        label = entity.get('label') or entity.get('entity_id') or 'Entity'
        bits = [str(entity.get('kind') or 'record'), str(entity.get('canon_status') or 'draft')]
        if entity.get('visibility'):
            bits.append(str(entity.get('visibility')))
        lines.append(f"- {label} ({', '.join(bits)})")
        if entity.get('summary'):
            lines.append(f"  {str(entity.get('summary'))[:360]}")
    warnings = summary.get('warnings') or []
    if warnings:
        lines.append('Canon graph warnings:')
        for warning in warnings[:5]:
            lines.append(f"- {warning.get('type')}: {warning.get('kind')} {warning.get('entity_key')}")
    return '\n'.join(lines).strip()
