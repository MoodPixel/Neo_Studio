from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal

IMAGE_STATE_VERSION = 'image-state-v1'
ImageMode = Literal['txt2img', 'img2img', 'inpaint', 'preview', 'upscale', 'adetailer', 'supir']


def _dimension(value: Any, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    if number < 64 or number > 8192:
        return fallback
    return number


def _float_range(value: Any, fallback: float, min_value: float, max_value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number < min_value or number > max_value:
        return fallback
    return number


@dataclass(slots=True)
class DynamicThresholdingState:
    enabled: bool = False
    preset: str = 'off'
    mode: str = 'simple'
    node: str = 'DynamicThresholdingSimple'
    mimic_scale: float = 7.0
    threshold_percentile: float = 1.0
    auto_disable_low_cfg: bool = True
    auto_disable_family: bool = True

    @classmethod
    def from_value(cls, value: Any) -> 'DynamicThresholdingState':
        if not isinstance(value, dict):
            return cls()
        preset = str(value.get('preset') or ('advanced' if value.get('enabled') else 'off')).strip().lower()
        if preset not in {'off', 'safe', 'detail_push', 'advanced'}:
            preset = 'advanced' if value.get('enabled') else 'off'
        mode = 'full' if str(value.get('mode') or '').strip().lower() == 'full' else 'simple'
        return cls(
            enabled=bool(value.get('enabled')) and preset != 'off',
            preset=preset,
            mode=mode,
            node='DynamicThresholdingFull' if mode == 'full' else 'DynamicThresholdingSimple',
            mimic_scale=_float_range(value.get('mimic_scale', value.get('mimic_cfg', 7.0)), 7.0, 1.0, 30.0),
            threshold_percentile=_float_range(value.get('threshold_percentile', value.get('percentile', 1.0)), 1.0, 0.80, 1.00),
            auto_disable_low_cfg=value.get('auto_disable_low_cfg') is not False,
            auto_disable_family=value.get('auto_disable_family') is not False,
        )


@dataclass(slots=True)
class ImageBuildState:
    width: int = 1024
    height: int = 1024
    size_source: str = 'default'
    family: str = ''
    checkpoint: str = ''
    sampler: str = ''
    scheduler: str = ''
    seed: int | None = None
    steps: int | None = None
    cfg: float | None = None

    def normalized(self) -> 'ImageBuildState':
        self.width = _dimension(self.width, 1024)
        self.height = _dimension(self.height, 1024)
        return self


@dataclass(slots=True)
class ImagePromptState:
    positive: str = ''
    negative: str = ''
    stack_source: str = 'ui'


@dataclass(slots=True)
class ImageSourceState:
    active_source_image: str | None = None
    selected_output_id: str | None = None
    selected_job_id: str | None = None
    preview_action_target: dict[str, Any] | None = None
    selected_output_snapshot: dict[str, Any] | None = None


@dataclass(slots=True)
class ImageModuleState:
    scene_director: dict[str, Any] | None = None
    dynamic_thresholding: DynamicThresholdingState | dict[str, Any] | None = field(default_factory=DynamicThresholdingState)
    ipadapter: dict[str, Any] | None = None
    controlnet: dict[str, Any] | None = None
    lora_stack: list[dict[str, Any]] | None = None
    embeddings: list[dict[str, Any]] | None = None
    finish_action: dict[str, Any] | None = None


@dataclass(slots=True)
class ImageStateMeta:
    last_update_source: str = 'init'
    last_updated_at: str | None = None
    dirty_keys: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ImageState:
    version: str = IMAGE_STATE_VERSION
    mode: str = 'txt2img'
    workflow_type: str = 'txt2img'
    build: ImageBuildState = field(default_factory=ImageBuildState)
    prompt: ImagePromptState = field(default_factory=ImagePromptState)
    source: ImageSourceState = field(default_factory=ImageSourceState)
    modules: ImageModuleState = field(default_factory=ImageModuleState)
    meta: ImageStateMeta = field(default_factory=ImageStateMeta)

    def normalized(self) -> 'ImageState':
        self.version = IMAGE_STATE_VERSION
        self.mode = str(self.mode or self.workflow_type or 'txt2img')
        self.workflow_type = str(self.workflow_type or self.mode or 'txt2img')
        self.build.normalized()
        self.modules.dynamic_thresholding = DynamicThresholdingState.from_value(self.modules.dynamic_thresholding if isinstance(self.modules.dynamic_thresholding, dict) else asdict(self.modules.dynamic_thresholding or DynamicThresholdingState()))
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.normalized())


def default_image_state() -> dict[str, Any]:
    return ImageState().to_dict()
