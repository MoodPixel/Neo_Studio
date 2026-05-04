
import gradio as gr
import os
import sys
import subprocess
import shutil
from pathlib import Path

try:
    from .shared_data_paths import library_data_path
except ImportError:
    from shared_data_paths import library_data_path
from vault_store import VaultStore
from ui_sync import get_prompt_composer_lora_refs, prompt_composer_lora_refresh

EXT_NAME = "Vault + Maps (Assets)"
EXT_VER = "v0.2"

EXT_ROOT = Path(__file__).resolve().parents[1]
LIBRARIES_DIR = EXT_ROOT / "libraries"


ASSETS_DIR = library_data_path('assets', legacy_rel='assets')


def _entry_prompt_ref(it: dict) -> str:
    kind = str((it or {}).get("kind") or "lora").strip().lower()
    name = str((it or {}).get("name") or "").strip()
    rel = str((it or {}).get("rel") or name or "").strip()
    if kind == "ti":
        return rel or name
    return name or (rel.split("/")[-1].strip() if rel else "")

def _open_folder(path: str) -> str:
    p = (path or "").strip()
    if not p:
        return "⚠️ No folder path."
    try:
        if not os.path.exists(p):
            return f"⚠️ Folder not found: {p}"
        if sys.platform.startswith("win"):
            os.startfile(p)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])
        return f"✅ Opened: {p}"
    except Exception as e:
        return f"⚠️ Could not open folder: {e}"
def build_vault_ui():
    store = VaultStore()

    tag_id = gr.State(value="")
    pack_id = gr.State(value="")
    base_id = gr.State(value="")
    mapset_id = gr.State(value="")

    prompt_refs = get_prompt_composer_lora_refs()

    with gr.Column():
        gr.Markdown(f"### 🗃️ {EXT_NAME}")
        gr.Markdown("This tab is **asset management only**: keywords / mapsets / LoRA metadata. No sending to txt2img/img2img.")

        with gr.Tabs():

            # ---------------- Library (Keywords + Packs) ----------------
            with gr.Tab("🔑 Keywords"):
                gr.Markdown("Everything here is **keyword-driven** from the `libraries/` folder. Categories and subcategories are derived from the keyword file names.")

                _cats0 = ["all"] + store.list_keyword_categories()
                _cat0 = _cats0[1] if len(_cats0) > 1 else "all"
                _subs0 = ["all"] + store.list_keyword_subcategories(_cat0)
                _sub0 = _subs0[1] if len(_subs0) > 1 else "all"

                gr.Markdown("#### 🧩 Keywords")
                with gr.Row():
                    kw_filter_cat = gr.Dropdown(label="Filter category", choices=_cats0, value=_cat0)
                    kw_filter_sub = gr.Dropdown(label="Filter subcategory", choices=_subs0, value=_sub0)
                    kw_search = gr.Textbox(label="Search keywords", placeholder="piggyback / streetwear / soft light…", lines=1)
                    kw_dd = gr.Dropdown(label="Saved keywords", choices=store.list_tag_choices(category=_cat0, subcategory=_sub0), value=None)

                kw_category = gr.Textbox(label="Category", placeholder="Locations")
                kw_subcategory = gr.Textbox(label="Subcategory", placeholder="Airport")
                kw_name = gr.Textbox(label="Keyword (canonical name)", placeholder="departure gate")
                kw_aliases = gr.Textbox(label="Aliases (comma-separated)", placeholder="airport gate, boarding gate")
                kw_desc = gr.Textbox(label="Description (optional)", lines=4)
                kw_enabled = gr.Checkbox(value=True, label="Enabled")

                with gr.Row():
                    btn_kw_new = gr.Button("➕ New")
                    btn_kw_save = gr.Button("💾 Save")
                    btn_kw_del = gr.Button("🗑️ Delete", variant="stop")
                kw_status = gr.Markdown("")

                def _refresh_kw_filters(cat_filter: str, sub_filter: str, q: str):
                    s = VaultStore()
                    cats = ["all"] + s.list_keyword_categories()
                    cat_val = cat_filter if cat_filter in cats else (cats[1] if len(cats) > 1 else "all")
                    subs = ["all"] + s.list_keyword_subcategories(cat_val)
                    sub_val = sub_filter if sub_filter in subs else (subs[1] if len(subs) > 1 else "all")
                    kws = s.list_tag_choices(q=q or "", category=cat_val, subcategory=sub_val)
                    return gr.update(choices=cats, value=cat_val), gr.update(choices=subs, value=sub_val), gr.update(choices=kws, value=None)

                def _load_keyword(tid: str):
                    s = VaultStore()
                    t = s.get_tag(tid) if tid else None
                    if not t:
                        return "", "", "", "", "", "", True, "⚠️ Select a keyword."
                    return tid, t.get("category",""), t.get("subcategory","general"), t.get("name",""), ", ".join(t.get("aliases") or []), t.get("desc",""), bool(t.get("enabled",True)), "✅ Loaded."

                def _new_keyword():
                    return "", "", "", "", "", "", True, "✅ New keyword."

                def _save_keyword(tid, cat, sub, name, aliases, desc, enabled, cat_filter: str, sub_filter: str, q: str):
                    s = VaultStore()
                    out_id = s.upsert_tag(tid, cat, sub, name, aliases, desc, enabled)
                    cats = ["all"] + s.list_keyword_categories()
                    cat_val = cat if cat in cats else (cat_filter if cat_filter in cats else (cats[1] if len(cats) > 1 else "all"))
                    subs = ["all"] + s.list_keyword_subcategories(cat_val)
                    sub_val = sub if sub in subs else (sub_filter if sub_filter in subs else (subs[1] if len(subs) > 1 else "all"))
                    kws = s.list_tag_choices(q=q or "", category=cat_val, subcategory=sub_val)
                    if not out_id:
                        return gr.update(choices=cats, value=cat_val), gr.update(choices=subs, value=sub_val), gr.update(choices=kws, value=None), "", "⚠️ Keyword name is required."
                    selected = out_id if any(v == out_id for (_, v) in kws) else None
                    return gr.update(choices=cats, value=cat_val), gr.update(choices=subs, value=sub_val), gr.update(choices=kws, value=selected), out_id, "✅ Saved."

                def _del_keyword(tid: str, cat_filter: str, sub_filter: str, q: str):
                    s = VaultStore()
                    if tid:
                        s.delete_tag(tid)
                    cats = ["all"] + s.list_keyword_categories()
                    cat_val = cat_filter if cat_filter in cats else (cats[1] if len(cats) > 1 else "all")
                    subs = ["all"] + s.list_keyword_subcategories(cat_val)
                    sub_val = sub_filter if sub_filter in subs else (subs[1] if len(subs) > 1 else "all")
                    kws = s.list_tag_choices(q=q or "", category=cat_val, subcategory=sub_val)
                    return gr.update(choices=cats, value=cat_val), gr.update(choices=subs, value=sub_val), gr.update(choices=kws, value=None), "", ("🗑️ Deleted." if tid else "⚠️ Nothing selected.")

                kw_filter_cat.change(_refresh_kw_filters, inputs=[kw_filter_cat, kw_filter_sub, kw_search], outputs=[kw_filter_cat, kw_filter_sub, kw_dd])
                kw_filter_sub.change(_refresh_kw_filters, inputs=[kw_filter_cat, kw_filter_sub, kw_search], outputs=[kw_filter_cat, kw_filter_sub, kw_dd])
                kw_search.change(_refresh_kw_filters, inputs=[kw_filter_cat, kw_filter_sub, kw_search], outputs=[kw_filter_cat, kw_filter_sub, kw_dd])
                kw_dd.change(_load_keyword, inputs=[kw_dd], outputs=[tag_id, kw_category, kw_subcategory, kw_name, kw_aliases, kw_desc, kw_enabled, kw_status])
                btn_kw_new.click(_new_keyword, inputs=[], outputs=[tag_id, kw_category, kw_subcategory, kw_name, kw_aliases, kw_desc, kw_enabled, kw_status])
                btn_kw_save.click(_save_keyword, inputs=[tag_id, kw_category, kw_subcategory, kw_name, kw_aliases, kw_desc, kw_enabled, kw_filter_cat, kw_filter_sub, kw_search], outputs=[kw_filter_cat, kw_filter_sub, kw_dd, tag_id, kw_status])
                btn_kw_del.click(_del_keyword, inputs=[tag_id, kw_filter_cat, kw_filter_sub, kw_search], outputs=[kw_filter_cat, kw_filter_sub, kw_dd, tag_id, kw_status])

                with gr.Accordion("📚 Library Files (Keywords)", open=False):
                    gr.Markdown(
                        "Manage your **keyword library `.md` files** inside the extension `libraries/` folder.\n\n"
                        "- Import new `.md` files here (no Forge restart).\n"
                        "- Edit existing files and save.\n"
                        "- The Prompt Composer keyword typeahead reads these libraries live as you type."
                    )

                    def _list_lib_md():
                        if not LIBRARIES_DIR.exists():
                            return []
                        return [p.name for p in sorted(LIBRARIES_DIR.glob("*.md"))]

                    with gr.Row():
                        lib_file = gr.Dropdown(label="Library file (.md)", choices=_list_lib_md(), value=None, scale=3)
                        btn_lib_refresh = gr.Button("🔄 Refresh list", scale=1)

                    lib_text = gr.Textbox(label="File content", lines=18, placeholder="Select a keyword library file to view/edit…")

                    with gr.Row():
                        btn_lib_load = gr.Button("↻ Load")
                        btn_lib_save = gr.Button("💾 Save")

                    with gr.Accordion("⬆️ Import .md into libraries/", open=True):
                        lib_upload = gr.File(label="Drop .md file(s) here", file_count="multiple", file_types=[".md"])
                        lib_overwrite = gr.Checkbox(value=False, label="Overwrite if same name exists")
                        btn_lib_import = gr.Button("Import file(s)")

                    lib_msg = gr.Markdown("")

                    def _load_lib(fn: str):
                        if not fn:
                            return "", "⚠️ Select a file."
                        path = LIBRARIES_DIR / fn
                        try:
                            txt = path.read_text(encoding="utf-8")
                        except Exception as e:
                            return "", f"❌ Read failed: `{e}`"
                        return txt, f"✅ Loaded `{fn}`"

                    def _save_lib(fn: str, txt: str):
                        if not fn:
                            return "⚠️ Select a file."
                        path = LIBRARIES_DIR / fn
                        try:
                            if path.exists():
                                try:
                                    (LIBRARIES_DIR / (fn + ".bak")).write_text(path.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
                                except Exception:
                                    pass
                            path.write_text(txt or "", encoding="utf-8")
                        except Exception as e:
                            return f"❌ Save failed: `{e}`"
                        return f"✅ Saved `{fn}`."

                    def _refresh_lib_list():
                        return gr.update(choices=_list_lib_md(), value=None), "✅ Refreshed list."

                    def _import_lib(files, overwrite: bool):
                        LIBRARIES_DIR.mkdir(parents=True, exist_ok=True)
                        if not files:
                            return gr.update(choices=_list_lib_md()), "⚠️ No files selected."
                        imported = 0
                        skipped = 0

                        def _fp(x):
                            if isinstance(x, str):
                                return x
                            if isinstance(x, dict):
                                return x.get("name") or ""
                            return getattr(x, "name", "") or ""

                        for f in (files or []):
                            fp = _fp(f)
                            if not fp:
                                skipped += 1
                                continue
                            src = Path(fp)
                            if src.suffix.lower() != ".md":
                                skipped += 1
                                continue
                            dst = LIBRARIES_DIR / src.name
                            if dst.exists() and not overwrite:
                                skipped += 1
                                continue
                            try:
                                shutil.copyfile(str(src), str(dst))
                                imported += 1
                            except Exception:
                                skipped += 1

                        msg = f"✅ Imported {imported} file(s)." + (f" Skipped {skipped}." if skipped else "")
                        return gr.update(choices=_list_lib_md()), msg

                    btn_lib_load.click(fn=_load_lib, inputs=[lib_file], outputs=[lib_text, lib_msg])
                    lib_file.change(fn=_load_lib, inputs=[lib_file], outputs=[lib_text, lib_msg])
                    btn_lib_save.click(fn=_save_lib, inputs=[lib_file, lib_text], outputs=[lib_msg])

                    btn_lib_refresh.click(fn=_refresh_lib_list, inputs=[], outputs=[lib_file, lib_msg])
                    btn_lib_import.click(fn=_import_lib, inputs=[lib_upload, lib_overwrite], outputs=[lib_file, lib_msg])


            # ---------------- LoRA / TI ----------------
            with gr.Tab("🎛️ LoRA / TI"):
                gr.Markdown("Register your existing **LoRAs** (and optional **Textual Inversions**) so Prompt Builder can insert them + show your trigger tags. This panel is the place to keep richer metadata like example prompts, strength ranges, preview image, and caution notes.")

                with gr.Row():
                    lora_dir = gr.Textbox(label="LoRA folder", value=store._default_lora_dir(), placeholder=r"F:\LLM\sd-webui-forge-neo\models\Lora")
                    embed_dir = gr.Textbox(label="Embeddings folder (TI)", value=store._default_embed_dir(), placeholder=r"F:\LLM\sd-webui-forge-neo\embeddings")

                include_ti = gr.Checkbox(label="Also scan embeddings (TI)", value=True)
                scan_btn = gr.Button("🔎 Scan folders")
                scan_msg = gr.Markdown("")

                with gr.Row():
                    lora_kind = gr.Radio(label="Kind", choices=["lora", "ti"], value="lora")
                    lora_search = gr.Textbox(label="Search", placeholder="portrait, skin, style, anime…", lines=1)

                with gr.Row():
                    lora_filter_cat = gr.Dropdown(label="Filter category", choices=["all"] + store.list_lora_categories("lora"), value="all")
                    lora_filter_base = gr.Dropdown(label="Base model", choices=["all"] + store.list_lora_base_models("lora"), value="all")
                    lora_filter_style = gr.Dropdown(label="Style/category", choices=["all"] + store.list_lora_style_categories("lora"), value="all")
                with gr.Row():
                    lora_missing_only = gr.Checkbox(label="Missing file only", value=False)
                    lora_duplicates_only = gr.Checkbox(label="Duplicate trigger only", value=False)

                lora_dd = gr.Dropdown(label="Registered", choices=store.list_lora_choices(kind="lora"), value=None)
                lora_id = gr.State(value="")

                lora_file = gr.Textbox(label="File (read-only)", value="", interactive=False)
                lora_rel = gr.Textbox(label="Prompt token (read-only)", value="", interactive=False)
                lora_cat = gr.Textbox(label="Category (folder)", value="", interactive=False)
                lora_name = gr.Textbox(label="Name (read-only)", value="", interactive=False)

                with gr.Row():
                    lora_strength = gr.Slider(0.0, 2.0, value=0.8, step=0.05, label="Default strength")
                    lora_min_strength = gr.Slider(0.0, 2.0, value=0.6, step=0.05, label="Recommended min")
                    lora_max_strength = gr.Slider(0.0, 2.0, value=1.0, step=0.05, label="Recommended max")

                lora_triggers = gr.Textbox(label="Triggers (comma-separated)", placeholder="trigger_word, keyword2, style_tag")
                lora_keywords = gr.Textbox(label="Keywords (comma-separated)", placeholder="portrait, skin, hair, lighting")
                with gr.Row():
                    lora_style_category = gr.Textbox(label="Style / use category", placeholder="portrait, fashion, realism, stylized")
                    lora_base_model = gr.Textbox(label="Base model compatibility", placeholder="SDXL / Pony / Flux / custom checkpoint")
                lora_example_prompt = gr.Textbox(label="Example prompt", lines=4, placeholder="Short example prompt for quick reuse")
                with gr.Row():
                    lora_preview_path = gr.Textbox(label="Preview image path", placeholder=r"Optional image path for preview")
                    lora_enabled = gr.Checkbox(label="Enabled", value=True)
                lora_preview_image = gr.Image(label="Preview image", type="filepath", interactive=False, height=360)
                lora_caution = gr.Textbox(label="Caution notes", lines=2, placeholder="Things to avoid, conflicts, or model quirks")
                lora_notes = gr.Textbox(label="Notes", lines=3, placeholder="What this LoRA is good for…")
                with gr.Accordion("🌐 Import from CivitAI", open=False):
                    gr.Markdown("Paste a **CivitAI model/version URL** to fetch remote previews + metadata without replacing your local file metadata unless you explicitly choose to.")
                    with gr.Row():
                        civitai_url = gr.Textbox(label="CivitAI URL", placeholder="https://civitai.com/models/...")
                        civitai_fetch = gr.Button("🌐 Fetch", scale=0)
                    with gr.Row():
                        civitai_merge_mode = gr.Dropdown(label="Import mode", choices=[("Fill missing fields only", "fill_missing"), ("Previews only", "previews_only"), ("Overwrite selected fields", "overwrite_selected")], value="fill_missing")
                        civitai_overwrite_fields = gr.CheckboxGroup(label="Selected fields to overwrite", choices=[("Triggers", "triggers"), ("Keywords", "keywords"), ("Base model", "base_model"), ("Example prompt", "example_prompt"), ("Notes", "notes"), ("Primary preview", "preview_image"), ("Fetched previews", "previews")], value=["previews"])
                    lora_provider_badge = gr.Markdown("🌐 Provider: none yet.")
                    with gr.Row():
                        civitai_preview_pick = gr.Dropdown(label="Fetched preview files", choices=[], value=None)
                        civitai_apply_preview = gr.Button("🖼️ Use selected preview", scale=0)
                    civitai_preview_image = gr.Image(label="Fetched preview", type="filepath", interactive=False, height=320)
                    civitai_fetch_status = gr.Markdown("")
                lora_insert_block = gr.Textbox(label="Full insert block", lines=2, interactive=False)
                lora_warning = gr.Markdown("")
                lora_meta_status = gr.Markdown("ℹ️ Metadata status: not checked yet.")

                with gr.Row():
                    lora_save = gr.Button("💾 Save meta")
                    lora_del = gr.Button("🗑️ Delete", variant="stop")

                lora_status = gr.Markdown("")

                def _refresh_filter_choices(kind: str, cat_val: str = 'all', base_val: str = 'all', style_val: str = 'all'):
                    s = VaultStore()
                    cats = ['all'] + s.list_lora_categories(kind)
                    bases = ['all'] + s.list_lora_base_models(kind)
                    styles = ['all'] + s.list_lora_style_categories(kind)
                    return (
                        gr.update(choices=cats, value=cat_val if cat_val in cats else 'all'),
                        gr.update(choices=bases, value=base_val if base_val in bases else 'all'),
                        gr.update(choices=styles, value=style_val if style_val in styles else 'all'),
                    )

                def _refresh_lora_choices(q: str, kind: str, cat: str, base_model: str, style_cat: str, missing_only: bool, duplicates_only: bool):
                    s = VaultStore()
                    return gr.update(choices=s.list_lora_choices(q=q, kind=kind, category=cat, base_model=base_model, style_category=style_cat, missing_only=bool(missing_only), duplicates_only=bool(duplicates_only)), value=None)

                def _scan(l_dir: str, e_dir: str, inc_ti: bool, kind: str, cat: str, base_model: str, style_cat: str, missing_only: bool, duplicates_only: bool):
                    s = VaultStore()
                    added, updated = s.scan_loras(l_dir, e_dir, include_ti=bool(inc_ti))
                    cats_u, base_u, style_u = _refresh_filter_choices(kind, cat, base_model, style_cat)
                    dd = gr.update(choices=s.list_lora_choices(kind=kind, category=cat, base_model=base_model, style_category=style_cat, missing_only=bool(missing_only), duplicates_only=bool(duplicates_only)), value=None)
                    return dd, cats_u, base_u, style_u, f"✅ Scan complete. Added: **{added}**, updated: **{updated}**"

                def _kind_change(kind: str, q: str, cat: str, base_model: str, style_cat: str, missing_only: bool, duplicates_only: bool):
                    s = VaultStore()
                    cats_u, base_u, style_u = _refresh_filter_choices(kind, 'all', 'all', 'all')
                    return (
                        gr.update(choices=s.list_lora_choices(q=q, kind=kind, category='all', base_model='all', style_category='all', missing_only=bool(missing_only), duplicates_only=bool(duplicates_only)), value=None),
                        cats_u,
                        base_u,
                        style_u,
                    )

                def _warning_text(it: dict) -> str:
                    bits = []
                    if it.get('missing_file'):
                        bits.append('⚠️ **Missing file:** saved path no longer exists.')
                    dup = it.get('duplicate_with') or []
                    if dup:
                        bits.append('⚠️ **Duplicate trigger overlap:** ' + ', '.join(dup[:8]))
                    rng = f"Recommended range: {float(it.get('min_strength') or 0.0):.2f} → {float(it.get('max_strength') or 0.0):.2f}"
                    bits.append('ℹ️ ' + rng)
                    return '\n\n'.join(bits)

                def _remote_badge(it: dict) -> str:
                    remote = dict((it or {}).get('remote_source') or {})
                    if not remote:
                        return '🌐 Provider: none yet.'
                    provider = str(remote.get('provider') or 'remote').strip().title()
                    model_name = str(remote.get('model_name') or '').strip()
                    version_name = str(remote.get('version_name') or '').strip()
                    parts = [f"🌐 Provider: **{provider}**"]
                    if model_name:
                        parts.append(model_name)
                    if version_name:
                        parts.append(f"version: {version_name}")
                    src = str(remote.get('url') or '').strip()
                    if src:
                        parts.append(src)
                    return ' · '.join(parts)

                def _remote_preview_updates(it: dict):
                    previews = [str(x or '').strip() for x in ((it or {}).get('preview_images') or []) if str(x or '').strip()]
                    primary = str((it or {}).get('preview_image') or '').strip()
                    if primary and primary not in previews:
                        previews.insert(0, primary)
                    choices = [(os.path.basename(p) or p, p) for p in previews]
                    selected = primary if primary in previews else (previews[0] if previews else None)
                    return gr.update(choices=choices, value=selected), (selected or None)

                def _load_lora(lid: str):
                    s = VaultStore()
                    it = s.get_lora_prefill(lid) if lid else None
                    if not it:
                        return '', '', '', '', '', 0.8, 0.6, 1.0, '', '', '', '', '', None, '', '', True, '', 'ℹ️ Metadata status: nothing selected.', '⚠️ Select an item.', '', '', '', '🌐 Provider: none yet.', gr.update(choices=[], value=None), None
                    meta_status = it.get('metadata_status') or 'No readable metadata found'
                    preview_path = it.get('preview_image') or ''
                    remote_dd, remote_img = _remote_preview_updates(it)
                    remote_url = str((it.get('remote_source') or {}).get('url') or '')
                    return (
                        lid,
                        it.get('file',''),
                        _entry_prompt_ref(it),
                        it.get('category',''),
                        it.get('name',''),
                        float(it.get('default_strength') or 1.0),
                        float(it.get('min_strength') or 0.6),
                        float(it.get('max_strength') or 1.0),
                        ', '.join(it.get('triggers') or []),
                        ', '.join(it.get('keywords') or []),
                        it.get('style_category',''),
                        it.get('base_model',''),
                        it.get('example_prompt',''),
                        preview_path or None,
                        preview_path,
                        it.get('caution_notes',''),
                        bool(it.get('enabled', True)),
                        it.get('notes',''),
                        f"ℹ️ Metadata status: {meta_status}",
                        '✅ Loaded.',
                        _warning_text(it),
                        s.build_lora_insert_block(lid, strength=float(it.get('default_strength') or 1.0), include_triggers=True),
                        remote_url,
                        _remote_badge(it),
                        remote_dd,
                        remote_img,
                    )

                def _sync_insert_block(lid: str, strength: float, triggers: str):
                    s = VaultStore()
                    trig_vals = [x.strip() for x in (triggers or '').split(',') if x.strip()]
                    return s.build_lora_insert_block(lid, strength=float(strength or 1.0), selected_triggers=trig_vals, include_triggers=True)

                def _prompt_refresh(kind: str, q: str, current_id: str, status: str = '✅ Prompt Composer LoRA/TI list refreshed.'):
                    return prompt_composer_lora_refresh(kind=kind, q=q, current_id=current_id, status=status)

                def _show_remote_preview(path: str):
                    p = str(path or '').strip()
                    return p or None

                def _fetch_civitai(lid: str, url: str, merge_mode: str, overwrite_fields, kind: str, q: str, cat: str, base_filter: str, style_filter: str, missing_only: bool, duplicates_only: bool):
                    s = VaultStore()
                    if not lid:
                        empty_dd = gr.update(choices=s.list_lora_choices(q=q, kind=kind, category=cat, base_model=base_filter, style_category=style_filter, missing_only=bool(missing_only), duplicates_only=bool(duplicates_only)), value=None)
                        load_vals = _load_lora('')
                        return (empty_dd, *load_vals, '⚠️ Select a LoRA/TI entry first before importing from CivitAI.')
                    try:
                        result = s.import_civitai_into_lora(lid, url, merge_mode=merge_mode, overwrite_fields=list(overwrite_fields or []))
                    except Exception as e:
                        result = {'ok': False, 'message': f'⚠️ CivitAI import failed: {e}'}
                    dd = gr.update(choices=s.list_lora_choices(q=q, kind=kind, category=cat, base_model=base_filter, style_category=style_filter, missing_only=bool(missing_only), duplicates_only=bool(duplicates_only)), value=lid if result.get('ok') else lid)
                    load_vals = _load_lora(lid)
                    status = result.get('message') or ('✅ CivitAI import complete.' if result.get('ok') else '⚠️ Import failed.')
                    return (dd, *load_vals, status)

                def _apply_selected_preview(lid: str, preview_path: str):
                    s = VaultStore()
                    if not lid or not str(preview_path or '').strip():
                        return None, '', '⚠️ Pick a fetched preview first.'
                    ok = s.set_primary_lora_preview(lid, preview_path)
                    return (preview_path if ok else None), (preview_path if ok else ''), ('✅ Primary preview updated.' if ok else '⚠️ Could not update preview.')

                def _save_lora(lid: str, strength: float, min_strength: float, max_strength: float, triggers: str, keywords: str, style_category: str, base_model: str, example_prompt: str, preview_image: str, caution_notes: str, notes: str, enabled: bool, kind: str, q: str, cat: str, base_filter: str, style_filter: str, missing_only: bool, duplicates_only: bool):
                    s = VaultStore()
                    ok = s.upsert_lora_meta(lid, triggers, keywords, strength, notes, enabled=enabled, min_strength=min_strength, max_strength=max_strength, base_model=base_model, caution_notes=caution_notes, example_prompt=example_prompt, preview_image=preview_image, style_category=style_category)
                    if not ok:
                        return gr.update(choices=s.list_lora_choices(q=q, kind=kind, category=cat, base_model=base_filter, style_category=style_filter, missing_only=bool(missing_only), duplicates_only=bool(duplicates_only))), '⚠️ Nothing to save (select a LoRA first).', _sync_insert_block(lid, strength, triggers)
                    return gr.update(choices=s.list_lora_choices(q=q, kind=kind, category=cat, base_model=base_filter, style_category=style_filter, missing_only=bool(missing_only), duplicates_only=bool(duplicates_only)), value=lid), '✅ Saved.', _sync_insert_block(lid, strength, triggers)

                def _del_lora(lid: str, kind: str, q: str, cat: str, base_filter: str, style_filter: str, missing_only: bool, duplicates_only: bool):
                    s = VaultStore()
                    if not lid:
                        return gr.update(choices=s.list_lora_choices(q=q, kind=kind, category=cat, base_model=base_filter, style_category=style_filter, missing_only=bool(missing_only), duplicates_only=bool(duplicates_only)), value=None), '⚠️ Nothing selected.'
                    s.delete_lora(lid)
                    return gr.update(choices=s.list_lora_choices(q=q, kind=kind, category=cat, base_model=base_filter, style_category=style_filter, missing_only=bool(missing_only), duplicates_only=bool(duplicates_only)), value=None), '🗑️ Deleted.'

                if prompt_refs:
                    pb_inputs = [prompt_refs["l_kind"], prompt_refs["l_search"], prompt_refs["l_dd"]]
                    pb_outputs = [prompt_refs["l_dd"], prompt_refs["l_recent"], prompt_refs["l_file"], prompt_refs["l_rel"], prompt_refs["l_strength"], prompt_refs["l_triggers"], prompt_refs["l_keywords_preview"], prompt_refs["l_example"], prompt_refs["l_insert_block"], prompt_refs["l_preview"], prompt_refs["l_msg"]]

                    def _scan_with_pb(l_dir: str, e_dir: str, inc_ti: bool, kind: str, cat: str, base_model: str, style_cat: str, missing_only: bool, duplicates_only: bool, pb_kind: str, pb_q: str, pb_current: str):
                        dd, cats_u, base_u, style_u, scan_status = _scan(l_dir, e_dir, inc_ti, kind, cat, base_model, style_cat, missing_only, duplicates_only)
                        return dd, cats_u, base_u, style_u, scan_status, *_prompt_refresh(pb_kind, pb_q, pb_current, '✅ Prompt Composer refreshed after scan.')

                    def _fetch_civitai_with_pb(lid: str, url: str, merge_mode: str, overwrite_fields, kind: str, q: str, cat: str, base_filter: str, style_filter: str, missing_only: bool, duplicates_only: bool, pb_kind: str, pb_q: str, pb_current: str):
                        base = _fetch_civitai(lid, url, merge_mode, overwrite_fields, kind, q, cat, base_filter, style_filter, missing_only, duplicates_only)
                        target_current = lid if (str(pb_current or '').strip() == str(lid or '').strip()) else pb_current
                        return (*base, *_prompt_refresh(pb_kind, pb_q, target_current, '✅ Prompt Composer refreshed after CivitAI import.'))

                    def _apply_selected_preview_with_pb(lid: str, preview_path: str, pb_kind: str, pb_q: str, pb_current: str):
                        base = _apply_selected_preview(lid, preview_path)
                        target_current = lid if (str(pb_current or '').strip() == str(lid or '').strip()) else pb_current
                        return (*base, *_prompt_refresh(pb_kind, pb_q, target_current, '✅ Prompt Composer refreshed after preview update.'))

                    def _save_lora_with_pb(lid: str, strength: float, min_strength: float, max_strength: float, triggers: str, keywords: str, style_category: str, base_model: str, example_prompt: str, preview_image: str, caution_notes: str, notes: str, enabled: bool, kind: str, q: str, cat: str, base_filter: str, style_filter: str, missing_only: bool, duplicates_only: bool, pb_kind: str, pb_q: str, pb_current: str):
                        base = _save_lora(lid, strength, min_strength, max_strength, triggers, keywords, style_category, base_model, example_prompt, preview_image, caution_notes, notes, enabled, kind, q, cat, base_filter, style_filter, missing_only, duplicates_only)
                        target_current = lid if (str(pb_current or '').strip() == str(lid or '').strip()) else pb_current
                        return (*base, *_prompt_refresh(pb_kind, pb_q, target_current, '✅ Prompt Composer refreshed after save.'))

                    def _del_lora_with_pb(lid: str, kind: str, q: str, cat: str, base_filter: str, style_filter: str, missing_only: bool, duplicates_only: bool, pb_kind: str, pb_q: str, pb_current: str):
                        base = _del_lora(lid, kind, q, cat, base_filter, style_filter, missing_only, duplicates_only)
                        target_current = None if str(pb_current or '').strip() == str(lid or '').strip() else pb_current
                        return (*base, *_prompt_refresh(pb_kind, pb_q, target_current, '✅ Prompt Composer refreshed after delete.'))

                    scan_btn.click(_scan_with_pb, inputs=[lora_dir, embed_dir, include_ti, lora_kind, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only] + pb_inputs, outputs=[lora_dd, lora_filter_cat, lora_filter_base, lora_filter_style, scan_msg] + pb_outputs)
                    lora_search.change(_refresh_lora_choices, inputs=[lora_search, lora_kind, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only], outputs=[lora_dd])
                    lora_kind.change(_kind_change, inputs=[lora_kind, lora_search, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only], outputs=[lora_dd, lora_filter_cat, lora_filter_base, lora_filter_style])
                    lora_filter_cat.change(_refresh_lora_choices, inputs=[lora_search, lora_kind, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only], outputs=[lora_dd])
                    lora_filter_base.change(_refresh_lora_choices, inputs=[lora_search, lora_kind, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only], outputs=[lora_dd])
                    lora_filter_style.change(_refresh_lora_choices, inputs=[lora_search, lora_kind, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only], outputs=[lora_dd])
                    lora_missing_only.change(_refresh_lora_choices, inputs=[lora_search, lora_kind, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only], outputs=[lora_dd])
                    lora_duplicates_only.change(_refresh_lora_choices, inputs=[lora_search, lora_kind, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only], outputs=[lora_dd])
                    lora_dd.change(_load_lora, inputs=[lora_dd], outputs=[lora_id, lora_file, lora_rel, lora_cat, lora_name, lora_strength, lora_min_strength, lora_max_strength, lora_triggers, lora_keywords, lora_style_category, lora_base_model, lora_example_prompt, lora_preview_image, lora_preview_path, lora_caution, lora_enabled, lora_notes, lora_meta_status, lora_status, lora_warning, lora_insert_block, civitai_url, lora_provider_badge, civitai_preview_pick, civitai_preview_image])
                    lora_strength.change(_sync_insert_block, inputs=[lora_id, lora_strength, lora_triggers], outputs=[lora_insert_block])
                    lora_triggers.change(_sync_insert_block, inputs=[lora_id, lora_strength, lora_triggers], outputs=[lora_insert_block])
                    civitai_preview_pick.change(_show_remote_preview, inputs=[civitai_preview_pick], outputs=[civitai_preview_image])
                    civitai_apply_preview.click(_apply_selected_preview_with_pb, inputs=[lora_id, civitai_preview_pick] + pb_inputs, outputs=[lora_preview_image, lora_preview_path, lora_status] + pb_outputs)
                    civitai_fetch.click(_fetch_civitai_with_pb, inputs=[lora_id, civitai_url, civitai_merge_mode, civitai_overwrite_fields, lora_kind, lora_search, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only] + pb_inputs, outputs=[lora_dd, lora_id, lora_file, lora_rel, lora_cat, lora_name, lora_strength, lora_min_strength, lora_max_strength, lora_triggers, lora_keywords, lora_style_category, lora_base_model, lora_example_prompt, lora_preview_image, lora_preview_path, lora_caution, lora_enabled, lora_notes, lora_meta_status, lora_status, lora_warning, lora_insert_block, civitai_url, lora_provider_badge, civitai_preview_pick, civitai_preview_image, civitai_fetch_status] + pb_outputs)
                    lora_save.click(_save_lora_with_pb, inputs=[lora_id, lora_strength, lora_min_strength, lora_max_strength, lora_triggers, lora_keywords, lora_style_category, lora_base_model, lora_example_prompt, lora_preview_path, lora_caution, lora_notes, lora_enabled, lora_kind, lora_search, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only] + pb_inputs, outputs=[lora_dd, lora_status, lora_insert_block] + pb_outputs)
                    lora_del.click(_del_lora_with_pb, inputs=[lora_id, lora_kind, lora_search, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only] + pb_inputs, outputs=[lora_dd, lora_status] + pb_outputs)
                else:
                    scan_btn.click(_scan, inputs=[lora_dir, embed_dir, include_ti, lora_kind, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only], outputs=[lora_dd, lora_filter_cat, lora_filter_base, lora_filter_style, scan_msg])
                    lora_search.change(_refresh_lora_choices, inputs=[lora_search, lora_kind, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only], outputs=[lora_dd])
                    lora_kind.change(_kind_change, inputs=[lora_kind, lora_search, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only], outputs=[lora_dd, lora_filter_cat, lora_filter_base, lora_filter_style])
                    lora_filter_cat.change(_refresh_lora_choices, inputs=[lora_search, lora_kind, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only], outputs=[lora_dd])
                    lora_filter_base.change(_refresh_lora_choices, inputs=[lora_search, lora_kind, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only], outputs=[lora_dd])
                    lora_filter_style.change(_refresh_lora_choices, inputs=[lora_search, lora_kind, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only], outputs=[lora_dd])
                    lora_missing_only.change(_refresh_lora_choices, inputs=[lora_search, lora_kind, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only], outputs=[lora_dd])
                    lora_duplicates_only.change(_refresh_lora_choices, inputs=[lora_search, lora_kind, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only], outputs=[lora_dd])
                    lora_dd.change(_load_lora, inputs=[lora_dd], outputs=[lora_id, lora_file, lora_rel, lora_cat, lora_name, lora_strength, lora_min_strength, lora_max_strength, lora_triggers, lora_keywords, lora_style_category, lora_base_model, lora_example_prompt, lora_preview_image, lora_preview_path, lora_caution, lora_enabled, lora_notes, lora_meta_status, lora_status, lora_warning, lora_insert_block, civitai_url, lora_provider_badge, civitai_preview_pick, civitai_preview_image])
                    lora_strength.change(_sync_insert_block, inputs=[lora_id, lora_strength, lora_triggers], outputs=[lora_insert_block])
                    lora_triggers.change(_sync_insert_block, inputs=[lora_id, lora_strength, lora_triggers], outputs=[lora_insert_block])
                    civitai_preview_pick.change(_show_remote_preview, inputs=[civitai_preview_pick], outputs=[civitai_preview_image])
                    civitai_apply_preview.click(_apply_selected_preview, inputs=[lora_id, civitai_preview_pick], outputs=[lora_preview_image, lora_preview_path, lora_status])
                    civitai_fetch.click(_fetch_civitai, inputs=[lora_id, civitai_url, civitai_merge_mode, civitai_overwrite_fields, lora_kind, lora_search, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only], outputs=[lora_dd, lora_id, lora_file, lora_rel, lora_cat, lora_name, lora_strength, lora_min_strength, lora_max_strength, lora_triggers, lora_keywords, lora_style_category, lora_base_model, lora_example_prompt, lora_preview_image, lora_preview_path, lora_caution, lora_enabled, lora_notes, lora_meta_status, lora_status, lora_warning, lora_insert_block, civitai_url, lora_provider_badge, civitai_preview_pick, civitai_preview_image, civitai_fetch_status])
                    lora_save.click(_save_lora, inputs=[lora_id, lora_strength, lora_min_strength, lora_max_strength, lora_triggers, lora_keywords, lora_style_category, lora_base_model, lora_example_prompt, lora_preview_path, lora_caution, lora_notes, lora_enabled, lora_kind, lora_search, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only], outputs=[lora_dd, lora_status, lora_insert_block])
                    lora_del.click(_del_lora, inputs=[lora_id, lora_kind, lora_search, lora_filter_cat, lora_filter_base, lora_filter_style, lora_missing_only, lora_duplicates_only], outputs=[lora_dd, lora_status])

            # ---------------- MapSets ----------------
            with gr.Tab("🗺️ MapSets"):

                gr.Markdown("A **mapset** is a saved set of maps (canny/depth/openpose) you can load later in Prompt Builder.")

                with gr.Row():
                    map_search = gr.Textbox(label="Search mapsets", placeholder="piggyback, balcony, hug…", lines=1)
                    map_dd = gr.Dropdown(label="Saved mapsets", choices=store.list_mapset_choices(), value=None)

                map_title = gr.Textbox(label="Mapset title", placeholder="Piggyback Pose A")
                map_tags = gr.Textbox(label="Tags (comma-separated)", placeholder="piggybackride, romantic, carry_pose")

                with gr.Row():
                    btn_map_new = gr.Button("➕ New mapset")
                    btn_map_save = gr.Button("💾 Save meta")
                    btn_map_del = gr.Button("🗑️ Delete", variant="stop")

                map_status = gr.Markdown("")
                with gr.Accordion("Preview maps", open=True):
                    with gr.Row():
                        show_canny = gr.Checkbox(value=True, label="Show Canny")
                        show_depth = gr.Checkbox(value=True, label="Show Depth")
                        show_pose  = gr.Checkbox(value=True, label="Show OpenPose")

                    canny_gallery = gr.Gallery(label="Canny", columns=4, rows=2, height="auto")
                    depth_gallery = gr.Gallery(label="Depth", columns=4, rows=2, height="auto")
                    pose_gallery  = gr.Gallery(label="OpenPose", columns=4, rows=2, height="auto")

                with gr.Accordion("Storage + Import", open=True):
                    gr.Markdown("Import maps into the selected mapset. **No Browse buttons** — paste paths or upload files.")
                    assets_root_tb = gr.Textbox(label="Mapsets root folder", value=str(ASSETS_DIR), interactive=False)
                    with gr.Row():
                        map_folder_tb = gr.Textbox(label="Selected mapset folder", value="", interactive=False)
                        btn_open_mapset_folder = gr.Button("📁 Open", scale=0)

                    with gr.Row():
                        btn_map_refresh = gr.Button("🔄 Refresh previews", scale=0)

                    with gr.Accordion("Batch upload (into selected mapset)", open=False):
                        enforce_suffix_up = gr.Checkbox(label="Enforce suffix (_canny/_depth/_openpose)", value=True)
                        with gr.Row():
                            up_canny = gr.File(label="Upload Canny map(s)", file_count="multiple", file_types=[".png",".jpg",".jpeg",".webp"])
                            btn_add_canny = gr.Button("➕ Add Canny", scale=0)
                        with gr.Row():
                            up_depth = gr.File(label="Upload Depth map(s)", file_count="multiple", file_types=[".png",".jpg",".jpeg",".webp"])
                            btn_add_depth = gr.Button("➕ Add Depth", scale=0)
                        with gr.Row():
                            up_pose = gr.File(label="Upload OpenPose map(s)", file_count="multiple", file_types=[".png",".jpg",".jpeg",".webp"])
                            btn_add_pose = gr.Button("➕ Add OpenPose", scale=0)

                    with gr.Accordion("Import from folder (paste path)", open=False):
                        folder_path = gr.Textbox(label="Folder path", placeholder=r"C:\maps\poseA  or  /workspace/maps/poseA", lines=1)
                        with gr.Row():
                            recursive = gr.Checkbox(label="Recursive", value=False)
                            enforce_suffix_imp = gr.Checkbox(label="Enforce suffix (_canny/_depth/_openpose)", value=True)
                        import_mode = gr.Dropdown(
                            label="How to classify files",
                            choices=["auto-detect by filename", "canny", "depth", "openpose"],
                            value="auto-detect by filename"
                        )
                        btn_import_folder = gr.Button("📂 Import ALL images from folder")

                def _refresh_mapsets(q: str):
                    s = VaultStore()
                    return gr.update(choices=s.list_mapset_choices(q))

                def _mapset_folder(mid: str) -> str:
                    if not mid:
                        return ""
                    try:
                        return str((ASSETS_DIR / mid).resolve())
                    except Exception:
                        return str(ASSETS_DIR / mid)

                def _select_mapset(mid: str):
                    s = VaultStore()
                    m = s.get_mapset(mid) if mid else None
                    if not m:
                        return "", "", "", "", [], [], [], "⚠️ Select a mapset."
                    return (
                        mid,
                        m.get("title",""),
                        ", ".join(m.get("tags") or []),
                        _mapset_folder(mid),
                        s.list_map_paths(mid, "canny"),
                        s.list_map_paths(mid, "depth"),
                        s.list_map_paths(mid, "openpose"),
                        "✅ Loaded."
                    )

                def _new_mapset(title: str, tags_csv: str):
                    s = VaultStore()
                    mid = s.create_mapset(title or "New Mapset", tags_csv or "")
                    m = s.get_mapset(mid) or {}
                    return (
                        gr.update(choices=s.list_mapset_choices(), value=mid),
                        mid,
                        m.get("title",""),
                        ", ".join(m.get("tags") or []),
                        _mapset_folder(mid),
                        [], [], [],
                        "✅ Created."
                    )

                def _save_mapset(mid: str, title: str, tags_csv: str):
                    if not mid:
                        return gr.update(choices=store.list_mapset_choices()), "⚠️ Select a mapset first."
                    s = VaultStore()
                    s.update_mapset_meta(mid, title, tags_csv)
                    return gr.update(choices=s.list_mapset_choices(), value=mid), "✅ Saved."

                def _del_mapset(mid: str):
                    if not mid:
                        return gr.update(choices=store.list_mapset_choices(), value=None), "", "", "", [], [], [], "⚠️ Nothing selected."
                    s = VaultStore()
                    s.delete_mapset(mid)
                    return gr.update(choices=s.list_mapset_choices(), value=None), "", "", "", [], [], [], "🗑️ Deleted."

                def _refresh_previews(mid: str):
                    if not mid:
                        return "", [], [], [], "⚠️ Select a mapset."
                    s = VaultStore()
                    return (
                        _mapset_folder(mid),
                        s.list_map_paths(mid, "canny"),
                        s.list_map_paths(mid, "depth"),
                        s.list_map_paths(mid, "openpose"),
                        "🔄 Refreshed."
                    )

                def _add_uploaded(mid: str, files, map_type: str, enforce_suffix: bool):
                    if not mid:
                        return "", [], [], [], "⚠️ Select a mapset."
                    s = VaultStore()
                    n = s.add_maps_to_mapset(mid, files or [], map_type=map_type, auto_detect=False, enforce_suffix=bool(enforce_suffix))
                    return (
                        _mapset_folder(mid),
                        s.list_map_paths(mid, "canny"),
                        s.list_map_paths(mid, "depth"),
                        s.list_map_paths(mid, "openpose"),
                        f"✅ Added {n} file(s) to **{map_type}**."
                    )

                def _import_from_folder(mid: str, folder: str, rec: bool, mode: str, enforce_suffix: bool):
                    if not mid:
                        return "", [], [], [], "⚠️ Select a mapset."
                    folder = (folder or "").strip().strip('"').strip("'")
                    if not folder or not os.path.isdir(folder):
                        # keep current preview, but show warning
                        p = _refresh_previews(mid)
                        return p[0], p[1], p[2], p[3], "⚠️ Folder not found."
                    exts = {".png",".jpg",".jpeg",".webp"}
                    paths = []
                    if rec:
                        for root, _, files in os.walk(folder):
                            for fn in files:
                                if os.path.splitext(fn)[1].lower() in exts:
                                    paths.append(os.path.join(root, fn))
                    else:
                        for fn in os.listdir(folder):
                            pth = os.path.join(folder, fn)
                            if os.path.isfile(pth) and os.path.splitext(fn)[1].lower() in exts:
                                paths.append(pth)
                    if not paths:
                        p = _refresh_previews(mid)
                        return p[0], p[1], p[2], p[3], "⚠️ No images found in that folder."
                    s = VaultStore()
                    auto_detect = (mode == "auto-detect by filename")
                    map_type = "canny" if auto_detect else mode
                    n = s.add_maps_to_mapset(mid, paths, map_type=map_type, auto_detect=auto_detect, enforce_suffix=bool(enforce_suffix))
                    return (
                        _mapset_folder(mid),
                        s.list_map_paths(mid, "canny"),
                        s.list_map_paths(mid, "depth"),
                        s.list_map_paths(mid, "openpose"),
                        f"✅ Imported {n} file(s) from folder."
                    )

                map_search.change(_refresh_mapsets, inputs=[map_search], outputs=[map_dd])
                map_dd.change(_select_mapset, inputs=[map_dd], outputs=[mapset_id, map_title, map_tags, map_folder_tb, canny_gallery, depth_gallery, pose_gallery, map_status])

                btn_map_new.click(_new_mapset, inputs=[map_title, map_tags], outputs=[map_dd, mapset_id, map_title, map_tags, map_folder_tb, canny_gallery, depth_gallery, pose_gallery, map_status])
                btn_map_save.click(_save_mapset, inputs=[mapset_id, map_title, map_tags], outputs=[map_dd, map_status])
                btn_map_del.click(_del_mapset, inputs=[mapset_id], outputs=[map_dd, mapset_id, map_title, map_tags, map_folder_tb, canny_gallery, depth_gallery, pose_gallery, map_status])

                btn_map_refresh.click(_refresh_previews, inputs=[mapset_id], outputs=[map_folder_tb, canny_gallery, depth_gallery, pose_gallery, map_status])

                btn_open_mapset_folder.click(_open_folder, inputs=[map_folder_tb], outputs=[map_status])

                btn_add_canny.click(_add_uploaded, inputs=[mapset_id, up_canny, gr.State("canny"), enforce_suffix_up], outputs=[map_folder_tb, canny_gallery, depth_gallery, pose_gallery, map_status])
                btn_add_depth.click(_add_uploaded, inputs=[mapset_id, up_depth, gr.State("depth"), enforce_suffix_up], outputs=[map_folder_tb, canny_gallery, depth_gallery, pose_gallery, map_status])
                btn_add_pose.click(_add_uploaded, inputs=[mapset_id, up_pose, gr.State("openpose"), enforce_suffix_up], outputs=[map_folder_tb, canny_gallery, depth_gallery, pose_gallery, map_status])

                btn_import_folder.click(_import_from_folder, inputs=[mapset_id, folder_path, recursive, import_mode, enforce_suffix_imp], outputs=[map_folder_tb, canny_gallery, depth_gallery, pose_gallery, map_status])

                show_canny.change(lambda v: gr.update(visible=v), inputs=[show_canny], outputs=[canny_gallery])
                show_depth.change(lambda v: gr.update(visible=v), inputs=[show_depth], outputs=[depth_gallery])
                show_pose.change(lambda v: gr.update(visible=v), inputs=[show_pose], outputs=[pose_gallery])

    return
