from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

REPO_INDEX_VERSION = 'assistant_repo_index_v1'
DEFAULT_MAX_FILE_BYTES = 240_000
DEFAULT_MAX_FILES = 1200
DEFAULT_RESULT_LIMIT = 8

TEXT_EXTENSIONS = {
    '.py', '.js', '.ts', '.tsx', '.jsx', '.html', '.css', '.scss', '.json', '.md', '.txt', '.yml', '.yaml',
    '.toml', '.ini', '.cfg', '.bat', '.ps1', '.sh', '.xml', '.jinja', '.j2'
}
EXCLUDED_DIRS = {
    '.git', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'node_modules', '.venv', 'venv',
    'env', '.env', 'logs', 'temp_uploads', 'cache', '.chroma', 'chroma', 'dist', 'build'
}
IMPORTANT_PATH_HINTS = (
    'neo_studio_v1/routes/',
    'neo_studio_v1/utils/',
    'neo_studio_v1/contracts/',
    'neo_studio_v1/templates/',
    'neo_studio_v1/static/js/',
    'neo_studio_v1/extensions/',
    'neo_extensions/installed/',
    'neo_system_records/',
)


@dataclass(frozen=True)
class RepoFileRecord:
    path: str
    kind: str
    size_bytes: int
    modified_ns: int
    digest: str
    summary: str
    symbols: List[str]
    keywords: List[str]


def find_repo_root(start: Path | None = None) -> Path:
    """Resolve the Neo Studio repo root without requiring configuration."""
    base = (start or Path(__file__)).resolve()
    for candidate in [base, *base.parents]:
        if (candidate / 'neo_studio_v1').exists() and (candidate / 'neo_system_records').exists():
            return candidate
    # utils/assistant_repo_indexer.py -> neo_studio_v1/utils -> repo root
    return Path(__file__).resolve().parents[2]


def _repo_data_dir(repo_root: Path) -> Path:
    path = repo_root / 'neo_studio_v1' / 'data' / 'assistant_repo_index'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index_file(repo_root: Path) -> Path:
    return _repo_data_dir(repo_root) / 'repo_index.json'


def _safe_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.name


def _is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS


def _should_skip(path: Path, repo_root: Path) -> bool:
    rel_parts = _safe_rel(path, repo_root).split('/')
    if any(part in EXCLUDED_DIRS for part in rel_parts):
        return True
    if path.is_dir():
        return False
    if not _is_text_file(path):
        return True
    try:
        if path.stat().st_size > DEFAULT_MAX_FILE_BYTES:
            return True
    except OSError:
        return True
    return False


def _classify_path(rel_path: str) -> str:
    if rel_path.startswith('neo_studio_v1/routes/'):
        return 'route'
    if rel_path.startswith('neo_studio_v1/utils/memory_service/'):
        return 'memory_service'
    if rel_path.startswith('neo_studio_v1/utils/'):
        return 'utility'
    if rel_path.startswith('neo_studio_v1/contracts/'):
        return 'contract'
    if rel_path.startswith('neo_studio_v1/templates/'):
        return 'template'
    if rel_path.startswith('neo_studio_v1/static/js/'):
        return 'frontend_js'
    if rel_path.startswith('neo_studio_v1/static/css/'):
        return 'frontend_css'
    if rel_path.startswith('neo_studio_v1/extensions/'):
        return 'runtime_extension'
    if rel_path.startswith('neo_extensions/installed/'):
        return 'installed_extension'
    if rel_path.startswith('neo_system_records/02_TABS/assistant/'):
        return 'assistant_record'
    if rel_path.startswith('neo_system_records/'):
        return 'system_record'
    return 'repo_file'


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return ''


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8', errors='ignore')).hexdigest()[:16]


def _tokens(text: str) -> List[str]:
    raw = re.findall(r'[A-Za-z_][A-Za-z0-9_]{2,}|[a-z0-9]{3,}', text.lower())
    stop = {'the', 'and', 'for', 'with', 'from', 'this', 'that', 'return', 'true', 'false', 'none', 'null', 'def'}
    out: List[str] = []
    seen: set[str] = set()
    for token in raw:
        token = token.strip().lower()
        if token in stop or token in seen:
            continue
        seen.add(token)
        out.append(token)
        if len(out) >= 80:
            break
    return out


def _symbols(rel_path: str, text: str) -> List[str]:
    patterns = [
        r'^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(',
        r'^\s*async\s+def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(',
        r'^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\b',
        r'^\s*function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(',
        r'^\s*const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=',
        r'^\s*export\s+function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(',
        r'@router\.(get|post|put|delete|patch)\(([^\n]+)\)',
    ]
    found: List[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.MULTILINE):
            if pattern.startswith('@router'):
                found.append(f'route:{match.group(1)} {match.group(2)[:80]}')
            else:
                found.append(match.group(1))
            if len(found) >= 40:
                return found
    if rel_path.endswith('.md'):
        for match in re.finditer(r'^#{1,3}\s+(.+)$', text, flags=re.MULTILINE):
            found.append(match.group(1).strip()[:120])
            if len(found) >= 25:
                break
    return found


def _summary(rel_path: str, kind: str, text: str, symbols: List[str]) -> str:
    lines = [line.strip() for line in text.replace('\r', '\n').split('\n') if line.strip()]
    doc_line = ''
    for line in lines[:80]:
        if line.startswith('"""') or line.startswith("'''"):
            doc_line = line.strip('"\' ')
            break
        if line.startswith('# ') or line.startswith('## '):
            doc_line = line.lstrip('#').strip()
            break
        if len(line) > 40 and not line.startswith(('import ', 'from ', 'const ', 'let ', 'var ')):
            doc_line = line[:220]
            break
    symbol_text = ', '.join(symbols[:12])
    parts = [f'{kind}: {rel_path}']
    if doc_line:
        parts.append(doc_line)
    if symbol_text:
        parts.append(f'Symbols/routes: {symbol_text}')
    return ' | '.join(parts)[:900]


def iter_repo_files(repo_root: Path) -> Iterable[Path]:
    priority: List[Path] = []
    fallback: List[Path] = []
    for path in repo_root.rglob('*'):
        if _should_skip(path, repo_root):
            continue
        if path.is_dir():
            continue
        rel = _safe_rel(path, repo_root)
        if any(rel.startswith(prefix) for prefix in IMPORTANT_PATH_HINTS):
            priority.append(path)
        else:
            fallback.append(path)
    for path in sorted(priority, key=lambda p: _safe_rel(p, repo_root)):
        yield path
    for path in sorted(fallback, key=lambda p: _safe_rel(p, repo_root)):
        yield path


def build_repo_index(*, repo_root: str | Path | None = None, max_files: int = DEFAULT_MAX_FILES) -> Dict[str, Any]:
    root = Path(repo_root).resolve() if repo_root else find_repo_root()
    records: List[Dict[str, Any]] = []
    kind_counts: Dict[str, int] = {}
    skipped_after_limit = 0
    for path in iter_repo_files(root):
        if len(records) >= max_files:
            skipped_after_limit += 1
            continue
        rel = _safe_rel(path, root)
        text = _read_text(path)
        if not text:
            continue
        kind = _classify_path(rel)
        symbols = _symbols(rel, text)
        keywords = _tokens(rel + '\n' + text[:8000])[:50]
        stat = path.stat()
        record = RepoFileRecord(
            path=rel,
            kind=kind,
            size_bytes=int(stat.st_size),
            modified_ns=int(stat.st_mtime_ns),
            digest=_digest(text),
            summary=_summary(rel, kind, text, symbols),
            symbols=symbols,
            keywords=keywords,
        )
        records.append(record.__dict__)
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
    index = {
        'version': REPO_INDEX_VERSION,
        'repo_root': root.as_posix(),
        'file_count': len(records),
        'skipped_after_limit': skipped_after_limit,
        'kind_counts': kind_counts,
        'records': records,
    }
    _index_file(root).write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding='utf-8')
    return index


def load_repo_index(*, repo_root: str | Path | None = None, rebuild_if_missing: bool = True) -> Dict[str, Any]:
    root = Path(repo_root).resolve() if repo_root else find_repo_root()
    path = _index_file(root)
    if not path.exists():
        return build_repo_index(repo_root=root) if rebuild_if_missing else {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, dict) and data.get('version') == REPO_INDEX_VERSION:
            return data
    except Exception:
        pass
    return build_repo_index(repo_root=root) if rebuild_if_missing else {}


def _score_record(record: Dict[str, Any], query_tokens: set[str], query: str) -> float:
    path = str(record.get('path') or '').lower()
    kind = str(record.get('kind') or '').lower()
    summary = str(record.get('summary') or '').lower()
    symbols = ' '.join(str(v).lower() for v in record.get('symbols') or [])
    keywords = set(str(v).lower() for v in (record.get('keywords') or []))
    haystack = f'{path}\n{kind}\n{summary}\n{symbols}'
    score = 0.0
    for token in query_tokens:
        if token in path:
            score += 4.0
        if token in symbols:
            score += 3.0
        if token in keywords:
            score += 2.0
        if token in summary:
            score += 1.4
        if token in kind:
            score += 1.0
    if query and query.lower() in haystack:
        score += 6.0
    if kind in {'route', 'utility', 'memory_service', 'assistant_record'}:
        score += 0.5
    if path.startswith('neo_studio_v1/utils/assistant') or '/assistant_' in path:
        score += 1.0
    if path.startswith('neo_system_records/02_tabs/assistant/'):
        score += 0.8
    return score


def search_repo_index(query_text: str, *, repo_root: str | Path | None = None, limit: int = DEFAULT_RESULT_LIMIT) -> Dict[str, Any]:
    query = str(query_text or '').strip()
    index = load_repo_index(repo_root=repo_root, rebuild_if_missing=True)
    records = index.get('records') if isinstance(index.get('records'), list) else []
    q_tokens = set(_tokens(query)[:40])
    scored: List[Tuple[float, Dict[str, Any]]] = []
    if q_tokens or query:
        for record in records:
            if not isinstance(record, dict):
                continue
            score = _score_record(record, q_tokens, query)
            if score > 0:
                scored.append((score, record))
    else:
        for record in records[:limit]:
            if isinstance(record, dict):
                scored.append((0.1, record))
    scored.sort(key=lambda item: item[0], reverse=True)
    results = []
    for score, record in scored[:max(1, limit)]:
        results.append({
            'path': str(record.get('path') or ''),
            'kind': str(record.get('kind') or ''),
            'score': round(float(score), 4),
            'summary': str(record.get('summary') or ''),
            'symbols': list(record.get('symbols') or [])[:18],
            'digest': str(record.get('digest') or ''),
        })
    return {
        'version': REPO_INDEX_VERSION,
        'query': query,
        'file_count': int(index.get('file_count') or 0),
        'kind_counts': index.get('kind_counts') if isinstance(index.get('kind_counts'), dict) else {},
        'result_count': len(results),
        'results': results,
    }


def format_repo_context(search_payload: Dict[str, Any], *, max_chars: int = 4500) -> str:
    results = search_payload.get('results') if isinstance(search_payload.get('results'), list) else []
    if not results:
        return ''
    blocks = ['Relevant Repo Index Matches:']
    for idx, item in enumerate(results, start=1):
        path = str(item.get('path') or '').strip()
        kind = str(item.get('kind') or '').strip()
        score = item.get('score')
        summary = str(item.get('summary') or '').strip()
        symbols = ', '.join(str(v) for v in (item.get('symbols') or [])[:10])
        line = f'[{idx}] {path} ({kind}, score={score})\n{summary}'
        if symbols:
            line += f'\nSymbols/routes: {symbols}'
        blocks.append(line)
    text = '\n\n'.join(blocks).strip()
    return text[:max_chars]
