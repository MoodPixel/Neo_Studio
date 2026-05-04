from __future__ import annotations

import copy
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from ..contracts.roleplay_v2_intake_records import build_helper_output_record
from .roleplay_v2_foundation import ROLEPLAY_V2_HELPER_OUTPUTS_DIR
from .roleplay_v2_source_projects import get_source_document
from .storage_io import atomic_write_json, read_json_object

ENTITY_STOPWORDS = {
    'The', 'A', 'An', 'And', 'But', 'Or', 'If', 'When', 'Then', 'After', 'Before', 'He', 'She', 'They', 'We', 'I',
    'His', 'Her', 'Their', 'Our', 'My', 'You', 'It', 'Its', 'In', 'On', 'At', 'By', 'For', 'From', 'To', 'Of',
    'Chapter', 'Scene', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
}
EMOTION_KEYWORDS = {'remember', 'felt', 'fear', 'afraid', 'love', 'loved', 'hate', 'hated', 'grief', 'cry', 'cried', 'promise', 'promised', 'regret', 'regretted', 'hurt', 'longed', 'wanted', 'needed', 'shame'}
RELATIONSHIP_KEYWORDS = {'love', 'hate', 'trust', 'betray', 'protect', 'fear', 'admire', 'envy', 'jealous', 'promise'}
RULE_KEYWORDS = {'must', 'must not', 'cannot', 'can never', 'always', 'never', 'forbidden', 'allowed', 'rule', 'law', 'oath'}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')



def _helper_output_path(helper_output_id: str):
    return ROLEPLAY_V2_HELPER_OUTPUTS_DIR / f'{str(helper_output_id or "").strip()}.json'



def _clean_text(value: Any) -> str:
    text = str(value or '').replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()



def _sentences(text: str) -> list[str]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    parts = re.split(r'(?<=[.!?])\s+', cleaned)
    return [part.strip() for part in parts if part.strip()]



def _extractive_summary(text: str, *, max_sentences: int = 3, max_chars: int = 700) -> str:
    chosen: list[str] = []
    total = 0
    for sentence in _sentences(text):
        if len(chosen) >= max_sentences:
            break
        if total + len(sentence) > max_chars and chosen:
            break
        chosen.append(sentence)
        total += len(sentence)
    return ' '.join(chosen)[:max_chars]



def _split_scenes(text: str) -> list[str]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    chunks = [part.strip() for part in re.split(r'\n\s*\n|(?:^|\n)(?:Scene\s+\d+|CHAPTER\s+\d+|Chapter\s+\d+)', cleaned) if part.strip()]
    if len(chunks) == 1 and len(chunks[0]) > 1800:
        paragraphs = [p.strip() for p in cleaned.split('\n') if p.strip()]
        grouped: list[str] = []
        bucket: list[str] = []
        bucket_len = 0
        for para in paragraphs:
            if bucket and bucket_len + len(para) > 1200:
                grouped.append('\n\n'.join(bucket))
                bucket = [para]
                bucket_len = len(para)
            else:
                bucket.append(para)
                bucket_len += len(para)
        if bucket:
            grouped.append('\n\n'.join(bucket))
        return grouped
    return chunks



def _extract_entity_candidates(text: str) -> list[dict[str, Any]]:
    matches = re.findall(r'\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', text)
    filtered = [m for m in matches if m not in ENTITY_STOPWORDS and len(m) > 1]
    counts = Counter(filtered)
    out: list[dict[str, Any]] = []
    for name, count in counts.most_common(12):
        out.append({'label': name, 'kind': 'candidate', 'mentions': count})
    return out



def _extract_rules(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sentence in _sentences(text):
        lower = sentence.lower()
        if any(keyword in lower for keyword in RULE_KEYWORDS):
            out.append({'rule_text': sentence[:400], 'confidence': 'low'})
    return out[:12]



def _extract_memory_candidates(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sentence in _sentences(text):
        lower = sentence.lower()
        if any(keyword in lower for keyword in EMOTION_KEYWORDS):
            title = sentence[:80].rstrip('.!?')
            out.append({
                'title': title,
                'canonical_text': sentence[:500],
                'memory_type_hint': 'episodic_memory',
                'confidence': 'low',
            })
    return out[:15]



def _extract_relationship_shifts(scene_text: str, scene_entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = [str(item.get('label') or '').strip() for item in scene_entities if str(item.get('label') or '').strip()]
    if len(names) < 2:
        return []
    lower = scene_text.lower()
    matched = [keyword for keyword in RELATIONSHIP_KEYWORDS if keyword in lower]
    if not matched:
        return []
    return [{
        'participants': names[:2],
        'shift_hint': matched[0],
        'evidence': scene_text[:400],
        'confidence': 'low',
    }]



def _scene_packets(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, scene in enumerate(_split_scenes(text), start=1):
        entities = _extract_entity_candidates(scene)
        out.append({
            'scene_index': index,
            'summary': _extractive_summary(scene, max_sentences=2, max_chars=420),
            'text_excerpt': scene[:1600],
            'entities': entities,
            'relationship_shifts': _extract_relationship_shifts(scene, entities),
            'memory_candidates': _extract_memory_candidates(scene),
        })
    return out



def _timeline_candidates(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for scene in scenes:
        summary = str(scene.get('summary') or '').strip()
        if not summary:
            continue
        out.append({
            'event_order': int(scene.get('scene_index') or 0),
            'title': summary[:120],
            'summary': summary,
            'scene_index': int(scene.get('scene_index') or 0),
        })
    return out[:20]



def _uncertainty_flags(text: str, scenes: list[dict[str, Any]], entities: list[dict[str, Any]]) -> list[str]:
    flags: list[str] = []
    if len(text) < 120:
        flags.append('Source text is very short, so breakdown confidence is limited.')
    if not scenes:
        flags.append('No clear scene boundaries were detected.')
    if not entities:
        flags.append('No strong entity candidates were detected from capitalization heuristics.')
    if len(scenes) == 1:
        flags.append('Only one scene segment was detected. Manual splitting may improve quality.')
    return flags





def _source_metadata(document: dict[str, Any]) -> dict[str, Any]:
    extra = document.get('extra') if isinstance(document.get('extra'), dict) else {}
    return {
        'document_type': str(document.get('document_type') or '').strip(),
        'order_index': int(document.get('order_index') or 0),
        'chapter_number': int(document.get('chapter_number') or 0),
        'scene_number': int(document.get('scene_number') or 0),
        'part_arc': str(extra.get('part_arc') or '').strip(),
        'pov': str(extra.get('pov') or '').strip(),
        'tense': str(extra.get('tense') or '').strip(),
        'chapter_goal': str(extra.get('chapter_goal') or '').strip(),
        'author_notes': str(extra.get('author_notes') or '').strip(),
        'draft_status': str(extra.get('draft_status') or '').strip() or 'draft',
    }


def _build_structured_payload(document: dict[str, Any]) -> dict[str, Any]:
    cleaned_text = _clean_text(document.get('cleaned_text') or document.get('raw_text') or '')
    scenes = _scene_packets(cleaned_text)
    flat_entities = _extract_entity_candidates(cleaned_text)
    source_metadata = _source_metadata(document)
    return {
        'project_id': str(document.get('project_id') or '').strip(),
        'document_id': str(document.get('id') or '').strip(),
        'document_type': str(document.get('document_type') or '').strip(),
        'title': str(document.get('title') or '').strip(),
        'source_metadata': source_metadata,
        'cleaned_text': cleaned_text,
        'chapter_summary': _extractive_summary(cleaned_text),
        'scene_breakdown': scenes,
        'entity_candidates': flat_entities,
        'timeline_candidates': _timeline_candidates(scenes),
        'relationship_shift_candidates': [item for scene in scenes for item in (scene.get('relationship_shifts') or [])][:20],
        'canon_rule_candidates': _extract_rules(cleaned_text),
        'memory_candidates': [item for scene in scenes for item in (scene.get('memory_candidates') or [])][:30],
        'uncertainty_flags': _uncertainty_flags(cleaned_text, scenes, flat_entities),
        'source_stats': {
            'char_count': len(cleaned_text),
            'scene_count': len(scenes),
            'entity_candidate_count': len(flat_entities),
        },
    }



def generate_breakdown_for_document(document_id: str) -> dict[str, Any]:
    document = get_source_document(document_id)
    if not document:
        raise ValueError('Source document not found.')
    kind_hint = 'novel_project' if str(document.get('document_type') or '').strip().startswith('novel') else 'scenario'
    structured_payload = _build_structured_payload(document)
    helper_output = build_helper_output_record(
        draft_id=str(document.get('id') or '').strip(),
        kind=kind_hint,
        cleaned_text=structured_payload['cleaned_text'],
        structured_payload=structured_payload,
        warnings=structured_payload['uncertainty_flags'],
        source_refs=[str(document.get('id') or '').strip()],
        meta={
            'status': 'review_needed',
            'approved': False,
            'notes': f"generated_from_source_document:{document.get('id') or ''}",
        },
    )
    ROLEPLAY_V2_HELPER_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(_helper_output_path(str(helper_output.get('id') or '')), helper_output)
    return helper_output



def get_breakdown_output(helper_output_id: str) -> dict[str, Any] | None:
    return read_json_object(_helper_output_path(helper_output_id), None)



def save_breakdown_review(*, helper_output_id: str, cleaned_text: str = '', structured_payload: dict[str, Any] | None = None, approved: bool = False, review_notes: str = '') -> dict[str, Any]:
    existing = get_breakdown_output(helper_output_id)
    if not existing:
        raise ValueError('Breakdown output not found.')
    updated = copy.deepcopy(existing)
    if cleaned_text.strip():
        updated['cleaned_text'] = _clean_text(cleaned_text)
    if isinstance(structured_payload, dict):
        updated['structured_payload'] = copy.deepcopy(structured_payload)
    meta = updated.get('meta') if isinstance(updated.get('meta'), dict) else {}
    meta['approved'] = bool(approved)
    meta['status'] = 'approved' if approved else 'reviewed'
    meta['updated_at'] = _now_iso()
    if review_notes.strip():
        meta['notes'] = review_notes.strip()[:4000]
    updated['meta'] = meta
    atomic_write_json(_helper_output_path(helper_output_id), updated)
    return updated
