from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MirrorWriteResult:
    ok: bool
    lane: str
    entity_type: str
    entity_id: str
    operation: str
    error: str = ''


@dataclass(slots=True)
class AssistantMirrorPayload:
    entity_id: str
    source_json_path: str
    record: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RoleplayMirrorPayload:
    entity_id: str
    source_json_path: str
    record: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NeoProjectMemoryPayload:
    entity_id: str
    source_json_path: str
    record: dict[str, Any] = field(default_factory=dict)
