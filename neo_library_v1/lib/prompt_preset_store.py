import json
import shutil
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .shared_data_paths import library_data_path
except ImportError:
    from shared_data_paths import library_data_path

EXT_ROOT = Path(__file__).resolve().parents[1]
USER_DATA = library_data_path('', legacy_rel='')
PRESETS_PATH = library_data_path('prompt_presets.json', legacy_rel='prompt_presets.json', default_json={'prompts': []})
ASSETS_DIR = library_data_path('prompt_preset_assets', legacy_rel='prompt_preset_assets')

def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def _ensure():
    USER_DATA.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    if not PRESETS_PATH.exists():
        PRESETS_PATH.write_text(json.dumps({"prompts": []}, indent=2), encoding="utf-8")

def _load() -> Dict[str, Any]:
    try:
        return json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"prompts": []}

def _save(data: Dict[str, Any]):
    tmp = PRESETS_PATH.with_suffix(PRESETS_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.replace(str(tmp), str(PRESETS_PATH))
    except Exception:
        PRESETS_PATH.write_text(tmp.read_text(encoding="utf-8"), encoding="utf-8")

def _safe_ext(p: Path) -> str:
    ext = (p.suffix or "").lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
        return ext
    return ".png"

def _copy_asset(src_path: str, dest_dir: Path, stem: str, index: int = 0) -> str:
    if not src_path:
        return ""
    try:
        src = Path(src_path)
        if not src.exists():
            return ""
        ext = _safe_ext(src)
        name = f"{stem}{'' if index<=0 else f'_{index:02d}'}{ext}"
        dst = dest_dir / name
        k = 2
        while dst.exists():
            name = f"{stem}{'' if index<=0 else f'_{index:02d}'}_{k}{ext}"
            dst = dest_dir / name
            k += 1
        shutil.copy2(src, dst)
        return str(dst)
    except Exception:
        return ""


class PromptPresetStore:
    """Stores prompt presets + optional linked assets in user_data/."""

    def __init__(self):
        _ensure()
        self.data = _load()
        self.data.setdefault("prompts", [])

    def save(self):
        _save(self.data)

    def _normalize_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(item or {})
        out["category"] = str(out.get("category") or "").strip() or "uncategorized"
        out["notes"] = str(out.get("notes") or "")
        out["group"] = str(out.get("group") or "").strip()
        out["favorite"] = bool(out.get("favorite", False))
        out["usage_count"] = int(out.get("usage_count") or 0)
        out["last_used"] = str(out.get("last_used") or "")
        return out

    def list_categories(self) -> List[str]:
        vals = set()
        for p in self.data.get("prompts", []):
            cat = str(p.get("category") or "").strip() or "uncategorized"
            vals.add(cat)
        return sorted(vals, key=str.lower)

    def list_groups(self) -> List[str]:
        vals = {str(p.get("group") or "").strip() for p in self.data.get("prompts", [])}
        return sorted([x for x in vals if x], key=str.lower)

    def list_choices(self, q: str = "", category: str = "all") -> List[Tuple[str, str]]:
        q = (q or "").strip().lower()
        want_cat = (category or "all").strip().lower()
        rows: List[Tuple[Tuple[int, str, str], Tuple[str, str]]] = []
        for p in self.data.get("prompts", []):
            p = self._normalize_item(p)
            pid = p.get("id") or ""
            title = p.get("title") or "Untitled"
            cat = p.get("category") or "uncategorized"
            notes = p.get("notes") or ""
            group = p.get("group") or ""
            if not pid:
                continue
            if want_cat not in {"", "all"} and cat.lower() != want_cat:
                continue
            hay = " | ".join([title, cat, notes, group]).lower()
            if q and q not in hay:
                continue
            prefix = "⭐ " if p.get("favorite") else ""
            group_txt = f" · {group}" if group else ""
            label = f"{prefix}[{cat}] {title}{group_txt}"
            sort_key = (0 if p.get("favorite") else 1, (group or "").lower(), title.lower())
            rows.append((sort_key, (label, pid)))
        rows.sort(key=lambda item: item[0])
        return [row for _, row in rows]

    def get(self, pid: str) -> Optional[Dict[str, Any]]:
        for p in self.data.get("prompts", []):
            if p.get("id") == pid:
                return self._normalize_item(p)
        return None

    def upsert(
        self,
        pid: str,
        title: str,
        positive: str,
        negative: str,
        linked: Dict[str, Any],
        cn_routing: Dict[str, Any],
        strengths: Dict[str, Any],
        assets: Optional[Dict[str, Any]] = None,
        category: str = "uncategorized",
        notes: str = "",
        group: str = "",
        favorite: bool = False,
    ) -> Optional[str]:
        title = (title or "").strip()
        if not title:
            return None

        item = self.get(pid) if pid else None
        if item is None:
            pid = str(uuid.uuid4())
            item = {"id": pid, "created": _now_iso(), "usage_count": 0, "last_used": "", "favorite": False, "group": ""}
            self.data.setdefault("prompts", []).append(item)

        assets_dir = ASSETS_DIR / pid
        assets_dir.mkdir(parents=True, exist_ok=True)
        copied_assets: Dict[str, Any] = {}
        if assets:
            maps = (assets.get("maps") or {}) if isinstance(assets, dict) else {}
            comp = (assets.get("composition") or []) if isinstance(assets, dict) else []
            refs = (assets.get("reference") or []) if isinstance(assets, dict) else []
            copied_maps = {
                "canny": _copy_asset(maps.get("canny", ""), assets_dir, "map_canny"),
                "depth": _copy_asset(maps.get("depth", ""), assets_dir, "map_depth"),
                "openpose": _copy_asset(maps.get("openpose", ""), assets_dir, "map_openpose"),
            }
            copied_comp = []
            for i, pth in enumerate(comp, start=1):
                cp = _copy_asset(pth, assets_dir, "composition", i)
                if cp:
                    copied_comp.append(cp)
            copied_refs = []
            for i, pth in enumerate(refs, start=1):
                rp = _copy_asset(pth, assets_dir, "reference", i)
                if rp:
                    copied_refs.append(rp)
            copied_assets = {"maps": copied_maps, "composition": copied_comp, "reference": copied_refs}

        item.update({
            "title": title,
            "positive": positive or "",
            "negative": negative or "",
            "category": (category or "").strip() or "uncategorized",
            "notes": notes or "",
            "group": (group or "").strip(),
            "favorite": bool(favorite),
            "linked": linked or {},
            "cn_routing": cn_routing or {"unit0": "canny", "unit1": "depth", "unit2": "openpose"},
            "strengths": strengths or {"canny": 1.0, "depth": 1.0, "openpose": 1.0},
            "assets": copied_assets if assets else (item.get("assets") or {}),
            "updated": _now_iso(),
        })
        self.save()
        return pid

    def mark_used(self, pid: str) -> Optional[Dict[str, Any]]:
        item = self.get(pid)
        if not item:
            return None
        item["usage_count"] = int(item.get("usage_count") or 0) + 1
        item["last_used"] = _now_iso()
        item["updated"] = _now_iso()
        for idx, p in enumerate(self.data.get("prompts", [])):
            if p.get("id") == pid:
                self.data["prompts"][idx] = item
                break
        self.save()
        return item

    def duplicate(self, pid: str, new_title: str = "") -> Optional[str]:
        item = self.get(pid)
        if not item:
            return None
        title = (new_title or f"{item.get('title') or 'Preset'} Copy").strip()
        return self.upsert(
            "",
            title,
            item.get("positive") or "",
            item.get("negative") or "",
            item.get("linked") or {},
            item.get("cn_routing") or {},
            item.get("strengths") or {},
            assets=item.get("assets") or {},
            category=item.get("category") or "uncategorized",
            notes=item.get("notes") or "",
            group=item.get("group") or "",
            favorite=False,
        )

    def toggle_favorite(self, pid: str) -> Optional[bool]:
        item = self.get(pid)
        if not item:
            return None
        item["favorite"] = not bool(item.get("favorite"))
        item["updated"] = _now_iso()
        for idx, p in enumerate(self.data.get("prompts", [])):
            if p.get("id") == pid:
                self.data["prompts"][idx] = item
                break
        self.save()
        return bool(item["favorite"])

    def compare(self, pid_a: str, pid_b: str) -> Dict[str, Any]:
        a = self.get(pid_a) or {}
        b = self.get(pid_b) or {}
        if not a or not b:
            return {"ok": False, "message": "Select two saved prompts to compare."}
        fields = ["title", "category", "group", "notes", "positive", "negative"]
        diffs = []
        for key in fields:
            va = a.get(key) or ""
            vb = b.get(key) or ""
            if va != vb:
                diffs.append({"field": key, "a": va, "b": vb})
        return {"ok": True, "title_a": a.get("title") or "A", "title_b": b.get("title") or "B", "differences": diffs}

    def export_one(self, pid: str) -> Dict[str, Any]:
        item = self.get(pid) or {}
        if not item:
            raise ValueError("Preset not found.")
        return {"schema_version": 1, "exported_at": _now_iso(), "prompt_preset": item}

    def delete(self, pid: str):
        self.data["prompts"] = [p for p in self.data.get("prompts", []) if p.get("id") != pid]
        self.save()

    def maybe_migrate_legacy(self):
        marker = USER_DATA / ".legacy_prompt_presets_migrated_v1"
        if marker.exists():
            return
        legacy_lib = EXT_ROOT / "data" / "library.json"
        if not legacy_lib.exists():
            marker.write_text("no legacy", encoding="utf-8")
            return
        try:
            legacy = json.loads(legacy_lib.read_text(encoding="utf-8"))
        except Exception:
            marker.write_text("bad legacy", encoding="utf-8")
            return
        prompts = legacy.get("prompts", []) or []
        if not prompts:
            marker.write_text("empty", encoding="utf-8")
            return
        if self.data.get("prompts"):
            marker.write_text("skipped - already has presets", encoding="utf-8")
            return
        for lp in prompts:
            title = lp.get("title") or "Legacy Prompt"
            pos = lp.get("prompt") or ""
            neg = lp.get("negative") or ""
            self.upsert(
                "",
                title + " (legacy)",
                pos,
                neg,
                {"mapset_id": ""},
                {"unit0": "canny", "unit1": "depth", "unit2": "openpose"},
                {"canny": 1.0, "depth": 1.0, "openpose": 1.0},
            )
        marker.write_text("done", encoding="utf-8")
