import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

try:
    from .shared_data_paths import library_data_path
except ImportError:
    from shared_data_paths import library_data_path


def _ext_root() -> str:
    here = os.path.dirname(__file__)
    return os.path.abspath(os.path.join(here, ".."))


def _user_data_dir() -> str:
    return str(library_data_path('', legacy_rel=''))


def _usage_path() -> str:
    return str(library_data_path('usage_store.json', legacy_rel='usage_store.json', default_json={}))


def _load_json(path: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback


def _save_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        os.replace(tmp, path)
    except Exception:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


@dataclass
class UsageItem:
    label: str
    value: str


class UsageStore:
    """Keeps lightweight UI state: recents + favorites (separate from vault_db)."""

    def __init__(self):
        self.path = _usage_path()
        self.data = _load_json(self.path, {"recents": [], "favorites": [], "typed_recents": {}, "typed_favorites": {}})
        self.data.setdefault("recents", [])
        self.data.setdefault("favorites", [])
        self.data.setdefault("typed_recents", {})
        self.data.setdefault("typed_favorites", {})

    def save(self) -> None:
        _save_json(self.path, self.data)

    def _norm_kind(self, kind: str) -> str:
        return (kind or "").strip().lower() or "misc"

    def _typed_list(self, bucket: str, kind: str) -> List[Dict[str, str]]:
        kind = self._norm_kind(kind)
        store = self.data.get(bucket)
        if not isinstance(store, dict):
            store = {}
            self.data[bucket] = store
        vals = store.get(kind)
        if not isinstance(vals, list):
            vals = []
            store[kind] = vals
        return vals

    def add_recent(self, label: str, value: str, max_items: int = 30) -> None:
        if not value:
            return
        label = (label or "").strip() or value
        rec = [x for x in (self.data.get("recents") or []) if x.get("value") != value]
        rec.insert(0, {"label": label, "value": value})
        self.data["recents"] = rec[:max_items]
        self.save()

    def add_recent_typed(self, kind: str, label: str, value: str, max_items: int = 20) -> None:
        if not value:
            return
        label = (label or "").strip() or value
        rec = [x for x in self._typed_list("typed_recents", kind) if x.get("value") != value]
        rec.insert(0, {"label": label, "value": value})
        self.data["typed_recents"][self._norm_kind(kind)] = rec[:max_items]
        self.save()

    def toggle_favorite(self, label: str, value: str, max_items: int = 200) -> bool:
        if not value:
            return False
        label = (label or "").strip() or value
        fav = self.data.get("favorites") or []
        exists = any(x.get("value") == value for x in fav)
        if exists:
            fav = [x for x in fav if x.get("value") != value]
            self.data["favorites"] = fav
            self.save()
            return False
        fav.append({"label": label, "value": value})
        self.data["favorites"] = fav[-max_items:]
        self.save()
        return True

    def toggle_favorite_typed(self, kind: str, label: str, value: str, max_items: int = 100) -> bool:
        if not value:
            return False
        label = (label or "").strip() or value
        fav = self._typed_list("typed_favorites", kind)
        exists = any(x.get("value") == value for x in fav)
        if exists:
            fav = [x for x in fav if x.get("value") != value]
            self.data["typed_favorites"][self._norm_kind(kind)] = fav
            self.save()
            return False
        fav.append({"label": label, "value": value})
        self.data["typed_favorites"][self._norm_kind(kind)] = fav[-max_items:]
        self.save()
        return True

    def choices_recents(self) -> List[Tuple[str, str]]:
        return [(x.get("label") or x.get("value") or "", x.get("value") or "") for x in (self.data.get("recents") or []) if x.get("value")]

    def choices_favorites(self) -> List[Tuple[str, str]]:
        return [(x.get("label") or x.get("value") or "", x.get("value") or "") for x in (self.data.get("favorites") or []) if x.get("value")]

    def choices_recents_typed(self, kind: str) -> List[Tuple[str, str]]:
        return [(x.get("label") or x.get("value") or "", x.get("value") or "") for x in self._typed_list("typed_recents", kind) if x.get("value")]

    def choices_favorites_typed(self, kind: str) -> List[Tuple[str, str]]:
        return [(x.get("label") or x.get("value") or "", x.get("value") or "") for x in self._typed_list("typed_favorites", kind) if x.get("value")]
