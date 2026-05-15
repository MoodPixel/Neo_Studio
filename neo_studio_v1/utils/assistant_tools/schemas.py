from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal

AssistantToolRisk = Literal['safe', 'medium', 'danger']


@dataclass(frozen=True)
class AssistantToolSpec:
    """Declarative contract for an Assistant tool.

    Phase 6 intentionally keeps tools schema-first and guardrail-first. Tools may be
    listed and previewed by the UI; execution is routed through the registry so later
    phases can add approvals and patch planning without bypassing safety policy.
    """

    id: str
    name: str
    description: str
    category: str
    risk: AssistantToolRisk = 'safe'
    requires_confirmation: bool = False
    read_only: bool = True
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    handler: Callable[[Dict[str, Any]], Dict[str, Any]] | None = None

    def public_dict(self, *, include_handler: bool = False) -> Dict[str, Any]:
        payload = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'risk': self.risk,
            'requires_confirmation': bool(self.requires_confirmation),
            'read_only': bool(self.read_only),
            'input_schema': self.input_schema,
            'output_schema': self.output_schema,
            'tags': list(self.tags or []),
        }
        if include_handler:
            payload['has_handler'] = self.handler is not None
        return payload


def text_property(description: str, *, default: str = '', max_length: int | None = None) -> Dict[str, Any]:
    schema: Dict[str, Any] = {'type': 'string', 'description': description, 'default': default}
    if max_length is not None:
        schema['maxLength'] = int(max_length)
    return schema


def int_property(description: str, *, default: int, minimum: int = 1, maximum: int = 100) -> Dict[str, Any]:
    return {'type': 'integer', 'description': description, 'default': int(default), 'minimum': int(minimum), 'maximum': int(maximum)}
