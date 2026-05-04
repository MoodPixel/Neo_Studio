from __future__ import annotations

from typing import Any

SANDBOX_MEMORY_SCOPE = 'sandbox'
SANDBOX_PROMOTION_SCOPE = 'sandbox_only'
_ALLOWED_RUNTIME_MEMORY_SCOPES = {SANDBOX_MEMORY_SCOPE}
_ALLOWED_PROMOTION_SCOPES = {SANDBOX_PROMOTION_SCOPE, 'shared_world', 'shared_universe', 'durable_project'}
_EXPLICIT_PROMOTION_FLAGS = {
    'allow_promotion',
    'allow_runtime_promotion',
    'explicit_promotion',
    'promotion_confirmed',
}


def _clean(value: Any, limit: int = 0) -> str:
    text = str(value or '').strip()
    if limit > 0:
        text = text[:limit]
    return text


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or '').strip().lower()
    return text in {'1', 'true', 'yes', 'y', 'on', 'allow', 'allowed', 'confirmed'}


def runtime_scope_allows_promotion(scope: dict[str, Any] | None) -> bool:
    payload = scope if isinstance(scope, dict) else {}
    return any(_truthy(payload.get(flag)) for flag in _EXPLICIT_PROMOTION_FLAGS)


def enforce_sandbox_writeback_scope(scope: dict[str, Any] | None, *, default_sandbox_id: str = '') -> dict[str, Any]:
    """Return a safe runtime writeback scope.

    Runtime scene writeback may create episodic/relationship/callback/thread rows,
    but it must not mutate source/canon memory or broader shared continuity unless
    the caller explicitly marks the operation as a promotion action. This keeps
    active stories sandboxed while still allowing dedicated future promotion UI.
    """
    raw = dict(scope or {}) if isinstance(scope, dict) else {}
    safe = dict(raw)
    warnings: list[str] = []

    requested_memory_scope = _clean(raw.get('memory_scope') or SANDBOX_MEMORY_SCOPE, limit=80).lower() or SANDBOX_MEMORY_SCOPE
    if requested_memory_scope not in _ALLOWED_RUNTIME_MEMORY_SCOPES:
        warnings.append(f"runtime writeback memory_scope '{requested_memory_scope}' was clamped to '{SANDBOX_MEMORY_SCOPE}'")
    safe['memory_scope'] = SANDBOX_MEMORY_SCOPE

    requested_promotion_scope = _clean(raw.get('promotion_scope') or SANDBOX_PROMOTION_SCOPE, limit=80).lower() or SANDBOX_PROMOTION_SCOPE
    if requested_promotion_scope not in _ALLOWED_PROMOTION_SCOPES:
        warnings.append(f"unknown promotion_scope '{requested_promotion_scope}' was clamped to '{SANDBOX_PROMOTION_SCOPE}'")
        requested_promotion_scope = SANDBOX_PROMOTION_SCOPE

    if requested_promotion_scope != SANDBOX_PROMOTION_SCOPE and not runtime_scope_allows_promotion(raw):
        warnings.append(
            f"promotion_scope '{requested_promotion_scope}' requires an explicit promotion flag; clamped to '{SANDBOX_PROMOTION_SCOPE}'"
        )
        requested_promotion_scope = SANDBOX_PROMOTION_SCOPE
    safe['promotion_scope'] = requested_promotion_scope

    sandbox_id = _clean(raw.get('sandbox_id') or default_sandbox_id, limit=120)
    if not sandbox_id:
        sandbox_id = 'default_sandbox'
        warnings.append("missing sandbox_id; assigned 'default_sandbox' for runtime isolation")
    safe['sandbox_id'] = sandbox_id

    prior = raw.get('sandbox_guard_warnings') if isinstance(raw.get('sandbox_guard_warnings'), list) else []
    safe['sandbox_guard_warnings'] = [str(item) for item in prior if str(item or '').strip()] + warnings
    safe['sandbox_guard_active'] = True
    return safe


def sandbox_boundary_report(scope: dict[str, Any] | None) -> dict[str, Any]:
    safe = enforce_sandbox_writeback_scope(scope)
    return {
        'ok': safe.get('memory_scope') == SANDBOX_MEMORY_SCOPE and safe.get('promotion_scope') in _ALLOWED_PROMOTION_SCOPES,
        'memory_scope': safe.get('memory_scope'),
        'promotion_scope': safe.get('promotion_scope'),
        'sandbox_id': safe.get('sandbox_id'),
        'warnings': list(safe.get('sandbox_guard_warnings') or []),
        'sandbox_guard_active': bool(safe.get('sandbox_guard_active')),
    }
