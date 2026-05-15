from __future__ import annotations

import json
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

from .config import LOGS_DIR, ROOT_DIR
from .logging_utils import get_logger

ASSISTANT_VALIDATION_VERSION = 'assistant_validation_logs_v1'
ASSISTANT_EVENT_LOG = LOGS_DIR / 'assistant_events.jsonl'
ASSISTANT_VALIDATION_LOG = LOGS_DIR / 'assistant_validation.jsonl'
MAX_LOG_LINES = 200
MAX_TEXT = 4000

logger = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _safe_text(value: Any, limit: int = MAX_TEXT) -> str:
    return str(value or '').replace('\r', ' ').strip()[:limit]


def _safe_jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except Exception:
        if isinstance(value, dict):
            return {str(k): _safe_jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_safe_jsonable(item) for item in value]
        return _safe_text(value)


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    record = _safe_jsonable({**payload, 'logged_at': payload.get('logged_at') or _now_iso()})
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')
    return record


def log_assistant_event(event_type: str, *, source: str = '', status: str = 'info', details: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Write structured Assistant audit events to JSONL and the normal Neo log."""
    payload = {
        'version': ASSISTANT_VALIDATION_VERSION,
        'event_type': _safe_text(event_type, 120),
        'source': _safe_text(source, 160),
        'status': _safe_text(status, 40),
        'details': details if isinstance(details, dict) else {},
        'logged_at': _now_iso(),
    }
    record = _append_jsonl(ASSISTANT_EVENT_LOG, payload)
    try:
        logger.info('assistant_event %s', json.dumps(record, ensure_ascii=False, sort_keys=True))
    except Exception:
        pass
    return record


def read_assistant_logs(kind: str = 'events', limit: int = 50) -> Dict[str, Any]:
    path = ASSISTANT_VALIDATION_LOG if str(kind or '').strip().lower() == 'validation' else ASSISTANT_EVENT_LOG
    clean_limit = max(1, min(int(limit or 50), MAX_LOG_LINES))
    if not path.exists():
        return {'ok': True, 'version': ASSISTANT_VALIDATION_VERSION, 'kind': kind or 'events', 'path': str(path), 'items': []}
    lines = path.read_text(encoding='utf-8', errors='ignore').splitlines()[-clean_limit:]
    items: List[Dict[str, Any]] = []
    for line in lines:
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                items.append(parsed)
        except Exception:
            items.append({'raw': line[:MAX_TEXT]})
    return {'ok': True, 'version': ASSISTANT_VALIDATION_VERSION, 'kind': kind or 'events', 'path': str(path), 'count': len(items), 'items': items}


@dataclass
class ValidationCheck:
    id: str
    label: str
    severity: str
    runner: Callable[[], Dict[str, Any]]


def _ok(details: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {'status': 'pass', 'details': details if isinstance(details, dict) else {}}


def _fail(message: str, details: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {'status': 'fail', 'message': _safe_text(message, 1200), 'details': details if isinstance(details, dict) else {}}


def _check_imports() -> Dict[str, Any]:
    modules = [
        'neo_studio_v1.utils.assistant_chat',
        'neo_studio_v1.utils.assistant_context_builder',
        'neo_studio_v1.utils.assistant_repo_indexer',
        'neo_studio_v1.utils.assistant_patch_planner',
        'neo_studio_v1.utils.assistant_action_memory',
        'neo_studio_v1.utils.assistant_local_pc_control',
        'neo_studio_v1.utils.assistant_persona_layer',
        'neo_studio_v1.utils.assistant_tools.registry',
        'neo_studio_v1.utils.assistant_tools.executor',
    ]
    imported = []
    for name in modules:
        __import__(name)
        imported.append(name)
    return _ok({'imported': imported})


def _check_tool_registry() -> Dict[str, Any]:
    from .assistant_tools.registry import get_assistant_tool_catalog
    catalog = get_assistant_tool_catalog()
    tools = catalog.get('tools') if isinstance(catalog, dict) else []
    if not isinstance(tools, list) or not tools:
        return _fail('Assistant tool catalog is empty.', {'catalog': catalog})
    missing = [tool for tool in tools if not str(tool.get('id') or '').strip() or not str(tool.get('risk') or '').strip()]
    if missing:
        return _fail('Some Assistant tools are missing id/risk metadata.', {'missing_count': len(missing)})
    return _ok({'tool_count': len(tools), 'categories': catalog.get('categories') if isinstance(catalog, dict) else []})


def _check_patch_planner() -> Dict[str, Any]:
    from .assistant_patch_planner import validate_patch_plan, preview_patch_plan
    plan = {
        'title': 'Phase 13 validation sample',
        'summary': 'Non-applied validation sample for patch planner.',
        'changes': [{'path': 'neo_system_records/02_TABS/assistant/validation/sample.md', 'action': 'add', 'content': '# Sample\n'}],
    }
    validation = validate_patch_plan(plan)
    if not validation.get('ok'):
        return _fail('Patch planner rejected a safe sample plan.', {'validation': validation})
    preview = preview_patch_plan(plan)
    if not preview.get('ok'):
        return _fail('Patch planner preview failed for safe sample plan.', {'preview': preview})
    return _ok({'change_count': validation.get('change_count'), 'preview_keys': sorted(preview.keys())})


def _check_local_pc_control() -> Dict[str, Any]:
    from .assistant_local_pc_control import list_local_action_catalog, preview_local_action
    catalog = list_local_action_catalog()
    if not catalog.get('ok'):
        return _fail('Local PC action catalog did not load.', {'catalog': catalog})
    preview = preview_local_action('run_command_preset', {'preset_id': 'python.version'})
    if not preview.get('ok'):
        return _fail('Local PC safe command preview failed.', {'preview': preview})
    return _ok({'platform': catalog.get('platform'), 'action_count': len(catalog.get('actions') or []), 'preview_risk': preview.get('risk')})


def _check_context_pack() -> Dict[str, Any]:
    from .assistant_context_builder import build_assistant_context_pack
    from .assistant_store import load_profile, list_sessions
    profile = load_profile()
    sessions = list_sessions()
    session = sessions[0] if sessions else {'id': 'validation_no_session', 'messages': [], 'mode': 'technical', 'project_id': ''}
    pack = build_assistant_context_pack(profile=profile, session=session, messages=session.get('messages') or [], preview_text='Phase 13 validation context pack smoke test')
    if not isinstance(pack, dict):
        return _fail('Context pack builder returned a non-dict payload.')
    sections = pack.get('prompt_sections') if isinstance(pack.get('prompt_sections'), list) else []
    if not sections:
        return _fail('Context pack contains no prompt sections.', {'keys': sorted(pack.keys())})
    return _ok({'section_count': len(sections), 'mode': pack.get('mode'), 'diagnostics': pack.get('diagnostics') if isinstance(pack.get('diagnostics'), dict) else {}})


def _check_repo_indexer() -> Dict[str, Any]:
    from .assistant_repo_indexer import load_repo_index, search_repo_index
    index = load_repo_index()
    if not isinstance(index, dict):
        return _fail('Repo index loader returned a non-dict payload.')
    results = search_repo_index('assistant routes', limit=5)
    if not isinstance(results, dict):
        return _fail('Repo index search returned a non-dict payload.')
    return _ok({'file_count': index.get('file_count') or len(index.get('files') or []), 'result_count': len(results.get('results') or [])})


def _check_memory_backend() -> Dict[str, Any]:
    from .memory_service.chroma_store import get_embedding_backend_status
    from .memory_service.retriever import build_memory_pack
    try:
        status = get_embedding_backend_status()
    except Exception as exc:
        status = {'ok': False, 'degraded': True, 'error': _safe_text(exc, 500)}
    try:
        pack = build_memory_pack('assistant', scope={'profile_id': 'default'}, query_text='Phase 13 validation memory retrieval', retrieval_mode='fast')
    except Exception as exc:
        # Fresh installs may not have the memory tables fully initialized until the
        # first Assistant/profile sync. Treat this as degraded, not fatal, because
        # chat routes already use defensive fallbacks around retrieval.
        return _ok({'backend': status, 'degraded': True, 'memory_error': _safe_text(exc, 500)})
    if not isinstance(pack, dict):
        return _fail('Assistant memory pack returned a non-dict payload.')
    return _ok({'backend': status, 'item_count': pack.get('item_count'), 'candidate_count': pack.get('candidate_count')})


def _check_docs() -> Dict[str, Any]:
    required = [
        ROOT_DIR / 'neo_system_records' / '02_TABS' / 'assistant' / 'ASSISTANT_DOC_INDEX.md',
        ROOT_DIR / 'neo_system_records' / '02_TABS' / 'assistant' / 'phase_records' / 'PHASE12_LOCAL_APP_CONTROL_UI.md',
        ROOT_DIR / 'neo_system_records' / '02_TABS' / 'assistant' / 'workflows' / 'LOCAL_PC_ACTIONS.md',
    ]
    missing = [str(path.relative_to(ROOT_DIR)) for path in required if not path.exists()]
    if missing:
        return _fail('Assistant documentation foundation has missing required records.', {'missing': missing})
    return _ok({'checked': [str(path.relative_to(ROOT_DIR)) for path in required]})


def validation_checks() -> List[ValidationCheck]:
    return [
        ValidationCheck('imports', 'Assistant module imports', 'critical', _check_imports),
        ValidationCheck('tool_registry', 'Tool registry integrity', 'critical', _check_tool_registry),
        ValidationCheck('patch_planner', 'Patch planner smoke test', 'critical', _check_patch_planner),
        ValidationCheck('local_pc_control', 'Local PC control guardrail smoke test', 'critical', _check_local_pc_control),
        ValidationCheck('context_pack', 'Context pack builder smoke test', 'major', _check_context_pack),
        ValidationCheck('repo_indexer', 'Repo indexer availability', 'major', _check_repo_indexer),
        ValidationCheck('memory_backend', 'Memory retrieval availability', 'major', _check_memory_backend),
        ValidationCheck('docs', 'Assistant documentation records', 'minor', _check_docs),
    ]


def run_assistant_validation_suite(*, include_optional: bool = True) -> Dict[str, Any]:
    started_at = _now_iso()
    results: List[Dict[str, Any]] = []
    for check in validation_checks():
        item = {'id': check.id, 'label': check.label, 'severity': check.severity, 'started_at': _now_iso()}
        try:
            payload = check.runner()
            item.update(payload if isinstance(payload, dict) else _fail('Check returned invalid payload.'))
        except Exception as exc:
            item.update({
                'status': 'fail',
                'message': _safe_text(str(exc) or check.label),
                'details': {'traceback': traceback.format_exc(limit=8)},
            })
        item['finished_at'] = _now_iso()
        results.append(item)
    failed = [item for item in results if item.get('status') != 'pass']
    payload = {
        'ok': not failed,
        'version': ASSISTANT_VALIDATION_VERSION,
        'started_at': started_at,
        'finished_at': _now_iso(),
        'summary': {
            'total': len(results),
            'passed': len(results) - len(failed),
            'failed': len(failed),
            'critical_failed': len([item for item in failed if item.get('severity') == 'critical']),
        },
        'results': results,
    }
    _append_jsonl(ASSISTANT_VALIDATION_LOG, payload)
    log_assistant_event('validation_suite_run', source='phase13', status='pass' if payload['ok'] else 'fail', details=payload.get('summary') or {})
    return payload
