from __future__ import annotations

from typing import Any, Dict, List, Tuple

import gradio as gr

from usage_store import UsageStore
from vault_store import VaultStore

_PROMPT_COMPOSER_LORA_REFS: Dict[str, Any] = {}


def register_prompt_composer_lora_refs(**refs):
    _PROMPT_COMPOSER_LORA_REFS.clear()
    _PROMPT_COMPOSER_LORA_REFS.update(refs)


def get_prompt_composer_lora_refs() -> Dict[str, Any]:
    return dict(_PROMPT_COMPOSER_LORA_REFS)


def _choice_values(choices) -> List[str]:
    vals: List[str] = []
    for item in list(choices or []):
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            vals.append(str(item[1]))
        else:
            vals.append(str(item))
    return vals


def _keywords_markdown(it: dict) -> str:
    kw = it.get("keywords") or []
    bits = []
    if kw:
        bits.append("**Keywords:** " + ", ".join(kw))
    if it.get("base_model"):
        bits.append(f"**Base:** {it.get('base_model')}")
    if it.get("caution_notes"):
        bits.append(f"**Caution:** {it.get('caution_notes')}")
    dup = it.get("duplicate_with") or []
    if dup:
        bits.append("**Duplicate triggers:** " + ", ".join(dup[:8]))
    return "  \n".join(bits)


def prompt_composer_lora_refresh(kind: str = "lora", q: str = "", current_id: str | None = None, status: str = ""):
    s = VaultStore()
    kind = str(kind or "lora").strip().lower() or "lora"
    q = str(q or "")
    choices = s.list_lora_choices(q=q, kind=kind)
    values = set(_choice_values(choices))
    selected = str(current_id or "").strip() or None
    if selected not in values:
        selected = None
    dd_update = gr.update(choices=choices, value=selected)
    recent_update = gr.update(choices=UsageStore().choices_recents_typed(kind), value=None)
    if not selected:
        msg = status or "✅ Quick insert refreshed."
        return (
            dd_update,
            recent_update,
            "",
            "",
            0.8,
            gr.update(choices=[], value=[]),
            "",
            "",
            "",
            None,
            msg,
        )
    it = s.get_lora_prefill(selected) or {}
    trig = it.get("triggers") or []
    strength = float(it.get("default_strength") or 1.0)
    msg = status or "✅ Quick insert refreshed."
    return (
        dd_update,
        recent_update,
        it.get("file", ""),
        it.get("rel", ""),
        strength,
        gr.update(choices=trig, value=[]),
        _keywords_markdown(it),
        it.get("example_prompt", ""),
        s.build_lora_insert_block(selected, strength=strength, include_triggers=True),
        (it.get("preview_image") or None),
        msg,
    )
