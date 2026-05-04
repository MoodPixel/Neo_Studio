from __future__ import annotations

from typing import Any

from .roleplay_v2_breakdown_helper import get_breakdown_output, save_breakdown_review


def approve_breakdown(helper_output_id: str, *, review_notes: str = '') -> dict[str, Any]:
    return save_breakdown_review(helper_output_id=helper_output_id, approved=True, review_notes=review_notes)



def update_breakdown(helper_output_id: str, *, cleaned_text: str = '', structured_payload: dict[str, Any] | None = None, approved: bool = False, review_notes: str = '') -> dict[str, Any]:
    return save_breakdown_review(
        helper_output_id=helper_output_id,
        cleaned_text=cleaned_text,
        structured_payload=structured_payload,
        approved=approved,
        review_notes=review_notes,
    )



def get_review_target(helper_output_id: str) -> dict[str, Any] | None:
    return get_breakdown_output(helper_output_id)
