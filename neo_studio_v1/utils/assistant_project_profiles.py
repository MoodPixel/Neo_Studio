from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

PROJECT_PROFILE_VERSION = 'assistant_project_profiles_v1'

PROJECT_TYPE_PROFILES: Dict[str, Dict[str, Any]] = {
    'general': {
        'id': 'general',
        'label': 'General',
        'description': 'Flexible project context for notes, planning, mixed tasks, and ordinary assistant work.',
        'memory_focus': ['project_summary', 'user_context', 'reference_notes', 'task_history'],
        'context_rules': [
            'Use project context only when it clearly relates to the current request.',
            'Prefer current session instructions over older project notes when they conflict.',
        ],
        'repo_index_enabled': False,
        'recommended_memory_lane': 'assistant',
    },
    'software': {
        'id': 'software',
        'label': 'Software / Codebase',
        'description': 'Code, repo, architecture, implementation phases, bugs, fixes, and validation logs.',
        'memory_focus': ['repo_fact', 'implementation_decision', 'bug_history', 'fix_pattern', 'validation_result', 'guardrail'],
        'context_rules': [
            'Prioritize exact file paths, contracts, validation results, and recent implementation decisions.',
            'Use repo index context when the request asks about code, files, routes, patches, or architecture.',
            'Do not assume runtime behavior without checking code or records when available.',
        ],
        'repo_index_enabled': True,
        'recommended_memory_lane': 'neo_project',
    },
    'universe': {
        'id': 'universe',
        'label': 'Universe / Worldbuilding',
        'description': 'Lore, canon, worlds, characters, factions, timelines, truth layers, and continuity rules.',
        'memory_focus': ['canon_guard', 'world_fact', 'entity_profile', 'timeline_event', 'relationship', 'open_question', 'draft_variant'],
        'context_rules': [
            'Keep canon, draft, disputed, deprecated, and author-only material separated.',
            'When answering lore questions, state whether the answer is confirmed canon, draft, disputed, or inferred.',
            'Before adding new lore, check project canon guards, entity relationships, and contradiction notes.',
            'Preserve public-vs-hidden truth layers instead of flattening everything into one literal summary.',
        ],
        'repo_index_enabled': False,
        'recommended_memory_lane': 'assistant',
    },
    'freelance_business': {
        'id': 'freelance_business',
        'label': 'Freelance Business / Client Work',
        'description': 'Client communication, pricing, offers, delivery rules, revisions, portfolio, and work history.',
        'memory_focus': ['client_preference', 'pricing_rule', 'offer_template', 'delivery_scope', 'boundary_rule', 'followup_note'],
        'context_rules': [
            'Keep client-specific context scoped to the project/client.',
            'Prioritize clear scope, pricing boundaries, deliverables, and professional tone.',
            'Do not mix private creative lore/project data into client communication context.',
        ],
        'repo_index_enabled': False,
        'recommended_memory_lane': 'assistant',
    },
    'creative_library': {
        'id': 'creative_library',
        'label': 'Creative Library / Assets',
        'description': 'Reusable prompts, visual styles, references, lyrics, concepts, presets, and asset notes.',
        'memory_focus': ['style_reference', 'prompt_pattern', 'asset_note', 'creative_rule', 'example_output'],
        'context_rules': [
            'Retrieve style examples only when they match the active creative goal.',
            'Separate reusable style rules from one-off draft experiments.',
        ],
        'repo_index_enabled': False,
        'recommended_memory_lane': 'assistant',
    },
    'custom': {
        'id': 'custom',
        'label': 'Custom',
        'description': 'User-defined project type with custom memory and context behavior.',
        'memory_focus': ['custom_fact', 'custom_rule', 'custom_reference', 'task_history'],
        'context_rules': [
            'Follow the custom type label, description, memory focus, and context rules saved on the project.',
            'If custom rules are vague, behave like a general project and ask for structure only when needed.',
        ],
        'repo_index_enabled': False,
        'recommended_memory_lane': 'assistant',
    },
}

PROJECT_TYPE_ALIASES = {
    'code': 'software',
    'repo': 'software',
    'repository': 'software',
    'world': 'universe',
    'worldbuilding': 'universe',
    'universe_worldbuilding': 'universe',
    'universe/worldbuilding': 'universe',
    'business': 'freelance_business',
    'client': 'freelance_business',
    'freelance': 'freelance_business',
    'assets': 'creative_library',
    'creative': 'creative_library',
}


def clean_project_type(value: Any) -> str:
    raw = str(value or 'general').strip().lower().replace(' ', '_').replace('-', '_')
    raw = PROJECT_TYPE_ALIASES.get(raw, raw)
    return raw if raw in PROJECT_TYPE_PROFILES else 'general'


def list_project_profiles() -> Dict[str, Dict[str, Any]]:
    return deepcopy(PROJECT_TYPE_PROFILES)


def sanitize_custom_profile(value: Any) -> Dict[str, Any]:
    src = value if isinstance(value, dict) else {}
    memory_focus = src.get('memory_focus') if isinstance(src.get('memory_focus'), list) else []
    context_rules = src.get('context_rules') if isinstance(src.get('context_rules'), list) else []
    do_not_mix = src.get('do_not_mix') if isinstance(src.get('do_not_mix'), list) else []
    return {
        'label': str(src.get('label') or src.get('custom_type_label') or '').strip()[:120],
        'description': str(src.get('description') or src.get('custom_type_description') or '').strip()[:1200],
        'memory_focus': [str(item or '').strip()[:80] for item in memory_focus if str(item or '').strip()][:16],
        'context_rules': [str(item or '').strip()[:220] for item in context_rules if str(item or '').strip()][:16],
        'do_not_mix': [str(item or '').strip()[:120] for item in do_not_mix if str(item or '').strip()][:16],
    }


def resolve_project_profile(project: Dict[str, Any] | None) -> Dict[str, Any]:
    project = project if isinstance(project, dict) else {}
    project_type = clean_project_type(project.get('project_type'))
    base = deepcopy(PROJECT_TYPE_PROFILES.get(project_type) or PROJECT_TYPE_PROFILES['general'])
    custom = sanitize_custom_profile(project.get('custom_profile'))
    if project_type == 'custom':
        if custom.get('label'):
            base['label'] = custom['label']
        if custom.get('description'):
            base['description'] = custom['description']
        if custom.get('memory_focus'):
            base['memory_focus'] = custom['memory_focus']
        if custom.get('context_rules'):
            base['context_rules'] = custom['context_rules']
    base['project_type'] = project_type
    base['custom_profile'] = custom
    base['display_label'] = base.get('label') or project_type.replace('_', ' ').title()
    return base


def project_profile_prompt_block(project: Dict[str, Any] | None) -> str:
    profile = resolve_project_profile(project)
    lines = [
        f"Project type: {profile.get('display_label') or 'General'} ({profile.get('project_type') or 'general'}).",
        f"Project behavior: {profile.get('description') or ''}",
    ]
    memory_focus = profile.get('memory_focus') if isinstance(profile.get('memory_focus'), list) else []
    context_rules = profile.get('context_rules') if isinstance(profile.get('context_rules'), list) else []
    do_not_mix = (profile.get('custom_profile') or {}).get('do_not_mix') if isinstance(profile.get('custom_profile'), dict) else []
    if memory_focus:
        lines.append('Memory focus: ' + ', '.join(str(item) for item in memory_focus[:16]))
    if context_rules:
        lines.append('Context rules:\n' + '\n'.join(f'- {rule}' for rule in context_rules[:12]))
    if do_not_mix:
        lines.append('Do not mix with: ' + ', '.join(str(item) for item in do_not_mix[:12]))
    return '\n'.join(line for line in lines if str(line or '').strip()).strip()


def should_use_repo_index(project: Dict[str, Any] | None) -> bool:
    profile = resolve_project_profile(project)
    return bool(profile.get('repo_index_enabled'))
