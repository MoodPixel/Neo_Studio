from __future__ import annotations

import json
from pathlib import Path

from .config import ROOT_DIR

GOAL_MAP_PATH = ROOT_DIR / 'neo_studio_v1' / 'docs' / 'phase01_generation_goal_map.json'


def load_phase01_goal_map() -> dict:
    try:
        return json.loads(GOAL_MAP_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {'version': 1, 'phase': 'phase1_canonical_journeys', 'journeys': {}}


__all__ = ['load_phase01_goal_map', 'GOAL_MAP_PATH']
