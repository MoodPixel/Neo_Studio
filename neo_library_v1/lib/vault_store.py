
import json
import os
import re
import shutil
import uuid
import unicodedata
import hashlib
import html
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# -------------------------------------------------------
# VaultStore (Prompt Suite)
# - Stores keywords / mapsets / assets
# - Persists to user_data/ so updates won't wipe data
# -------------------------------------------------------

try:
    from .shared_data_paths import library_data_path
except ImportError:
    from shared_data_paths import library_data_path

EXT_ROOT = Path(__file__).resolve().parents[1]
USER_DATA = library_data_path('', legacy_rel='')
VAULT_DB_PATH = library_data_path('vault_db.json', legacy_rel='vault_db.json', default_json={"tags": [], "packs": [], "mapsets": [], "loras": []})
ASSETS_DIR = library_data_path('assets', legacy_rel='assets')  # assets/<mapset_id>/<type>/*.png
LORA_PREVIEW_CACHE_DIR = library_data_path('lora_previews', legacy_rel='lora_previews')

# LoRA/TI registry storage lives in the same vault DB under the key "loras".
# Each entry example:
# {
#   "id": "...", "kind": "lora"|"ti",
#   "file": "C:/.../models/Lora/foo.safetensors",
#   "rel": "subfolder/foo", "name": "foo", "category": "subfolder",
#   "triggers": ["trigger1", "trigger2"],
#   "keywords": ["style", "subject"],
#   "default_strength": 0.8,
#   "notes": "...",
#   "created": "...", "updated": "...",
# }

_MAP_TYPES = ("canny", "depth", "openpose")
_LORA_EXTS = (".safetensors", ".pt", ".ckpt")
_EMBED_EXTS = (".pt", ".safetensors")


def _infer_lora_base_model_hint(*values: Any) -> str:
    hay = ' '.join(str(v or '') for v in values if str(v or '').strip())
    norm = _norm_token(hay)
    if not norm:
        return ''
    qwen_tokens = (
        'qwen image edit', 'qwen-image-edit', 'qwen image', 'qwen-image',
        'qwen2.5-vl', 'qwen 2.5 vl', 'qwen vl', 'qwen-image-edit-2509',
        'qwen-image-edit-2511', 'qwen image edit 2509', 'qwen image edit 2511',
    )
    if any(tok in norm for tok in qwen_tokens) or norm.startswith('qwen'):
        return 'Qwen Image Edit'
    if 'flux' in norm:
        return 'Flux'
    if 'sdxl' in norm or re.search(r'(^|[^a-z])xl([^a-z]|$)', norm):
        return 'SDXL'
    if any(tok in norm for tok in ('sd 1.5', 'sd1.5', 'v1-5', 'stable diffusion 1.5')):
        return 'SD 1.5'
    return ''

def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def _ensure_dirs():
    USER_DATA.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    LORA_PREVIEW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not VAULT_DB_PATH.exists():
        VAULT_DB_PATH.write_text(json.dumps({"tags": [], "packs": [], "mapsets": [], "loras": []}, indent=2), encoding="utf-8")


# ---------------- Built-in library import ----------------
_LIB_DIR = EXT_ROOT / "libraries"

_NUM_ITEM = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")
_BULLET_ITEM = re.compile(r"^\s*-\s+(.*\S)\s*$")
_H1 = re.compile(r"^\s*#\s+(.*\S)\s*$")
_H2 = re.compile(r"^\s*##\s+(.*\S)\s*$")
_TAG = re.compile(r"\[([A-Za-z0-9_+-]+)\]")

def _infer_category_from_filename(name: str) -> str:
    n = (name or "").lower()
    if "outfit" in n or "streetwear" in n:
        return "clothing"
    if "hair" in n:
        return "clothing"
    if "location" in n:
        return "location"
    if "pose" in n:
        return "pose"
    if "moment" in n:
        return "moment"
    return "misc"

def _clean_item_text(s: str) -> Tuple[str, List[str]]:
    """Return (main_text, bracket_tags)."""
    raw = (s or "").strip()
    tags = _TAG.findall(raw) if raw else []
    # strip bracket tags from the line
    main = _TAG.sub("", raw).strip()
    main = re.sub(r"\s{2,}", " ", main).strip()
    # remove trailing markdown line breaks
    main = main.rstrip(" -–—")
    return main, tags

def _maybe_import_builtin_libraries(data: Dict[str, Any]) -> bool:
    """
    One-time import:
    - Each .md file becomes one or more packs (per ## section if present)
    - List items become tag entries
    Returns True if it modified data.
    """
    try:
        if data.get("_builtin_import_v1") is True:
            return False
        if not _LIB_DIR.exists():
            data["_builtin_import_v1"] = True
            return False
    except Exception:
        return False

    tags = data.get("tags") or []
    packs = data.get("packs") or []

    # Index existing tags by normalized key to avoid duplicates
    seen = set()
    for t in tags:
        cat = (t.get("category") or "misc").strip()
        name = (t.get("name") or "").strip()
        if name:
            seen.add((_norm_token(cat), _norm_token(name)))

    def upsert_tag(cat: str, name: str, aliases: List[str], desc: str = "") -> str:
        c = (cat or "misc").strip()
        n = (name or "").strip()
        if not n:
            return ""
        key = (_norm_token(c), _norm_token(n))
        if key in seen:
            # find existing id
            for t in tags:
                if _norm_token(t.get("category") or "misc") == key[0] and _norm_token(t.get("name") or "") == key[1]:
                    return t.get("id") or ""
            return ""
        tid = str(uuid.uuid4())
        seen.add(key)
        # add underscore alias to help booru-style matching
        alias_set = set([a.strip() for a in (aliases or []) if a.strip()])
        alias_set.add(re.sub(r"\s+", "_", n.lower()))
        tags.append({
            "id": tid,
            "category": c,
            "name": n,
            "aliases": sorted(alias_set),
            "desc": desc or "",
            "enabled": True,
            "created": _now_iso(),
            "updated": _now_iso(),
            "_source": "builtin_md",
        })
        return tid

    def upsert_pack(cat: str, title: str, tag_ids: List[str]):
        if not title or not tag_ids:
            return
        # Avoid exact duplicate pack titles (same cat/title)
        for p in packs:
            if _norm_token(p.get("category") or "misc") == _norm_token(cat) and _norm_token(p.get("title") or "") == _norm_token(title):
                return
        packs.append({
            "id": str(uuid.uuid4()),
            "category": (cat or "misc").strip(),
            "title": title.strip(),
            "tag_ids": [tid for tid in tag_ids if tid],
            "created": _now_iso(),
            "updated": _now_iso(),
            "_source": "builtin_md",
        })

    # Parse every .md
    for md in sorted(_LIB_DIR.glob("*.md")):
        base = md.stem.strip()
        cat = _infer_category_from_filename(md.name)
        cur_section = ""
        section_items: Dict[str, List[str]] = {}
        try:
            text = md.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue

        for line in text:
            if _H2.match(line):
                cur_section = _H2.match(line).group(1).strip()
                continue
            if _H1.match(line):
                # ignore H1 as section; we use filename
                continue
            m = _NUM_ITEM.match(line) or _BULLET_ITEM.match(line)
            if not m:
                continue
            item_raw = m.group(2) if isinstance(m, re.Match) and m.re == _NUM_ITEM else m.group(1)
            item_raw = (item_raw or "").strip()
            if not item_raw:
                continue
            main, bt = _clean_item_text(item_raw)
            if not main:
                continue
            sec_key = cur_section or base
            section_items.setdefault(sec_key, []).append((main, bt))

        # Create tags + packs
        for sec, items in section_items.items():
            tag_ids = []
            # Pack title: "File — Section" if section differs
            pack_title = base if sec == base else f"{base} — {sec}"
            for main, bt in items:
                tid = upsert_tag(cat, main, bt, "")
                if tid:
                    tag_ids.append(tid)
            if tag_ids:
                upsert_pack(cat, pack_title, tag_ids)

    data["tags"] = tags
    data["packs"] = packs
    data["_builtin_import_v1"] = True
    return True


def _load_json(path: Path, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback

def _save_json(path: Path, data: Dict[str, Any]) -> None:
    """Atomic-ish save to avoid corrupting vault_db on crash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.replace(str(tmp), str(path))
    except Exception:
        # Fallback (non-atomic) if replace fails on some FS.
        path.write_text(tmp.read_text(encoding="utf-8"), encoding="utf-8")

def _safe_name(s: str, max_len: int = 120) -> str:
    s = (s or "").strip()
    s = re.sub(r"[^a-zA-Z0-9._ -]+", "_", s)
    return (s[:max_len] or "Untitled")

def _norm_token(s: str) -> str:
    """Canonical token for matching/lookup (case + spacing/punctuation tolerant)."""
    s = unicodedata.normalize("NFKC", (s or "").strip())
    s = s.casefold()
    # treat space/_/- as similar
    s = re.sub(r"[\s_\-–—]+", "", s)
    # drop punctuation but keep word chars across languages
    s = re.sub(r"[^\w]+", "", s, flags=re.UNICODE)
    return s

def _guess_map_type(filename: str) -> Optional[str]:
    n = filename.lower()
    if "canny" in n:
        return "canny"
    if "depth" in n:
        return "depth"
    if "openpose" in n or re.search(r"(^|[_-])pose([_-]|\.)", n):
        return "openpose"
    return None


def _prompt_token_ref(it: Dict[str, Any]) -> str:
    kind = str((it or {}).get("kind") or "lora").strip().lower()
    name = str((it or {}).get("name") or "").strip()
    rel = str((it or {}).get("rel") or name or "").strip()
    if kind == "ti":
        return rel or name
    return name or (rel.split("/")[-1].strip() if rel else "")


def _try_get_default_dirs() -> Tuple[Optional[str], Optional[str]]:
    """Best-effort (Forge/A1111) default directories for LoRA and embeddings."""
    lora_dir = None
    emb_dir = None
    try:
        # A1111 style
        from modules import paths  # type: ignore
        models_path = getattr(paths, "models_path", None)
        if models_path and os.path.isdir(models_path):
            cand = os.path.join(models_path, "Lora")
            if os.path.isdir(cand):
                lora_dir = cand
        # Embeddings live at repo root typically
        sd_path = getattr(paths, "script_path", None)
        if sd_path and os.path.isdir(sd_path):
            cand = os.path.join(sd_path, "embeddings")
            if os.path.isdir(cand):
                emb_dir = cand
    except Exception:
        pass

    try:
        # cmd opts override
        from modules import shared  # type: ignore
        co = getattr(shared, "cmd_opts", None)
        if co is not None:
            ld = getattr(co, "lora_dir", None)
            if ld and os.path.isdir(ld):
                lora_dir = ld
            ed = getattr(co, "embeddings_dir", None)
            if ed and os.path.isdir(ed):
                emb_dir = ed
    except Exception:
        pass

    return lora_dir, emb_dir

def _ensure_suffix(stem: str, map_type: str) -> str:
    # enforce suffix for auto-detect in other tools
    st = stem
    st_low = st.lower()
    suf = f"_{map_type}"
    if st_low.endswith(suf):
        return st
    # avoid double suffixes like _canny_depth
    for t in _MAP_TYPES:
        if st_low.endswith(f"_{t}"):
            return st
    return f"{st}{suf}"

class VaultStore:
    def __init__(self):
        _ensure_dirs()
        # Vault DB is still used for MapSets + LoRA/TI meta.
        # Keywords/Packs are library (.md) driven in CLEAN mode.
        self.data = _load_json(VAULT_DB_PATH, {"mapsets": [], "loras": [], "tags": [], "packs": []})
        self.data.setdefault("mapsets", [])
        self.data.setdefault("loras", [])
        # keep minimal keys for compatibility
        self.data.setdefault("tags", [])
        self.data.setdefault("packs", [])
        self._lib_dir = _LIB_DIR

    def save(self):
        _save_json(VAULT_DB_PATH, self.data)


    # ------------------ Library (Keywords / Packs) ------------------
    def _slug_category(self, name: str) -> str:
        name = (name or "").strip()
        if not name:
            return ""
        name = unicodedata.normalize("NFKC", name).casefold()
        name = re.sub(r"[\s\-–—]+", "_", name)
        name = re.sub(r"[^a-z0-9_]+", "", name)
        name = re.sub(r"_+", "_", name).strip("_")
        return name

    def _parse_lib_filename(self, filename: str) -> Optional[Tuple[str, str]]:
        # Expected: <category>__keywords*.md OR <category>__packs*.md
        stem = Path(filename).stem
        parts = stem.split("__")
        if len(parts) < 2:
            return None
        cat = (parts[0] or "").strip()
        kind = (parts[1] or "").strip().casefold()
        if kind not in ("keywords", "packs", "bases"):
            return None
        if not cat:
            return None
        return cat, kind

    def _iter_lib_files(self, kind: str) -> List[Path]:
        kind = (kind or "").strip().casefold()
        if not self._lib_dir.exists():
            return []
        out = []
        for p in sorted(self._lib_dir.glob("*.md")):
            info = self._parse_lib_filename(p.name)
            if not info:
                continue
            cat, k = info
            if k == kind:
                out.append(p)
        return out

    def _kw_id(self, category: str, subcategory: str, canonical: str) -> str:
        return f"kw::{(category or 'misc')}::{(subcategory or 'general')}::{_norm_token(canonical)}"

    def _parse_keyword_lib_filename(self, filename: str) -> Optional[Tuple[str, str]]:
        """Support legacy keyword-library file naming patterns.

        Accepted examples:
        - <category>__keywords__<subcategory>.md
        - <category>__keywords.md
        - <category>__<subcategory>.md
        - <category>__<section>__<subcategory>__<rating>.md

        The old Neo Library keyword libraries often used 3+ path segments such as
        ``Male__Hair__Color__Any_Safe.md``. Those should still be treated as
        keyword sources, with the first token as the broad category and the
        remaining tokens kept together as the subcategory label.
        """
        stem = Path(filename).stem
        parts = [x.strip() for x in stem.split("__") if x.strip()]
        if len(parts) >= 3 and (parts[1] or '').strip().casefold() == 'keywords':
            return parts[0], '__'.join(parts[2:]).strip() or 'general'
        if len(parts) >= 2 and (parts[-1] or '').strip().casefold() == 'keywords':
            cat = '__'.join(parts[:-1]).strip()
            return (cat, 'general') if cat else None
        if len(parts) >= 2:
            # Preserve old multi-part library names like
            # Male__Body__Skin__Any_Safe.md without treating pack/base files
            # as keyword libraries.
            if (parts[1] or '').strip().casefold() in ('packs', 'bases'):
                return None
            cat = parts[0]
            sub = '__'.join(parts[1:]).strip() or 'general'
            return (cat, sub) if cat else None
        return None

    def list_keyword_categories(self) -> List[str]:
        cats = set()
        if not self._lib_dir.exists():
            return []
        for p in sorted(self._lib_dir.glob('*.md')):
            info = self._parse_keyword_lib_filename(p.name)
            if info:
                cats.add(info[0])
        return sorted(cats)

    def list_keyword_subcategories(self, category: str = 'all') -> List[str]:
        cn = _norm_token(category)
        subs = set()
        if not self._lib_dir.exists():
            return []
        for p in sorted(self._lib_dir.glob('*.md')):
            info = self._parse_keyword_lib_filename(p.name)
            if not info:
                continue
            cat, sub = info
            if cn and cn not in ('all', '*') and _norm_token(cat) != cn:
                continue
            subs.add(sub)
        return sorted(subs)

    # ------------------ Categories ------------------
    def list_categories(self, kinds: Optional[List[str]] = None) -> List[str]:
        """List categories present in library .md files.

        Args:
            kinds: Optional list of kinds to include. Supported: keywords, packs, bases.
                   If None/empty, includes all.
        """
        if kinds is None:
            kinds_list: List[str] = ["keywords", "packs", "bases"]
        elif isinstance(kinds, str):  # type: ignore
            kinds_list = [kinds]  # type: ignore
        else:
            kinds_list = list(kinds)

        # normalize + filter
        k_norm: List[str] = []
        for k in kinds_list:
            kk = (k or "").strip().casefold()
            if kk in ("keywords", "packs", "bases") and kk not in k_norm:
                k_norm.append(kk)
        if not k_norm:
            k_norm = ["keywords", "packs", "bases"]

        cats = set()
        for kk in k_norm:
            for p in self._iter_lib_files(kk):
                info = self._parse_lib_filename(p.name)
                if info:
                    cats.add(info[0])
        return sorted(cats)

    def add_category(self, name: str) -> bool:
        cat = self._slug_category(name) or (name or '').strip()
        if not cat:
            return False
        self._lib_dir.mkdir(parents=True, exist_ok=True)
        kw_path = self._lib_dir / f"{cat}__general.md"
        if kw_path.exists():
            return False
        kw_path.write_text("", encoding="utf-8")
        return True

    # ------------------ Keywords (compat: Tags) ------------------
    def _parse_keyword_line(self, line: str) -> Optional[Dict[str, Any]]:
        raw = (line or "").strip()
        if not raw:
            return None
        if raw.startswith("#") or raw.startswith("//"):
            return None
        parts = [p.strip() for p in raw.split("|") if p.strip()]
        if not parts:
            return None
        canonical = parts[0]
        meta = {"aliases": [], "desc": "", "enabled": True}
        for seg in parts[1:]:
            if ":" not in seg:
                continue
            k, v = seg.split(":", 1)
            k = (k or "").strip().casefold()
            v = (v or "").strip()
            if k in ("alias", "aliases"):
                meta["aliases"] = [a.strip() for a in v.split(",") if a.strip()]
            elif k in ("desc", "description"):
                meta["desc"] = v
            elif k in ("enabled", "enable"):
                vv = v.casefold()
                meta["enabled"] = vv not in ("0", "false", "no", "off")
        return {"name": canonical, **meta}

    def _load_keywords(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        if not self._lib_dir.exists():
            return out
        for p in sorted(self._lib_dir.glob("*.md")):
            info = self._parse_keyword_lib_filename(p.name)
            if not info:
                continue
            cat, sub = info
            try:
                lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            for line in lines:
                rec = self._parse_keyword_line(line)
                if not rec:
                    continue
                kid = self._kw_id(cat, sub, rec["name"])
                if kid in out:
                    continue
                out[kid] = {
                    "id": kid,
                    "category": cat,
                    "subcategory": sub,
                    "name": rec["name"],
                    "aliases": rec.get("aliases") or [],
                    "desc": rec.get("desc") or "",
                    "enabled": bool(rec.get("enabled", True)),
                    "source_file": str(p),
                }
        return out

    def list_tag_choices(self, q: str = "", category: str = "all", subcategory: str = "all") -> List[Tuple[str, str]]:
        # Back-compat name: "tags" = keywords
        qn = _norm_token(q)
        cn = _norm_token(category)
        sn = _norm_token(subcategory)
        kws = self._load_keywords()
        out: List[Tuple[str, str]] = []
        for kid, k in kws.items():
            cat = k.get("category") or "misc"
            sub = k.get("subcategory") or "general"
            name = k.get("name") or ""
            if not name:
                continue
            if cn and cn not in ("all", "*") and _norm_token(cat) != cn:
                continue
            if sn and sn not in ("all", "*") and _norm_token(sub) != sn:
                continue
            label = name if cn not in ("", "all", "*") and sn not in ("", "all", "*") else f"{cat} › {sub} › {name}"
            if qn:
                hay = _norm_token(label + " " + " ".join(k.get("aliases") or []) + " " + (k.get("desc") or ""))
                if qn not in hay:
                    continue
            out.append((label, kid))
        return out

    def get_tag(self, tid: str) -> Optional[Dict[str, Any]]:
        kws = self._load_keywords()
        return kws.get(tid)

    def _keywords_primary_file(self, category: str, subcategory: str = "general", preferred: str = "") -> Path:
        self._lib_dir.mkdir(parents=True, exist_ok=True)
        category = (category or "misc").strip() or "misc"
        subcategory = (subcategory or "general").strip() or "general"
        if preferred:
            pp = Path(preferred)
            info = self._parse_keyword_lib_filename(pp.name)
            if info and _norm_token(info[0]) == _norm_token(category) and _norm_token(info[1]) == _norm_token(subcategory):
                return pp
        return self._lib_dir / f"{category}__{subcategory}.md"

    def _write_keywords_for_category(self, category: str, subcategory: str, keywords: List[Dict[str, Any]], preferred: str = "") -> None:
        p = self._keywords_primary_file(category, subcategory, preferred=preferred)
        lines = []
        for k in sorted(keywords, key=lambda x: (x.get("name") or "").casefold()):
            name = (k.get("name") or "").strip()
            if not name:
                continue
            segs = [name]
            aliases = [a.strip() for a in (k.get("aliases") or []) if a.strip()]
            if aliases:
                segs.append("alias:" + ",".join(aliases))
            desc = (k.get("desc") or "").strip()
            if desc:
                segs.append("desc:" + desc)
            enabled = bool(k.get("enabled", True))
            if not enabled:
                segs.append("enabled:false")
            lines.append(" | ".join(segs))
        txt = "\n".join(lines) + ("\n" if lines else "")
        bak = p.with_suffix(p.suffix + ".bak")
        tmp = p.with_suffix(p.suffix + ".tmp")
        try:
            if p.exists():
                shutil.copy2(p, bak)
        except Exception:
            pass
        tmp.write_text(txt, encoding="utf-8")
        os.replace(str(tmp), str(p))

    def _propagate_keyword_rename_in_packs(self, old_cat: str, old_name: str, new_cat: str, new_name: str):
        old_norm = _norm_token(old_name)
        for pf in self._iter_lib_files("packs"):
            try:
                txt = pf.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            blocks = self._parse_pack_blocks(txt, source_file=str(pf))
            changed = False
            for b in blocks:
                kws = b.get("keywords_raw") or []
                new_list = []
                for token in kws:
                    cat, nm = self._split_kw_token(token)
                    if _norm_token(nm) == old_norm and (not cat or _norm_token(cat) == _norm_token(old_cat)):
                        new_list.append(f"{new_cat}::{new_name}")
                        changed = True
                    else:
                        new_list.append(token)
                b["keywords_raw"] = new_list
            if changed:
                self._write_pack_blocks_to_file(pf, blocks)

    def upsert_tag(self, tid: str, category: str, subcategory: str, name: str, aliases_csv: str, desc: str, enabled: bool) -> Optional[str]:
        name = (name or "").strip()
        if not name:
            return None
        category0 = (category or "").strip() or "misc"
        subcategory0 = (subcategory or "").strip() or "general"
        aliases = [a.strip() for a in (aliases_csv or "").split(",") if a.strip()]

        old = self.get_tag(tid) if tid else None
        old_cat = old.get("category") if old else None
        old_sub = old.get("subcategory") if old else None
        old_name = old.get("name") if old else None
        old_source = old.get("source_file") if old else ""

        def load_primary(cat: str, sub: str, preferred: str = "") -> List[Dict[str, Any]]:
            p = self._keywords_primary_file(cat, sub, preferred=preferred)
            if not p.exists():
                return []
            items = []
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                rec = self._parse_keyword_line(line)
                if not rec:
                    continue
                items.append({"name": rec["name"], "aliases": rec.get("aliases") or [], "desc": rec.get("desc") or "", "enabled": bool(rec.get("enabled", True))})
            return items

        groups = {(category0, subcategory0): load_primary(category0, subcategory0, preferred=old_source if old_cat == category0 and old_sub == subcategory0 else "")}
        if old_cat and old_sub:
            groups[(old_cat, old_sub)] = load_primary(old_cat, old_sub, preferred=old_source)

        if old_cat and old_sub and old_name:
            old_norm = _norm_token(old_name)
            groups[(old_cat, old_sub)] = [k for k in groups.get((old_cat, old_sub), []) if _norm_token(k.get("name","")) != old_norm]

        new_norm = _norm_token(name)
        kept = [k for k in groups.get((category0, subcategory0), []) if _norm_token(k.get("name","")) != new_norm]
        kept.append({"name": name, "aliases": aliases, "desc": desc or "", "enabled": bool(enabled)})
        groups[(category0, subcategory0)] = kept

        for (c, s), items in groups.items():
            pref = old_source if old_cat == c and old_sub == s else ""
            self._write_keywords_for_category(c, s, items, preferred=pref)

        return self._kw_id(category0, subcategory0, name)

    def delete_tag(self, tid: str):
        k = self.get_tag(tid)
        if not k:
            return
        cat = k.get("category") or "misc"
        sub = k.get("subcategory") or "general"
        name = k.get("name") or ""
        src = k.get("source_file") or ""
        p = self._keywords_primary_file(cat, sub, preferred=src)
        if p.exists():
            items = []
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                rec = self._parse_keyword_line(line)
                if not rec:
                    continue
                if _norm_token(rec["name"]) == _norm_token(name):
                    continue
                items.append({"name": rec["name"], "aliases": rec.get("aliases") or [], "desc": rec.get("desc") or "", "enabled": bool(rec.get("enabled", True))})
            self._write_keywords_for_category(cat, sub, items, preferred=src)

    def _parse_pack_blocks(self, txt: str, source_file: str = "") -> List[Dict[str, Any]]:
        blocks: List[Dict[str, Any]] = []
        cur: List[str] = []
        for line in (txt or "").splitlines():
            if line.strip() == "---":
                if cur:
                    blocks.append(self._parse_pack_block(cur, source_file))
                cur = []
            else:
                cur.append(line)
        if cur:
            blocks.append(self._parse_pack_block(cur, source_file))
        return [b for b in blocks if b.get("title")]

    def _parse_pack_block(self, lines: List[str], source_file: str = "") -> Dict[str, Any]:
        pid = ""
        title = ""
        note = ""
        keywords_raw: List[str] = []
        for ln in lines:
            s = (ln or "").strip()
            if not s:
                continue
            if s.startswith("#"):
                continue
            if s.startswith("@") and ":" in s:
                k, v = s[1:].split(":", 1)
                k = (k or "").strip().casefold()
                v = (v or "").strip()
                if k == "id":
                    pid = v
                elif k == "title":
                    title = v
                elif k in ("keywords", "tags"):
                    keywords_raw = [x.strip() for x in v.split(",") if x.strip()]
                elif k == "note":
                    note = v
        if not pid and title:
            pid = f"pk::{_safe_name(title)}::{abs(hash(source_file + '|' + title))}"
        return {
            "id": pid,
            "category": "",
            "title": title,
            "note": note,
            "keywords_raw": keywords_raw,
            "source_file": source_file,
        }

    def _packs_primary_file(self, category: str) -> Path:
        category = (category or "misc").strip()
        self._lib_dir.mkdir(parents=True, exist_ok=True)
        return self._lib_dir / f"{category}__packs.md"

    def _write_pack_blocks_to_file(self, path: Path, blocks: List[Dict[str, Any]]) -> None:
        out_lines: List[str] = []
        for b in blocks:
            title = (b.get("title") or "").strip()
            if not title:
                continue
            pid = (b.get("id") or "").strip() or str(uuid.uuid4())
            out_lines.append(f"@id: {pid}")
            out_lines.append(f"@title: {title}")
            kws = [x.strip() for x in (b.get("keywords_raw") or []) if x.strip()]
            if kws:
                out_lines.append("@keywords: " + ", ".join(kws))
            note = (b.get("note") or "").strip()
            if note:
                out_lines.append(f"@note: {note}")
            out_lines.append("")
            out_lines.append("---")
            out_lines.append("")
        txt = "\n".join(out_lines).strip() + ("\n" if out_lines else "")
        bak = path.with_suffix(path.suffix + ".bak")
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            if path.exists():
                shutil.copy2(path, bak)
        except Exception:
            pass
        tmp.write_text(txt, encoding="utf-8")
        os.replace(str(tmp), str(path))

    def _load_packs(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for p in self._iter_lib_files("packs"):
            info = self._parse_lib_filename(p.name)
            if not info:
                continue
            cat, _ = info
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            blocks = self._parse_pack_blocks(txt, source_file=str(p))
            for b in blocks:
                pid = b.get("id") or ""
                title = b.get("title") or ""
                if not pid or not title:
                    continue
                b["category"] = cat
                out[pid] = b
        return out


    # ------------------ Base Prompts (Templates) ------------------
    _BASE_SPLIT = re.compile(r"^\s*---\s*$", flags=re.M)

    def _slug_id(self, name: str) -> str:
        name = (name or "").strip()
        if not name:
            return ""
        name = unicodedata.normalize("NFKC", name).casefold()
        name = re.sub(r"[\s\-–—]+", "_", name)
        name = re.sub(r"[^a-z0-9_]+", "", name)
        name = re.sub(r"_+", "_", name).strip("_")
        return name

    def _base_key(self, category: str, base_id: str) -> str:
        return f"base::{(category or 'misc')}::{(base_id or '').strip()}"

    def _parse_base_block(self, text: str) -> Optional[Dict[str, Any]]:
        lines = (text or "").splitlines()
        if not any((ln.strip() for ln in lines)):
            return None

        meta: Dict[str, Any] = {"id": "", "title": "", "slots": 0, "template": ""}
        in_template = False
        template_lines: List[str] = []

        for ln in lines:
            raw = ln.rstrip("\n")
            s = raw.strip()
            if not s and not in_template:
                continue

            if not in_template and s.startswith("@") and ":" in s:
                k, v = s[1:].split(":", 1)
                k = (k or "").strip().casefold()
                v = (v or "").strip()
                if k == "id":
                    meta["id"] = v
                    continue
                if k == "title":
                    meta["title"] = v
                    continue
                if k == "slots":
                    try:
                        meta["slots"] = int(v)
                    except Exception:
                        meta["slots"] = 0
                    continue
                if k == "template":
                    in_template = True
                    if v:
                        template_lines.append(v)
                    continue

            # also allow "template:" without "@"
            if not in_template and s.casefold().startswith("template:"):
                in_template = True
                v = s.split(":", 1)[1].strip()
                if v:
                    template_lines.append(v)
                continue

            if in_template:
                template_lines.append(raw)

        base_id = (meta.get("id") or "").strip()
        title = (meta.get("title") or "").strip()
        template = "\n".join(template_lines).strip()

        if not template:
            # fallback: treat entire block as template if no marker
            template = "\n".join([ln for ln in lines if ln.strip()]).strip()

        if not base_id:
            base_id = self._slug_id(title) if title else self._slug_id(template[:40])
        if not title:
            title = base_id or "Base Prompt"

        meta["id"] = base_id
        meta["title"] = title
        meta["template"] = template
        return meta

    def _load_bases(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for p in self._iter_lib_files("bases"):
            info = self._parse_lib_filename(p.name)
            if not info:
                continue
            cat, _ = info
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            blocks = re.split(r"^\s*---\s*$", txt, flags=re.M)
            for b in blocks:
                rec = self._parse_base_block(b)
                if not rec:
                    continue
                bid = (rec.get("id") or "").strip()
                if not bid:
                    continue
                key = self._base_key(cat, bid)
                if key in out:
                    continue
                out[key] = {
                    "id": key,
                    "base_id": bid,
                    "category": cat,
                    "title": rec.get("title") or bid,
                    "slots": int(rec.get("slots") or 0),
                    "template": rec.get("template") or "",
                    "source_file": str(p),
                }
        return out

    def list_base_choices(self, q: str = "", category: str = "all") -> List[Tuple[str, str]]:
        qn = _norm_token(q)
        cn = _norm_token(category)
        bases = self._load_bases()
        out: List[Tuple[str, str]] = []
        for key, b in bases.items():
            cat = (b.get("category") or "misc").strip()
            title = (b.get("title") or "").strip()
            if not key or not title:
                continue
            if cn and cn not in ("all", "*"):
                if _norm_token(cat) != cn:
                    continue
            label = f"{cat} › {title}"
            if qn:
                hay = _norm_token(label + " " + (b.get("template") or ""))
                if qn not in hay:
                    continue
            out.append((label, key))
        return out

    def get_base(self, base_key: str) -> Optional[Dict[str, Any]]:
        return self._load_bases().get(base_key)

    def _bases_primary_file(self, category: str) -> Path:
        category = (category or "misc").strip()
        self._lib_dir.mkdir(parents=True, exist_ok=True)
        return self._lib_dir / f"{category}__bases.md"

    def _read_bases_from_file(self, path: Path, category: str) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        try:
            txt = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return []
        blocks = re.split(r"^\s*---\s*$", txt, flags=re.M)
        out = []
        for b in blocks:
            rec = self._parse_base_block(b)
            if not rec:
                continue
            bid = (rec.get("id") or "").strip()
            if not bid:
                continue
            out.append({
                "base_id": bid,
                "category": category,
                "title": (rec.get("title") or bid).strip(),
                "slots": int(rec.get("slots") or 0),
                "template": (rec.get("template") or "").strip(),
            })
        return out

    def _write_bases_for_category(self, category: str, bases: List[Dict[str, Any]]) -> None:
        p = self._bases_primary_file(category)
        blocks = []
        for b in sorted(bases, key=lambda x: (x.get("title") or "").casefold()):
            bid = (b.get("base_id") or b.get("id") or "").strip()
            if bid.startswith("base::"):
                bid = bid.split("::")[-1]
            bid = self._slug_id(bid) or self._slug_id(b.get("title") or "") or str(uuid.uuid4())[:8]
            title = (b.get("title") or bid).strip()
            slots = int(b.get("slots") or 0)
            tmpl = (b.get("template") or "").strip()
            if not tmpl:
                continue
            block = [
                f"@id: {bid}",
                f"@title: {title}",
                f"@slots: {slots}",
                "@template:",
                tmpl,
                "---",
            ]
            blocks.append("\n".join(block))
        p.write_text("\n\n".join(blocks).strip() + ("\n" if blocks else ""), encoding="utf-8")

    def upsert_base(self, base_key: str, category: str, title: str, slots: int, template: str) -> str:
        cat = (category or "misc").strip()
        title = (title or "").strip()
        tmpl = (template or "").strip()
        if not cat or not title or not tmpl:
            return ""

        # Determine base_id + key
        base_id = ""
        if base_key and base_key.startswith("base::"):
            parts = base_key.split("::", 2)
            if len(parts) == 3:
                base_id = parts[2].strip()
                # if category changed, keep base_id but move file
        if not base_id:
            base_id = self._slug_id(title) or str(uuid.uuid4())[:8]
        key = self._base_key(cat, base_id)

        path = self._bases_primary_file(cat)
        existing = self._read_bases_from_file(path, cat)

        # replace by base_id
        updated = False
        for b in existing:
            if (b.get("base_id") or "").strip() == base_id:
                b["title"] = title
                b["slots"] = int(slots or 0)
                b["template"] = tmpl
                updated = True
                break
        if not updated:
            existing.append({"base_id": base_id, "category": cat, "title": title, "slots": int(slots or 0), "template": tmpl})

        self._write_bases_for_category(cat, existing)
        return key

    def delete_base(self, base_key: str) -> bool:
        if not base_key or not base_key.startswith("base::"):
            return False
        parts = base_key.split("::", 2)
        if len(parts) != 3:
            return False
        cat = (parts[1] or "misc").strip()
        base_id = (parts[2] or "").strip()
        path = self._bases_primary_file(cat)
        existing = self._read_bases_from_file(path, cat)
        new_list = [b for b in existing if (b.get("base_id") or "").strip() != base_id]
        if len(new_list) == len(existing):
            return False
        self._write_bases_for_category(cat, new_list)
        return True
    def list_pack_choices(self, q: str = "", category: str = "all") -> List[Tuple[str, str]]:
        qn = _norm_token(q)
        cn = _norm_token(category)
        packs = self._load_packs()
        out: List[Tuple[str, str]] = []
        for pid, p in packs.items():
            cat = p.get("category") or "misc"
            title = p.get("title") or ""
            if not title:
                continue
            if cn and cn not in ("all", "*"):
                if _norm_token(cat) != cn:
                    continue
            label = f"{cat} › {title}"
            if qn and qn not in _norm_token(label + " " + (p.get("note") or "")):
                continue
            out.append((label, pid))
        return out

    def get_pack(self, pid: str) -> Optional[Dict[str, Any]]:
        packs = self._load_packs()
        return packs.get(pid)

    def upsert_pack(self, pid: str, category: str, title: str, tag_ids: List[str]) -> Optional[str]:
        title = (title or "").strip()
        if not title:
            return None
        category0 = (category or "").strip()
        category0 = self._slug_category(category0) or category0 or "misc"
        self.add_category(category0)

        kws = self._load_keywords()
        kw_tokens: List[str] = []
        for kid in (tag_ids or []):
            k = kws.get(kid)
            if not k:
                continue
            nm = (k.get("name") or "").strip()
            if nm:
                kw_tokens.append(f"{k.get('category','misc')}::{nm}")

        path = self._packs_primary_file(category0)
        existing_blocks: List[Dict[str, Any]] = []
        if path.exists():
            try:
                existing_blocks = self._parse_pack_blocks(path.read_text(encoding="utf-8", errors="ignore"), source_file=str(path))
            except Exception:
                existing_blocks = []

        if pid:
            packs = self._load_packs()
            old = packs.get(pid)
            if old:
                old_file = Path(old.get("source_file") or "")
                try:
                    old_blocks = self._parse_pack_blocks(old_file.read_text(encoding="utf-8", errors="ignore"), source_file=str(old_file))
                    old_blocks = [b for b in old_blocks if b.get("id") != pid]
                    self._write_pack_blocks_to_file(old_file, old_blocks)
                except Exception:
                    pass

        if not pid:
            pid = str(uuid.uuid4())

        new_block = {"id": pid, "title": title, "keywords_raw": kw_tokens, "note": "", "source_file": str(path), "category": category0}
        existing_blocks = [b for b in existing_blocks if b.get("id") != pid]
        existing_blocks.append(new_block)
        existing_blocks = sorted(existing_blocks, key=lambda b: (b.get("title") or "").casefold())
        self._write_pack_blocks_to_file(path, existing_blocks)
        return pid

    def delete_pack(self, pid: str):
        packs = self._load_packs()
        p = packs.get(pid)
        if not p:
            return
        fp = Path(p.get("source_file") or "")
        if not fp.exists():
            return
        blocks = self._parse_pack_blocks(fp.read_text(encoding="utf-8", errors="ignore"), source_file=str(fp))
        blocks = [b for b in blocks if b.get("id") != pid]
        self._write_pack_blocks_to_file(fp, blocks)

    def resolve_pack_tags(self, pack_id: str) -> List[Dict[str, Any]]:
        p = self.get_pack(pack_id)
        if not p:
            return []
        kws = self._load_keywords()
        out = []
        for token in (p.get("keywords_raw") or []):
            cat, name = self._split_kw_token(token)
            if cat and name:
                kid = self._kw_id(cat, name)
                k = kws.get(kid)
                if k and k.get("enabled", True):
                    out.append(k)
                else:
                    out.append({"id": kid, "category": cat, "name": name, "aliases": [], "desc": "", "enabled": True})
            elif name:
                out.append({"id": "kw::misc::" + _norm_token(name), "category": "misc", "name": name, "aliases": [], "desc": "", "enabled": True})
        return out
    # ------------------ MapSets ------------------
    def list_mapset_choices(self, q: str = "") -> List[Tuple[str, str]]:
        qn = _norm_token(q)
        out: List[Tuple[str, str]] = []
        for m in self.data.get("mapsets", []):
            mid = m.get("id") or ""
            title = m.get("title") or ""
            label = title
            if not mid or not title:
                continue
            if qn and qn not in _norm_token(label + " " + " ".join(m.get("tags") or [])):
                continue
            out.append((label, mid))
        return out

    def get_mapset(self, mid: str) -> Optional[Dict[str, Any]]:
        for m in self.data.get("mapsets", []):
            if m.get("id") == mid:
                return m
        return None

    def create_mapset(self, title: str, tags_csv: str = "") -> str:
        mid = str(uuid.uuid4())
        tags = [t.strip() for t in (tags_csv or "").split(",") if t.strip()]
        item = {
            "id": mid,
            "title": _safe_name(title),
            "tags": tags,
            "created": _now_iso(),
            "updated": _now_iso(),
            "maps": {t: [] for t in _MAP_TYPES},
        }
        self.data.setdefault("mapsets", []).append(item)
        for t in _MAP_TYPES:
            (ASSETS_DIR / mid / t).mkdir(parents=True, exist_ok=True)
        self.save()
        return mid

    def update_mapset_meta(self, mid: str, title: str, tags_csv: str):
        m = self.get_mapset(mid)
        if not m:
            return
        m["title"] = _safe_name(title)
        m["tags"] = [t.strip() for t in (tags_csv or "").split(",") if t.strip()]
        m["updated"] = _now_iso()
        self.save()

    def delete_mapset(self, mid: str):
        self.data["mapsets"] = [m for m in self.data.get("mapsets", []) if m.get("id") != mid]
        folder = ASSETS_DIR / mid
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
        self.save()

    def add_maps_to_mapset(
        self,
        mid: str,
        files: List[Any],
        map_type: str,
        auto_detect: bool,
        enforce_suffix: bool,
    ) -> int:
        m = self.get_mapset(mid)
        if not m:
            return 0
        count = 0
        for f in files or []:
            src = getattr(f, "name", None) or str(f)
            if not src or not os.path.exists(src):
                continue
            chosen = map_type
            if auto_detect:
                g = _guess_map_type(os.path.basename(src))
                if g:
                    chosen = g
            if chosen not in _MAP_TYPES:
                continue

            dst_dir = ASSETS_DIR / mid / chosen
            dst_dir.mkdir(parents=True, exist_ok=True)
            stem = _safe_name(Path(src).stem, max_len=90)
            if enforce_suffix:
                stem = _ensure_suffix(stem, chosen)
            suffix = Path(src).suffix.lower() or ".png"
            dst = dst_dir / f"{stem}{suffix}"
            if dst.exists():
                dst = dst_dir / f"{stem}_{uuid.uuid4().hex[:6]}{suffix}"
            shutil.copy2(src, dst)

            rel = str(dst.relative_to(USER_DATA)).replace("\\", "/")
            m["maps"][chosen].append(rel)
            count += 1

        m["updated"] = _now_iso()
        self.save()
        return count

    def list_map_paths(self, mid: str, map_type: str) -> List[Tuple[str, str]]:
        m = self.get_mapset(mid)
        if not m:
            return []
        rels = m.get("maps", {}).get(map_type, []) or []
        out: List[Tuple[str, str]] = []
        for r in rels:
            p = USER_DATA / r
            if p.exists():
                out.append((str(p), os.path.basename(str(p))))
        return out

    # ------------------ LoRA / TI Registry ------------------
    def _norm_path(self, p: str) -> str:
        try:
            return os.path.abspath(p).replace("\\", "/").lower()
        except Exception:
            return (p or "").replace("\\", "/").lower()

    def _default_lora_dir(self) -> str:
        """Best-effort guess of Forge's LoRA dir."""
        # Try A1111/Forge conventions
        try:
            from modules import shared
            d = getattr(getattr(shared, "cmd_opts", None), "lora_dir", None)
            if d and os.path.isdir(d):
                return d
        except Exception:
            pass
        try:
            from modules import paths
            d = os.path.join(paths.models_path, "Lora")
            if os.path.isdir(d):
                return d
        except Exception:
            pass
        # Fallback: relative to webui root
        try:
            here = str(EXT_ROOT)
            # EXT_ROOT/.../extensions/prompt_suite_bridge -> .../sd-webui-forge-neo
            root = Path(here).parents[2]
            d = str(root / "models" / "Lora")
            if os.path.isdir(d):
                return d
        except Exception:
            pass
        return ""

    def _default_embed_dir(self) -> str:
        """Best-effort guess of Forge's embeddings dir."""
        try:
            from modules import shared
            d = getattr(getattr(shared, "cmd_opts", None), "embeddings_dir", None)
            if d and os.path.isdir(d):
                return d
        except Exception:
            pass
        try:
            from modules import paths
            d = os.path.join(paths.script_path, "embeddings")
            if os.path.isdir(d):
                return d
        except Exception:
            pass
        try:
            here = str(EXT_ROOT)
            root = Path(here).parents[2]
            d = str(root / "embeddings")
            if os.path.isdir(d):
                return d
        except Exception:
            pass
        return ""

    def _iter_loras(self, kind: str = "lora") -> List[Dict[str, Any]]:
        return [it for it in (self.data.get("loras", []) or []) if (it.get("kind") or "lora") == kind]

    def list_lora_categories(self, kind: str = "lora") -> List[str]:
        vals = {str((it.get("category") or "").strip()) for it in self._iter_loras(kind) if str((it.get("category") or "").strip())}
        return sorted(vals, key=lambda x: x.casefold())

    def list_lora_base_models(self, kind: str = "lora") -> List[str]:
        vals = {str((it.get("base_model") or "").strip()) for it in self._iter_loras(kind) if str((it.get("base_model") or "").strip())}
        return sorted(vals, key=lambda x: x.casefold())

    def list_lora_style_categories(self, kind: str = "lora") -> List[str]:
        vals = {str((it.get("style_category") or "").strip()) for it in self._iter_loras(kind) if str((it.get("style_category") or "").strip())}
        return sorted(vals, key=lambda x: x.casefold())

    def find_duplicate_lora_triggers(self, kind: str = "lora") -> Dict[str, List[str]]:
        token_to_ids: Dict[str, List[str]] = {}
        for it in self._iter_loras(kind):
            lid = str(it.get("id") or "").strip()
            if not lid:
                continue
            for trig in it.get("triggers") or []:
                norm = _norm_token(str(trig or ""))
                if not norm:
                    continue
                token_to_ids.setdefault(norm, []).append(lid)
        dup_map: Dict[str, List[str]] = {}
        for ids in token_to_ids.values():
            uniq = []
            seen = set()
            for lid in ids:
                if lid not in seen:
                    seen.add(lid)
                    uniq.append(lid)
            if len(uniq) > 1:
                for lid in uniq:
                    dup_map.setdefault(lid, [])
                    for other in uniq:
                        if other != lid and other not in dup_map[lid]:
                            dup_map[lid].append(other)
        return dup_map

    def build_lora_insert_block(self, lid: str, strength: float = 1.0, selected_triggers: Optional[List[str]] = None, include_triggers: bool = True) -> str:
        it = self.get_lora(lid) if lid else None
        if not it:
            return ""
        ref = _prompt_token_ref(it)
        if not ref:
            return ""
        kind = str(it.get('kind') or 'lora').strip().lower()
        token = ref if kind == 'ti' else f"<lora:{ref}:{float(strength or 1.0):.2f}>"
        if not include_triggers:
            return token
        triggers = selected_triggers if selected_triggers is not None else list(it.get("triggers") or [])
        clean = []
        seen = set()
        for trig in triggers:
            trig = str(trig or "").strip()
            key = _norm_token(trig)
            if not trig or not key or key in seen:
                continue
            seen.add(key)
            clean.append(trig)
        return token if not clean else token + ", " + ", ".join(clean)

    def _clean_remote_text(self, value: Any, limit: int = 1200) -> str:
        raw = str(value or "")
        if not raw:
            return ""
        raw = re.sub(r"<[^>]+>", " ", raw)
        raw = html.unescape(raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        return raw[:limit].strip()

    def _guess_remote_keywords(self, values: Any, limit: int = 20) -> List[str]:
        if isinstance(values, list):
            items = values
        else:
            items = re.split(r"[,|\n;]+", str(values or ""))
        return self._clean_meta_tokens([str(x or "").strip() for x in items], limit=limit)

    def parse_civitai_url(self, url: str) -> Dict[str, Any]:
        raw = str(url or "").strip()
        if not raw:
            raise ValueError("Enter a CivitAI model or version URL first.")
        parsed = urlparse(raw)
        host = (parsed.netloc or "").lower()
        if not any(dom in host for dom in ("civitai.com", "civitai.red")):
            raise ValueError("Only CivitAI URLs are supported in this import step.")
        path = parsed.path or ""
        query = parse_qs(parsed.query or "")
        version_id = ""
        model_id = ""
        m = re.search(r"/models/(\d+)", path)
        if m:
            model_id = m.group(1)
        v = re.search(r"/model-versions/(\d+)", path)
        if v:
            version_id = v.group(1)
        d = re.search(r"/api/download/models/(\d+)", path)
        if d and not version_id:
            version_id = d.group(1)
        if not version_id:
            mv = (query.get("modelVersionId") or [""])[0]
            if mv and str(mv).isdigit():
                version_id = str(mv)
        if not model_id and not version_id:
            raise ValueError("Could not detect a model or version id from that CivitAI URL.")
        api_hosts: List[str] = []
        preferred_host = host or "civitai.com"
        if "civitai.red" in preferred_host:
            api_hosts = ["civitai.red", "civitai.com"]
        else:
            api_hosts = ["civitai.com", "civitai.red"]
        return {
            "url": raw,
            "model_id": model_id,
            "version_id": version_id,
            "host": preferred_host,
            "api_hosts": api_hosts,
        }

    def _http_json(self, url: str, timeout: int = 20) -> Dict[str, Any]:
        req = Request(url, headers={"User-Agent": "NeoLibrary/1.0 (+local)", "Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        payload = data.decode("utf-8", errors="ignore").strip()
        if not payload:
            raise ValueError(f"Empty server response from {url}")
        try:
            obj = json.loads(payload)
        except Exception as exc:
            sample = re.sub(r"\s+", " ", payload[:180]).strip()
            raise ValueError(f"Non-JSON server response from {url}: {sample or 'unreadable payload'}") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"Unexpected response shape from {url}")
        return obj

    def fetch_civitai_remote(self, url: str) -> Dict[str, Any]:
        parsed = self.parse_civitai_url(url)
        model_id = parsed.get("model_id") or ""
        version_id = parsed.get("version_id") or ""
        api_hosts = list(parsed.get("api_hosts") or ["civitai.com", "civitai.red"])
        model_obj: Dict[str, Any] = {}
        version_obj: Dict[str, Any] = {}
        errors: List[str] = []

        def _fetch_with_fallback(path: str) -> Dict[str, Any]:
            last_exc = None
            for api_host in api_hosts:
                try:
                    return self._http_json(f"https://{api_host}{path}")
                except Exception as exc:
                    last_exc = exc
                    errors.append(str(exc))
            if last_exc:
                raise last_exc
            return {}

        if version_id:
            version_obj = _fetch_with_fallback(f"/api/v1/model-versions/{version_id}")
            if not model_id:
                model_id = str(version_obj.get("modelId") or "").strip()
        if model_id:
            try:
                model_obj = _fetch_with_fallback(f"/api/v1/models/{model_id}")
            except Exception:
                model_obj = {}
            if not version_obj:
                versions = model_obj.get("modelVersions") or []
                if version_id:
                    for cand in versions:
                        if str(cand.get("id") or "") == str(version_id):
                            version_obj = cand or {}
                            break
                if not version_obj and versions:
                    version_obj = versions[0] or {}
        if not version_obj:
            extra = f" Details: {' | '.join(dict.fromkeys(errors))}" if errors else ""
            raise ValueError("Could not fetch a usable CivitAI model version from that URL." + extra)

        images = version_obj.get("images") or []
        preview_urls: List[str] = []
        example_prompt = ""
        negative_prompt = ""
        for img in images:
            if not isinstance(img, dict):
                continue
            url_val = str(img.get("url") or img.get("imageUrl") or img.get("src") or "").strip()
            if url_val:
                preview_urls.append(url_val)
            meta = img.get("meta") or {}
            if not example_prompt and isinstance(meta, dict):
                example_prompt = self._clean_remote_text(meta.get("prompt") or "", limit=2500)
                negative_prompt = self._clean_remote_text(meta.get("negativePrompt") or "", limit=1200)
        trained_words = self._guess_remote_keywords(version_obj.get("trainedWords") or model_obj.get("trainedWords") or [], limit=24)
        tags = self._guess_remote_keywords(model_obj.get("tags") or [], limit=24)
        base_model = str(version_obj.get("baseModel") or version_obj.get("baseModelType") or model_obj.get("baseModel") or "").strip()
        model_name = str(model_obj.get("name") or version_obj.get("modelName") or "").strip()
        version_name = str(version_obj.get("name") or "").strip()
        desc_parts = [
            self._clean_remote_text(version_obj.get("description") or ""),
            self._clean_remote_text(model_obj.get("description") or ""),
        ]
        description = "\n\n".join([x for x in desc_parts if x]).strip()
        if negative_prompt:
            description = (description + ("\n\n" if description else "") + f"Example negative prompt: {negative_prompt}").strip()
        if not parsed.get("version_id"):
            parsed["version_id"] = str(version_obj.get("id") or "").strip()
        provider_url = parsed.get("url") or ""
        if model_id and parsed.get("version_id"):
            provider_host = str(parsed.get("host") or "civitai.com")
            provider_url = f"https://{provider_host}/models/{model_id}?modelVersionId={parsed.get('version_id')}"
        return {
            "provider": "civitai",
            "source_url": provider_url,
            "model_id": str(model_id or ""),
            "version_id": str(parsed.get("version_id") or ""),
            "model_name": model_name,
            "version_name": version_name,
            "trained_words": trained_words,
            "keywords": tags,
            "base_model": base_model,
            "example_prompt": example_prompt,
            "notes": description,
            "preview_urls": list(dict.fromkeys(preview_urls)),
        }

    def _download_binary(self, url: str, dst: Path, timeout: int = 30) -> bool:
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            req = Request(url, headers={"User-Agent": "NeoLibrary/1.0 (+local)"})
            with urlopen(req, timeout=timeout) as resp, open(dst, "wb") as f:
                shutil.copyfileobj(resp, f)
            return True
        except Exception:
            return False

    def _download_civitai_preview_images(self, lid: str, urls: List[str], limit: int = 6) -> List[str]:
        lid_clean = re.sub(r"[^A-Za-z0-9_-]+", "_", str(lid or "preview"))[:80] or "preview"
        out_dir = LORA_PREVIEW_CACHE_DIR / lid_clean
        out_dir.mkdir(parents=True, exist_ok=True)
        out: List[str] = []
        for idx, src in enumerate(urls[: max(1, int(limit or 6))], start=1):
            parsed = urlparse(str(src or ""))
            ext = os.path.splitext(parsed.path or "")[1].lower()
            if ext not in (".png", ".jpg", ".jpeg", ".webp"):
                ext = ".jpg"
            dst = out_dir / f"civitai_{idx:02d}{ext}"
            if not dst.exists():
                self._download_binary(src, dst)
            if dst.exists():
                out.append(str(dst))
        return out

    def import_civitai_into_lora(
        self,
        lid: str,
        url: str,
        merge_mode: str = "fill_missing",
        overwrite_fields: Optional[List[str]] = None,
        preview_limit: int = 6,
    ) -> Dict[str, Any]:
        it = self.get_lora(lid) if lid else None
        if not it:
            return {"ok": False, "message": "Select a LoRA/TI entry first."}
        remote = self.fetch_civitai_remote(url)
        downloaded = self._download_civitai_preview_images(lid, remote.get("preview_urls") or [], limit=preview_limit)
        overwrite = {str(x or "").strip() for x in (overwrite_fields or []) if str(x or "").strip()}
        local_defaults = self._extract_lora_metadata_defaults(str(it.get("file") or ""))
        field_sources = dict(it.get("field_sources") or {})
        changed: List[str] = []

        def _effective_existing(field: str):
            cur = it.get(field)
            if field == "triggers" and not cur:
                cur = local_defaults.get("triggers") or []
            elif field == "keywords" and not cur:
                cur = local_defaults.get("keywords") or []
            elif field == "base_model" and not str(cur or "").strip():
                cur = local_defaults.get("base_model") or ""
            elif field == "notes" and not str(cur or "").strip():
                cur = local_defaults.get("notes") or ""
            return cur

        def _is_missing(value: Any) -> bool:
            if value is None:
                return True
            if isinstance(value, list):
                return len([x for x in value if str(x or "").strip()]) == 0
            return not str(value or "").strip()

        def _merge_unique(existing_list: Any, incoming_list: Any) -> List[str]:
            merged: List[str] = []
            seen = set()
            for raw in list(existing_list or []) + list(incoming_list or []):
                token = str(raw or "").strip()
                key = _norm_token(token)
                if not token or not key or key in seen:
                    continue
                seen.add(key)
                merged.append(token)
            return merged

        def _append_prompt_option(name: str, text_value: str, source: str = "civitai") -> bool:
            prompt_text = str(text_value or "").strip()
            if not prompt_text:
                return False
            options = [dict(x) for x in (it.get("prompt_options") or []) if isinstance(x, dict)]
            existing_texts = {_norm_token(str(opt.get("text") or "")) for opt in options}
            if _norm_token(prompt_text) in existing_texts:
                return False
            options.append({
                "id": str(uuid.uuid4()),
                "name": str(name or f"Variant {len(options) + 1}").strip() or f"Variant {len(options) + 1}",
                "text": prompt_text,
                "source": source,
                "created": _now_iso(),
            })
            it["prompt_options"] = options
            field_sources["prompt_options"] = f"remote:{source}"
            if "prompt_options" not in changed:
                changed.append("prompt_options")
            return True

        def _maybe_apply(field: str, value: Any):
            if value is None:
                return
            if isinstance(value, list) and not value:
                return
            if isinstance(value, str) and not value.strip():
                return
            existing = _effective_existing(field)
            if merge_mode == "previews_only":
                return
            if merge_mode == "smart_merge":
                if field in {"triggers", "keywords"}:
                    merged = _merge_unique(existing if isinstance(existing, list) else [], value if isinstance(value, list) else [])
                    old_value = list(it.get(field) or [])
                    if merged != old_value:
                        it[field] = merged
                        field_sources[field] = "remote:civitai"
                        if field not in changed:
                            changed.append(field)
                    return
                if field == "example_prompt":
                    incoming_text = str(value or "").strip()
                    current_text = str(existing or "").strip()
                    if not current_text:
                        it[field] = incoming_text
                        field_sources[field] = "remote:civitai"
                        if field not in changed:
                            changed.append(field)
                    elif _norm_token(current_text) != _norm_token(incoming_text):
                        _append_prompt_option("CivitAI import", incoming_text, "civitai")
                    return
                if field == "notes":
                    incoming_text = str(value or "").strip()
                    current_text = str(existing or "").strip()
                    if not incoming_text:
                        return
                    if not current_text:
                        it[field] = incoming_text
                        field_sources[field] = "remote:civitai"
                        if field not in changed:
                            changed.append(field)
                    elif _norm_token(incoming_text) not in _norm_token(current_text):
                        it[field] = f"{current_text}\n\n{incoming_text}".strip()
                        field_sources[field] = "remote:civitai"
                        if field not in changed:
                            changed.append(field)
                    return
                if field in {"base_model"}:
                    if _is_missing(existing):
                        it[field] = value
                        field_sources[field] = "remote:civitai"
                        if field not in changed:
                            changed.append(field)
                    return
            should_write = False
            if merge_mode == "fill_missing":
                should_write = _is_missing(existing)
            elif merge_mode == "overwrite_selected":
                should_write = field in overwrite
            if not should_write:
                return
            old = it.get(field)
            it[field] = value
            field_sources[field] = "remote:civitai"
            if old != value and field not in changed:
                changed.append(field)

        _maybe_apply("triggers", list(remote.get("trained_words") or []))
        _maybe_apply("keywords", list(remote.get("keywords") or []))
        _maybe_apply("base_model", str(remote.get("base_model") or "").strip())
        _maybe_apply("example_prompt", str(remote.get("example_prompt") or "").strip())
        _maybe_apply("notes", str(remote.get("notes") or "").strip())

        existing_preview_images = [str(x or "").strip() for x in (it.get("preview_images") or []) if str(x or "").strip()]
        if str(it.get("preview_image") or "").strip() and str(it.get("preview_image")).strip() not in existing_preview_images:
            existing_preview_images.insert(0, str(it.get("preview_image")).strip())
        merged_previews: List[str] = []
        seen = set()
        for path in existing_preview_images + downloaded:
            key = os.path.normcase(os.path.abspath(path)) if path else ""
            if not path or key in seen:
                continue
            seen.add(key)
            merged_previews.append(path)
        if merged_previews:
            it["preview_images"] = merged_previews
            field_sources["preview_images"] = "remote:civitai"
            primary_existing = str(it.get("preview_image") or "").strip()
            set_primary = False
            if merge_mode in ("fill_missing", "previews_only"):
                set_primary = not primary_existing
            elif merge_mode == "overwrite_selected":
                set_primary = ("previews" in overwrite or "preview_image" in overwrite or not primary_existing)
            if set_primary:
                it["preview_image"] = merged_previews[0]
                field_sources["preview_image"] = "remote:civitai"
                if "preview_image" not in changed:
                    changed.append("preview_image")

        it["remote_source"] = {
            "provider": "civitai",
            "url": str(remote.get("source_url") or url or ""),
            "model_id": str(remote.get("model_id") or ""),
            "version_id": str(remote.get("version_id") or ""),
            "model_name": str(remote.get("model_name") or ""),
            "version_name": str(remote.get("version_name") or ""),
            "imported_at": _now_iso(),
        }
        it["field_sources"] = field_sources
        it["updated"] = _now_iso()
        self.save()
        downloaded_count = len(downloaded)
        changed_label = ", ".join(changed) if changed else "none"
        msg = f"✅ CivitAI import complete. Downloaded previews: {downloaded_count}. Updated fields: {changed_label}."
        return {"ok": True, "message": msg, "downloaded": downloaded_count, "changed": changed, "remote": remote}

    def set_primary_lora_preview(self, lid: str, preview_path: str) -> bool:
        it = self.get_lora(lid) if lid else None
        path = str(preview_path or "").strip()
        if not it or not path:
            return False
        previews = [str(x or "").strip() for x in (it.get("preview_images") or []) if str(x or "").strip()]
        if path not in previews:
            previews.insert(0, path)
        it["preview_images"] = previews
        it["preview_image"] = path
        field_sources = dict(it.get("field_sources") or {})
        field_sources["preview_image"] = "manual"
        it["field_sources"] = field_sources
        it["updated"] = _now_iso()
        self.save()
        return True

    def list_lora_choices(
        self,
        q: str = "",
        kind: str = "lora",
        category: str = "all",
        base_model: str = "all",
        style_category: str = "all",
        missing_only: bool = False,
        duplicates_only: bool = False,
    ) -> List[Tuple[str, str]]:
        qn = _norm_token(q)
        cn = _norm_token(category)
        bn = _norm_token(base_model)
        sn = _norm_token(style_category)
        dup_map = self.find_duplicate_lora_triggers(kind) if duplicates_only else {}
        out: List[Tuple[str, str]] = []
        for it in self._iter_loras(kind):
            lid = str(it.get("id") or "").strip()
            rel = str(it.get("rel") or it.get("name") or "").strip()
            cat = str(it.get("category") or "").strip()
            name = str(it.get("name") or "").strip()
            base = str(it.get("base_model") or "").strip()
            style = str(it.get("style_category") or "").strip()
            missing = bool(str(it.get("file") or "").strip()) and (not os.path.isfile(str(it.get("file") or "").strip()))
            if not lid or not name:
                continue
            if cn not in ("", "all", "*") and _norm_token(cat) != cn:
                continue
            if bn not in ("", "all", "*") and _norm_token(base) != bn:
                continue
            if sn not in ("", "all", "*") and _norm_token(style) != sn:
                continue
            if missing_only and not missing:
                continue
            if duplicates_only and lid not in dup_map:
                continue
            label = f"{cat} › {rel}" if cat else rel
            if qn:
                hay = _norm_token(" ".join([
                    label,
                    rel,
                    cat,
                    name,
                    base,
                    style,
                    " ".join(it.get("triggers") or []),
                    " ".join(it.get("keywords") or []),
                    str(it.get("notes") or ""),
                    str(it.get("example_prompt") or ""),
                    str(it.get("caution_notes") or ""),
                ]))
                if qn not in hay:
                    continue
            badge = []
            if missing:
                badge.append("missing")
            if lid in dup_map:
                badge.append("dup")
            if style:
                badge.append(style)
            if badge:
                label = f"{label} [{' • '.join(badge)}]"
            out.append((label, lid))
        return out

    def get_lora(self, lid: str) -> Optional[Dict[str, Any]]:
        for it in self.data.get("loras", []) or []:
            if it.get("id") == lid:
                return it
        return None

    def _read_safetensors_metadata(self, file_path: str) -> Dict[str, Any]:
        fp = (file_path or '').strip()
        if not fp or not fp.lower().endswith('.safetensors') or not os.path.isfile(fp):
            return {}
        try:
            with open(fp, 'rb') as f:
                header_len_bytes = f.read(8)
                if len(header_len_bytes) != 8:
                    return {}
                header_len = int.from_bytes(header_len_bytes, 'little', signed=False)
                if header_len <= 0 or header_len > 16 * 1024 * 1024:
                    return {}
                header = json.loads(f.read(header_len).decode('utf-8', errors='ignore'))
                meta = header.get('__metadata__') if isinstance(header, dict) else {}
                return meta if isinstance(meta, dict) else {}
        except Exception:
            return {}

    def _clean_meta_tokens(self, tokens: List[str], limit: int = 24) -> List[str]:
        junk = {
            '1girl', '1boy', 'solo', 'best quality', 'masterpiece', 'high quality', 'absurdres',
            'lowres', 'rating:safe', 'score_9', 'score_8_up', 'score_7_up', 'monochrome'
        }
        out: List[str] = []
        seen = set()
        for raw in tokens or []:
            token = str(raw or '').strip().strip(',')
            if not token:
                continue
            token = re.sub(r'\s+', ' ', token)
            key = token.casefold()
            if key in seen or key in junk:
                continue
            seen.add(key)
            out.append(token)
            if len(out) >= limit:
                break
        return out

    def _extract_lora_metadata_defaults(self, file_path: str) -> Dict[str, Any]:
        meta = self._read_safetensors_metadata(file_path)
        if not meta:
            return {'triggers': [], 'keywords': [], 'notes': '', 'metadata_status': 'No readable metadata found', 'base_model': ''}

        def _csvish(v: Any) -> List[str]:
            if isinstance(v, list):
                vals = v
            else:
                vals = re.split(r'[,|\n;]+', str(v or ''))
            return [str(x or '').strip() for x in vals if str(x or '').strip()]

        tag_tokens: List[str] = []
        for key in ('modelspec.tags', 'tags', 'trainedWords', 'activation text', 'sd tag', 'trigger', 'triggers'):
            if meta.get(key):
                tag_tokens.extend(_csvish(meta.get(key)))

        tag_freq = meta.get('ss_tag_frequency')
        if tag_freq:
            try:
                parsed = json.loads(tag_freq) if isinstance(tag_freq, str) else tag_freq
                counts: Dict[str, int] = {}
                if isinstance(parsed, dict):
                    for _, bucket in parsed.items():
                        if isinstance(bucket, dict):
                            for tag, count in bucket.items():
                                tag = str(tag or '').strip()
                                if not tag:
                                    continue
                                counts[tag] = counts.get(tag, 0) + int(count or 0)
                ranked = [k for k, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].casefold()))]
                tag_tokens.extend(ranked[:32])
            except Exception:
                pass

        clean_keywords = self._clean_meta_tokens(tag_tokens, limit=20)
        trigger_guess = [t for t in clean_keywords if ' ' not in t][:8] or clean_keywords[:8]
        clean_triggers = self._clean_meta_tokens(trigger_guess, limit=8)

        note_parts: List[str] = []
        base_model = str(meta.get('ss_base_model_version') or meta.get('ss_sd_model_name') or '').strip()
        base_model = base_model or _infer_lora_base_model_hint(
            os.path.basename(file_path),
            meta.get('modelspec.title'),
            meta.get('ss_output_name'),
            meta.get('modelspec.description'),
            meta.get('description'),
            meta.get('modelspec.architecture'),
            meta.get('modelspec.implementation'),
        )
        if base_model:
            note_parts.append(f'Base model: {base_model}')
        desc = str(meta.get('modelspec.description') or meta.get('description') or '').strip()
        if desc:
            note_parts.append(desc[:500])
        title = str(meta.get('modelspec.title') or meta.get('ss_output_name') or '').strip()
        if title and title.casefold() not in ' '.join(note_parts).casefold():
            note_parts.insert(0, f'Title: {title}')

        status = 'Metadata found and applied' if (clean_triggers or clean_keywords) else ('Partial metadata found' if note_parts else 'No readable metadata found')
        return {
            'triggers': clean_triggers,
            'keywords': clean_keywords,
            'notes': '\n'.join([x for x in note_parts if x]).strip(),
            'metadata_status': status,
            'base_model': base_model,
        }

    def get_lora_prefill(self, lid: str) -> Optional[Dict[str, Any]]:
        it = self.get_lora(lid)
        if not it:
            return None
        out = dict(it)
        meta_defaults = self._extract_lora_metadata_defaults(it.get('file') or '')
        if not (out.get('triggers') or []):
            out['triggers'] = list(meta_defaults.get('triggers') or [])
        if not (out.get('keywords') or []):
            out['keywords'] = list(meta_defaults.get('keywords') or [])
        if not str(out.get('notes') or '').strip():
            out['notes'] = meta_defaults.get('notes') or ''
        out['metadata_status'] = meta_defaults.get('metadata_status') or 'No readable metadata found'
        out['base_model'] = str(out.get('base_model') or meta_defaults.get('base_model') or '').strip()
        out['min_strength'] = float(out.get('min_strength') or 0.6)
        out['max_strength'] = float(out.get('max_strength') or 1.0)
        out['example_prompt'] = str(out.get('example_prompt') or '').strip()
        out['preview_image'] = str(out.get('preview_image') or '').strip()
        out['style_category'] = str(out.get('style_category') or '').strip()
        out['caution_notes'] = str(out.get('caution_notes') or '').strip()
        previews = [str(x or '').strip() for x in (out.get('preview_images') or []) if str(x or '').strip()]
        if out['preview_image'] and out['preview_image'] not in previews:
            previews.insert(0, out['preview_image'])
        out['preview_images'] = previews
        out['remote_source'] = dict(out.get('remote_source') or {})
        out['field_sources'] = dict(out.get('field_sources') or {})
        out['prompt_options'] = [dict(x) for x in (out.get('prompt_options') or []) if isinstance(x, dict)]
        file_path = str(out.get('file') or '').strip()
        out['missing_file'] = bool(file_path) and (not os.path.isfile(file_path))
        dup_ids = self.find_duplicate_lora_triggers(kind=str(out.get('kind') or 'lora')).get(str(out.get('id') or ''), [])
        dup_names = []
        for other_id in dup_ids:
            other = self.get_lora(other_id) or {}
            name = str(other.get('rel') or other.get('name') or other_id).strip()
            if name and name not in dup_names:
                dup_names.append(name)
        out['duplicate_with'] = dup_names
        out['insert_block'] = self.build_lora_insert_block(str(out.get('id') or ''), strength=float(out.get('default_strength') or 1.0), include_triggers=True)
        return out

    def upsert_lora_meta(
        self,
        lid: str,
        triggers_csv: str,
        keywords_csv: str,
        default_strength: float,
        notes: str,
        enabled: bool = True,
        min_strength: Optional[float] = None,
        max_strength: Optional[float] = None,
        base_model: str = "",
        caution_notes: str = "",
        example_prompt: str = "",
        preview_image: str = "",
        style_category: str = "",
        prompt_options: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[str]:
        it = self.get_lora(lid) if lid else None
        if it is None:
            return None
        triggers = [x.strip() for x in (triggers_csv or "").split(",") if x.strip()]
        keywords = [x.strip() for x in (keywords_csv or "").split(",") if x.strip()]
        try:
            default_strength_val = float(default_strength) if default_strength is not None else float(it.get("default_strength") or 1.0)
        except Exception:
            default_strength_val = float(it.get("default_strength") or 1.0)
        try:
            min_strength_val = float(min_strength) if min_strength is not None else float(it.get("min_strength") or default_strength_val)
        except Exception:
            min_strength_val = float(it.get("min_strength") or default_strength_val)
        try:
            max_strength_val = float(max_strength) if max_strength is not None else float(it.get("max_strength") or default_strength_val)
        except Exception:
            max_strength_val = float(it.get("max_strength") or default_strength_val)
        if min_strength_val > max_strength_val:
            min_strength_val, max_strength_val = max_strength_val, min_strength_val
        clean_prompt_options: List[Dict[str, Any]] = []
        seen_prompt_keys = set()
        for opt in (prompt_options or []):
            if not isinstance(opt, dict):
                continue
            text_value = str(opt.get("text") or "").strip()
            if not text_value:
                continue
            key = _norm_token(text_value)
            if key in seen_prompt_keys:
                continue
            seen_prompt_keys.add(key)
            clean_prompt_options.append({
                "id": str(opt.get("id") or uuid.uuid4()),
                "name": str(opt.get("name") or f"Variant {len(clean_prompt_options) + 1}").strip() or f"Variant {len(clean_prompt_options) + 1}",
                "text": text_value,
                "source": str(opt.get("source") or "manual").strip() or "manual",
                "created": str(opt.get("created") or _now_iso()),
            })
        it.update({
            "triggers": triggers,
            "keywords": keywords,
            "default_strength": default_strength_val,
            "notes": notes or "",
            "enabled": bool(enabled),
            "min_strength": min_strength_val,
            "max_strength": max_strength_val,
            "base_model": (base_model or "").strip(),
            "caution_notes": caution_notes or "",
            "example_prompt": example_prompt or "",
            "preview_image": preview_image or "",
            "style_category": (style_category or "").strip(),
            "prompt_options": clean_prompt_options,
            "field_sources": dict(it.get("field_sources") or {}),
            "updated": _now_iso(),
        })
        self.save()
        return it.get("id")

    def delete_lora(self, lid: str):
        self.data["loras"] = [x for x in (self.data.get("loras") or []) if x.get("id") != lid]
        self.save()

    def scan_loras(self, lora_dir: str = "", embed_dir: str = "", include_ti: bool = True) -> Tuple[int, int]:
        """Scan LoRA/Embeddings folders and upsert missing entries. Returns (added, updated)."""
        lora_dir = (lora_dir or self._default_lora_dir()).strip()
        embed_dir = (embed_dir or self._default_embed_dir()).strip()

        existing = self.data.get("loras") or []
        by_file = {self._norm_path(x.get("file") or ""): x for x in existing if x.get("file")}

        added = 0
        updated = 0

        def _walk(base: str, exts: Tuple[str, ...]) -> List[str]:
            out: List[str] = []
            if not base or not os.path.isdir(base):
                return out
            for root, _, files in os.walk(base):
                for fn in files:
                    if fn.lower().endswith(tuple([e.lower() for e in exts])):
                        out.append(os.path.join(root, fn))
            return out

        # LoRAs
        for fp in _walk(lora_dir, _LORA_EXTS):
            nfp = self._norm_path(fp)
            rel = ""
            cat = ""
            try:
                relp = os.path.relpath(fp, lora_dir)
                rel = os.path.splitext(relp)[0].replace("\\", "/")
                cat = os.path.dirname(rel).replace("\\", "/").strip("/")
            except Exception:
                rel = os.path.splitext(os.path.basename(fp))[0]
                cat = ""
            name = os.path.splitext(os.path.basename(fp))[0]
            if nfp in by_file:
                it = by_file[nfp]
                inferred_base = _infer_lora_base_model_hint(name, rel, cat, str(it.get("notes") or ""))
                # update discovered fields only
                it.update({
                    "kind": "lora",
                    "file": fp,
                    "rel": rel,
                    "name": name,
                    "category": cat,
                    "base_model": str(it.get("base_model") or inferred_base or "").strip(),
                    "updated": _now_iso(),
                })
                updated += 1
                continue
            meta_defaults = self._extract_lora_metadata_defaults(fp)
            inferred_base = _infer_lora_base_model_hint(name, rel, cat, meta_defaults.get("notes") or "")
            existing.append({
                "id": str(uuid.uuid4()),
                "kind": "lora",
                "file": fp,
                "rel": rel,
                "name": name,
                "category": cat,
                "triggers": list(meta_defaults.get("triggers") or []),
                "keywords": list(meta_defaults.get("keywords") or []),
                "default_strength": 0.8,
                "notes": meta_defaults.get("notes") or "",
                "base_model": meta_defaults.get("base_model") or inferred_base or "",
                "min_strength": 0.6,
                "max_strength": 1.0,
                "example_prompt": "",
                "preview_image": "",
                "preview_images": [],
                "prompt_options": [],
                "remote_source": {},
                "field_sources": {},
                "style_category": "",
                "caution_notes": "",
                "enabled": True,
                "created": _now_iso(),
                "updated": _now_iso(),
            })
            added += 1

        # Embeddings (TI)
        if include_ti:
            for fp in _walk(embed_dir, _EMBED_EXTS):
                nfp = self._norm_path(fp)
                name = os.path.splitext(os.path.basename(fp))[0]
                rel = name
                cat = ""
                if nfp in by_file:
                    it = by_file[nfp]
                    it.update({
                        "kind": "ti",
                        "file": fp,
                        "rel": rel,
                        "name": name,
                        "category": cat,
                        "updated": _now_iso(),
                    })
                    updated += 1
                    continue
                existing.append({
                    "id": str(uuid.uuid4()),
                    "kind": "ti",
                    "file": fp,
                    "rel": rel,
                    "name": name,
                    "category": cat,
                    "triggers": [],
                    "keywords": [],
                    "default_strength": 1.0,
                    "notes": "",
                    "base_model": "",
                    "min_strength": 1.0,
                    "max_strength": 1.0,
                    "example_prompt": "",
                    "preview_image": "",
                    "preview_images": [],
                    "remote_source": {},
                    "field_sources": {},
                    "style_category": "",
                    "caution_notes": "",
                    "enabled": True,
                    "created": _now_iso(),
                    "updated": _now_iso(),
                })
                added += 1

        self.data["loras"] = existing
        self.save()
        return added, updated

    # ------------------ Legacy migration ------------------
    def maybe_migrate_legacy_prompt_map_vault(self):
        """
        If an old data/library.json exists (prompt_map_vault style), migrate:
        - each legacy prompt -> new mapset with copied assets
        - (prompt text migration handled by PromptPresetStore)
        """
        legacy_lib = EXT_ROOT / "data" / "library.json"
        legacy_assets = EXT_ROOT / "data" / "assets"
        marker = USER_DATA / ".legacy_migrated_v1"
        if marker.exists():
            return
        if not legacy_lib.exists():
            marker.write_text("no legacy", encoding="utf-8")
            return
        try:
            legacy = json.loads(legacy_lib.read_text(encoding="utf-8"))
        except Exception:
            marker.write_text("bad legacy json", encoding="utf-8")
            return

        prompts = legacy.get("prompts", []) or []
        if not prompts:
            marker.write_text("empty legacy", encoding="utf-8")
            return

        # only migrate if vault is empty
        if self.data.get("mapsets"):
            marker.write_text("skipped - already has mapsets", encoding="utf-8")
            return

        for lp in prompts:
            pid = lp.get("id")
            title = lp.get("title") or "Legacy"
            if not pid:
                continue
            mid = self.create_mapset(f"{title} (legacy)", tags_csv="")
            # copy assets folder if exists
            if legacy_assets.exists():
                for t in _MAP_TYPES:
                    src_dir = legacy_assets / pid / t
                    if not src_dir.exists():
                        continue
                    dst_dir = ASSETS_DIR / mid / t
                    dst_dir.mkdir(parents=True, exist_ok=True)
                    for fn in src_dir.iterdir():
                        if fn.is_file():
                            stem = _safe_name(fn.stem, max_len=90)
                            # keep legacy name
                            dst = dst_dir / f"{stem}{fn.suffix}"
                            if dst.exists():
                                dst = dst_dir / f"{stem}_{uuid.uuid4().hex[:6]}{fn.suffix}"
                            shutil.copy2(str(fn), str(dst))
                            rel = str(dst.relative_to(USER_DATA)).replace("\\", "/")
                            m = self.get_mapset(mid)
                            if m:
                                m["maps"][t].append(rel)
            self.save()

        marker.write_text("done", encoding="utf-8")
