"""Feature pipeline รุ่นทดลองสำหรับลำดับ landmark ของ HandVox.

โมดูลนี้รับข้อมูลดิบรูป ``(T, 171)`` ที่สร้างโดย :mod:`body_features`
และเก็บ 171 ค่าเดิมไว้เป็นส่วนแรกของผลลัพธ์เสมอ จากนั้นจึงเพิ่มพิกัดมือ
เฉพาะที่ รูปทรงมือ สถานะการมองเห็น และการเคลื่อนไหวตามเวลา

Augmentation ในไฟล์นี้ไม่มีการสลับซ้าย-ขวา เพราะมือหลักและทิศทางอาจเป็น
ส่วนหนึ่งของความหมายภาษามือ ผู้เรียกต้องระบุ ``training=True`` อย่างชัดเจน
จึงจะมีการดัดแปลงข้อมูลเกิดขึ้น
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from body_features import FEATURE_COUNT, HAND_POINTS, POSE_IDS, feature_columns as raw_feature_columns


FEATURE_SCHEMA_VERSION = "handvox.temporal_landmarks.v2"
INPUT_FEATURE_COUNT = FEATURE_COUNT
POSE_POINT_COUNT = len(POSE_IDS)
LANDMARK_COUNT = POSE_POINT_COUNT + HAND_POINTS * 2

POSE_FEATURE_COUNT = POSE_POINT_COUNT * 3
HAND_FEATURE_COUNT = HAND_POINTS * 3
LOCAL_HAND_FEATURE_COUNT = HAND_FEATURE_COUNT * 2
HAND_ANGLE_FEATURE_COUNT = 15 * 2
HAND_DISTANCE_FEATURE_COUNT = 5 * 2
HAND_GEOMETRY_FEATURE_COUNT = HAND_ANGLE_FEATURE_COUNT + HAND_DISTANCE_FEATURE_COUNT
VISIBILITY_FEATURE_COUNT = 2
VELOCITY_FEATURE_COUNT = INPUT_FEATURE_COUNT
OUTPUT_FEATURE_COUNT = (
    INPUT_FEATURE_COUNT
    + LOCAL_HAND_FEATURE_COUNT
    + HAND_GEOMETRY_FEATURE_COUNT
    + VISIBILITY_FEATURE_COUNT
    + VELOCITY_FEATURE_COUNT
)

POSE_FEATURE_SLICE = slice(0, POSE_FEATURE_COUNT)
LEFT_HAND_FEATURE_SLICE = slice(POSE_FEATURE_COUNT, POSE_FEATURE_COUNT + HAND_FEATURE_COUNT)
RIGHT_HAND_FEATURE_SLICE = slice(
    POSE_FEATURE_COUNT + HAND_FEATURE_COUNT,
    POSE_FEATURE_COUNT + HAND_FEATURE_COUNT * 2,
)

BASE_OUTPUT_SLICE = slice(0, INPUT_FEATURE_COUNT)
LOCAL_HAND_OUTPUT_SLICE = slice(
    INPUT_FEATURE_COUNT, INPUT_FEATURE_COUNT + LOCAL_HAND_FEATURE_COUNT
)
HAND_GEOMETRY_OUTPUT_SLICE = slice(
    LOCAL_HAND_OUTPUT_SLICE.stop,
    LOCAL_HAND_OUTPUT_SLICE.stop + HAND_GEOMETRY_FEATURE_COUNT,
)
VISIBILITY_OUTPUT_SLICE = slice(
    HAND_GEOMETRY_OUTPUT_SLICE.stop,
    HAND_GEOMETRY_OUTPUT_SLICE.stop + VISIBILITY_FEATURE_COUNT,
)
VELOCITY_OUTPUT_SLICE = slice(VISIBILITY_OUTPUT_SLICE.stop, OUTPUT_FEATURE_COUNT)

_HAND_SLICES = (LEFT_HAND_FEATURE_SLICE, RIGHT_HAND_FEATURE_SLICE)
_HAND_NAMES = ("left", "right")
_FINGER_CHAINS = (
    ("thumb", (0, 1, 2, 3, 4)),
    ("index", (0, 5, 6, 7, 8)),
    ("middle", (0, 9, 10, 11, 12)),
    ("ring", (0, 13, 14, 15, 16)),
    ("pinky", (0, 17, 18, 19, 20)),
)
_FINGER_TIPS = (4, 8, 12, 16, 20)
_PALM_POINTS = (5, 9, 13, 17)
_MISSING_EPSILON = 1e-8
_SCALE_EPSILON = 1e-6


@dataclass(frozen=True)
class AugmentationConfig:
    """ขอบเขต augmentation แบบเบาสำหรับข้อมูล landmark ชุดฝึกเท่านั้น."""

    rotation_degrees: float = 5.0
    translation_max: float = 0.025
    scale_min: float = 0.95
    scale_max: float = 1.05
    jitter_std: float = 0.003
    time_scale_min: float = 0.92
    time_scale_max: float = 1.08
    frame_drop_probability: float = 0.05

    def __post_init__(self) -> None:
        if self.rotation_degrees < 0:
            raise ValueError("rotation_degrees ต้องไม่ติดลบ")
        if self.translation_max < 0:
            raise ValueError("translation_max ต้องไม่ติดลบ")
        if self.scale_min <= 0 or self.scale_max < self.scale_min:
            raise ValueError("ช่วง scale ไม่ถูกต้อง")
        if self.jitter_std < 0:
            raise ValueError("jitter_std ต้องไม่ติดลบ")
        if self.time_scale_min <= 0 or self.time_scale_max < self.time_scale_min:
            raise ValueError("ช่วง time scale ไม่ถูกต้อง")
        if not 0 <= self.frame_drop_probability < 1:
            raise ValueError("frame_drop_probability ต้องอยู่ในช่วง [0, 1)")


@dataclass(frozen=True)
class FeaturePipelineConfig:
    """ค่าตั้งต้นสำหรับเตรียมหนึ่ง sequence ให้มีขนาดคงที่."""

    target_length: int = 30
    max_missing_gap: int = 2
    trim_motion: bool = False
    motion_threshold: float = 0.015
    trim_padding: int = 2
    minimum_trimmed_frames: int = 5
    augmentation: AugmentationConfig = field(default_factory=AugmentationConfig)

    def __post_init__(self) -> None:
        if self.target_length <= 0:
            raise ValueError("target_length ต้องมากกว่า 0")
        if self.max_missing_gap < 0:
            raise ValueError("max_missing_gap ต้องไม่ติดลบ")
        if self.motion_threshold < 0:
            raise ValueError("motion_threshold ต้องไม่ติดลบ")
        if self.trim_padding < 0:
            raise ValueError("trim_padding ต้องไม่ติดลบ")
        if self.minimum_trimmed_frames <= 0:
            raise ValueError("minimum_trimmed_frames ต้องมากกว่า 0")


def validate_raw_sequence(sequence: np.ndarray | Sequence[Sequence[float]]) -> np.ndarray:
    """ตรวจและคืนสำเนา ``float32`` ของ sequence รูป ``(T, 171)``."""

    values = np.asarray(sequence, dtype=np.float32)
    if values.ndim != 2 or values.shape[1] != INPUT_FEATURE_COUNT:
        raise ValueError(
            f"sequence ต้องมีรูป (T, {INPUT_FEATURE_COUNT}) แต่ได้รับ {values.shape}"
        )
    if values.shape[0] == 0:
        raise ValueError("sequence ต้องมีอย่างน้อย 1 เฟรม")
    if not np.isfinite(values).all():
        raise ValueError("sequence มีค่า NaN หรือ Infinity")
    return values.copy()


def hand_visibility(sequence: np.ndarray | Sequence[Sequence[float]]) -> np.ndarray:
    """คืน mask รูป ``(T, 2)`` ตามบล็อกมือที่ไม่ได้ถูกเติมศูนย์ทั้งข้าง."""

    values = validate_raw_sequence(sequence)
    masks = [
        np.any(np.abs(values[:, hand_slice]) > _MISSING_EPSILON, axis=1)
        for hand_slice in _HAND_SLICES
    ]
    return np.stack(masks, axis=1)


def _visibility_without_copy(values: np.ndarray) -> np.ndarray:
    masks = [
        np.any(np.abs(values[:, hand_slice]) > _MISSING_EPSILON, axis=1)
        for hand_slice in _HAND_SLICES
    ]
    return np.stack(masks, axis=1)


def _false_runs(mask: np.ndarray):
    index = 0
    while index < len(mask):
        if mask[index]:
            index += 1
            continue
        start = index
        while index < len(mask) and not mask[index]:
            index += 1
        yield start, index


def interpolate_short_hand_gaps(
    sequence: np.ndarray | Sequence[Sequence[float]], *, max_gap: int = 2
) -> np.ndarray:
    """เติมช่วงมือหายสั้น ๆ ที่มีเฟรมจริงประกบทั้งสองด้านด้วยเส้นตรง.

    ช่วงที่หายตรงต้น/ท้ายหรือยาวเกิน ``max_gap`` จะยังเป็นศูนย์ เพื่อไม่สร้าง
    landmark มือปลอมในช่วงที่กล้องไม่เห็นมือจริง
    """

    if max_gap < 0:
        raise ValueError("max_gap ต้องไม่ติดลบ")
    values = validate_raw_sequence(sequence)
    if max_gap == 0 or len(values) < 3:
        return values

    masks = _visibility_without_copy(values)
    for hand_index, hand_slice in enumerate(_HAND_SLICES):
        for start, stop in _false_runs(masks[:, hand_index]):
            gap_length = stop - start
            if (
                gap_length > max_gap
                or start == 0
                or stop == len(values)
                or not masks[start - 1, hand_index]
                or not masks[stop, hand_index]
            ):
                continue
            before = values[start - 1, hand_slice]
            after = values[stop, hand_slice]
            for offset in range(gap_length):
                weight = (offset + 1) / (gap_length + 1)
                values[start + offset, hand_slice] = before * (1 - weight) + after * weight
    return values


def _sample_raw_at_positions(values: np.ndarray, positions: np.ndarray) -> np.ndarray:
    """Linear sampling ที่รักษาสถานะมือหายด้วย mask แบบ nearest-neighbour."""

    if len(values) == 1:
        sampled = np.repeat(values, len(positions), axis=0)
        return sampled.astype(np.float32, copy=False)

    positions = np.clip(np.asarray(positions, dtype=np.float64), 0, len(values) - 1)
    lower = np.floor(positions).astype(int)
    upper = np.minimum(lower + 1, len(values) - 1)
    weight = (positions - lower).astype(np.float32)[:, None]
    sampled = values[lower] * (1 - weight) + values[upper] * weight

    source_masks = _visibility_without_copy(values)
    nearest = np.floor(positions + 0.5).astype(int)
    nearest = np.clip(nearest, 0, len(values) - 1)
    sampled_masks = source_masks[nearest]
    for hand_index, hand_slice in enumerate(_HAND_SLICES):
        sampled[~sampled_masks[:, hand_index], hand_slice] = 0.0
    return sampled.astype(np.float32, copy=False)


def resample_sequence(
    sequence: np.ndarray | Sequence[Sequence[float]], target_length: int
) -> np.ndarray:
    """ปรับจำนวนเฟรมด้วย linear interpolation โดยคงเฟรมแรกและสุดท้าย."""

    if target_length <= 0:
        raise ValueError("target_length ต้องมากกว่า 0")
    values = validate_raw_sequence(sequence)
    positions = np.linspace(0, len(values) - 1, target_length, dtype=np.float64)
    return _sample_raw_at_positions(values, positions)


def _expand_window(start: int, stop: int, total: int, minimum: int) -> tuple[int, int]:
    required = min(minimum, total)
    missing = required - (stop - start)
    if missing <= 0:
        return start, stop
    grow_left = missing // 2
    grow_right = missing - grow_left
    start = max(0, start - grow_left)
    stop = min(total, stop + grow_right)
    if stop - start < required:
        if start == 0:
            stop = min(total, required)
        else:
            start = max(0, total - required)
    return start, stop


def trim_motion_window(
    sequence: np.ndarray | Sequence[Sequence[float]],
    *,
    motion_threshold: float = 0.015,
    padding: int = 2,
    minimum_frames: int = 5,
) -> np.ndarray:
    """ตัดขอบนิ่งจากการเคลื่อนของข้อมือ โดยไม่ตัดท่าที่ตรวจการเคลื่อนไหวไม่ได้.

    หากไม่มีเฟรมใดเกิน threshold จะคืน sequence เดิม เหมาะกับท่าคงรูปที่ไม่ควร
    ถูกตัดทิ้งเพียงเพราะข้อมือเคลื่อนน้อย
    """

    if motion_threshold < 0:
        raise ValueError("motion_threshold ต้องไม่ติดลบ")
    if padding < 0:
        raise ValueError("padding ต้องไม่ติดลบ")
    if minimum_frames <= 0:
        raise ValueError("minimum_frames ต้องมากกว่า 0")

    values = validate_raw_sequence(sequence)
    if len(values) < 2:
        return values

    points = values.reshape(len(values), LANDMARK_COUNT, 3)
    masks = _visibility_without_copy(values)
    pose_left_wrist = POSE_IDS.index(15)
    pose_right_wrist = POSE_IDS.index(16)
    point_ids = (pose_left_wrist, pose_right_wrist, POSE_POINT_COUNT, POSE_POINT_COUNT + HAND_POINTS)

    valid = np.ones((len(values), len(point_ids)), dtype=bool)
    valid[:, 2] = masks[:, 0]
    valid[:, 3] = masks[:, 1]
    motion = np.zeros(len(values), dtype=np.float32)
    for frame in range(1, len(values)):
        pair_valid = valid[frame - 1] & valid[frame]
        if not np.any(pair_valid):
            continue
        previous = points[frame - 1, list(point_ids)][pair_valid]
        current = points[frame, list(point_ids)][pair_valid]
        motion[frame] = np.linalg.norm(current - previous, axis=1).mean()

    active = np.flatnonzero(motion >= motion_threshold)
    if len(active) == 0:
        return values
    start = max(0, int(active[0]) - 1 - padding)
    stop = min(len(values), int(active[-1]) + 1 + padding)
    start, stop = _expand_window(start, stop, len(values), minimum_frames)
    return values[start:stop].copy()


def _rotation_matrix_z(angle_radians: float) -> np.ndarray:
    cosine = np.cos(angle_radians)
    sine = np.sin(angle_radians)
    return np.asarray(
        ((cosine, -sine, 0.0), (sine, cosine, 0.0), (0.0, 0.0, 1.0)),
        dtype=np.float32,
    )


def augment_sequence(
    sequence: np.ndarray | Sequence[Sequence[float]],
    *,
    training: bool,
    seed: int | np.random.Generator | None = None,
    config: AugmentationConfig | None = None,
) -> np.ndarray:
    """ทำ augmentation เมื่อ ``training=True`` และรักษารูป/ความยาวเดิม.

    การแปลงประกอบด้วย rotation, scale, jitter, time scaling และ frame drop
    ขนาดเล็กเท่านั้น ฟังก์ชันนี้จงใจไม่มีตัวเลือก mirror ซ้าย-ขวา
    """

    values = validate_raw_sequence(sequence)
    if not training:
        return values
    options = config or AugmentationConfig()
    generator = seed if isinstance(seed, np.random.Generator) else np.random.default_rng(seed)
    original_masks = _visibility_without_copy(values)

    points = values.reshape(len(values), LANDMARK_COUNT, 3).copy()
    angle = np.deg2rad(generator.uniform(-options.rotation_degrees, options.rotation_degrees))
    scale = generator.uniform(options.scale_min, options.scale_max)
    points = (points @ _rotation_matrix_z(float(angle)).T) * np.float32(scale)

    observed = np.ones((len(values), LANDMARK_COUNT), dtype=bool)
    observed[:, POSE_POINT_COUNT : POSE_POINT_COUNT + HAND_POINTS] = original_masks[:, 0, None]
    observed[:, POSE_POINT_COUNT + HAND_POINTS :] = original_masks[:, 1, None]
    if options.translation_max > 0:
        translation = np.asarray(
            (
                generator.uniform(-options.translation_max, options.translation_max),
                generator.uniform(-options.translation_max, options.translation_max),
                0.0,
            ),
            dtype=np.float32,
        )
        points += translation[None, None, :] * observed[:, :, None]
    if options.jitter_std > 0:
        jitter = generator.normal(0.0, options.jitter_std, size=points.shape).astype(np.float32)
        points += jitter * observed[:, :, None]
    values = points.reshape(len(values), INPUT_FEATURE_COUNT).astype(np.float32, copy=False)
    for hand_index, hand_slice in enumerate(_HAND_SLICES):
        values[~original_masks[:, hand_index], hand_slice] = 0.0

    if len(values) > 1:
        time_scale = generator.uniform(options.time_scale_min, options.time_scale_max)
        center = (len(values) - 1) / 2
        positions = center + (np.arange(len(values), dtype=np.float64) - center) * time_scale
        values = _sample_raw_at_positions(values, np.clip(positions, 0, len(values) - 1))

    if len(values) > 2 and options.frame_drop_probability > 0:
        keep = generator.random(len(values)) >= options.frame_drop_probability
        keep[0] = True
        keep[-1] = True
        if np.count_nonzero(keep) < len(values):
            retained = values[keep]
            positions = np.linspace(0, len(retained) - 1, len(values), dtype=np.float64)
            values = _sample_raw_at_positions(retained, positions)
    return values.astype(np.float32, copy=False)


def _safe_angle(first: np.ndarray, center: np.ndarray, last: np.ndarray) -> float:
    first_vector = first - center
    last_vector = last - center
    denominator = float(np.linalg.norm(first_vector) * np.linalg.norm(last_vector))
    if denominator <= _SCALE_EPSILON:
        return 0.0
    cosine = float(np.dot(first_vector, last_vector) / denominator)
    return float(np.arccos(np.clip(cosine, -1.0, 1.0)) / np.pi)


def _local_hand_and_geometry(hand_values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    points = hand_values.reshape(HAND_POINTS, 3)
    wrist = points[0]
    palm_lengths = np.linalg.norm(points[list(_PALM_POINTS)] - wrist, axis=1)
    positive_lengths = palm_lengths[palm_lengths > _SCALE_EPSILON]
    if len(positive_lengths) == 0:
        return (
            np.zeros(HAND_FEATURE_COUNT, dtype=np.float32),
            np.zeros(20, dtype=np.float32),
        )
    palm_scale = max(float(np.median(positive_lengths)), _SCALE_EPSILON)
    local = (points - wrist) / palm_scale

    angles = []
    for _, chain in _FINGER_CHAINS:
        for joint in range(1, 4):
            angles.append(_safe_angle(local[chain[joint - 1]], local[chain[joint]], local[chain[joint + 1]]))
    distances = [float(np.linalg.norm(local[tip])) for tip in _FINGER_TIPS]
    geometry = np.asarray(angles + distances, dtype=np.float32)
    return local.reshape(-1).astype(np.float32), geometry


def extract_temporal_features(
    sequence: np.ndarray | Sequence[Sequence[float]],
) -> np.ndarray:
    """แปลง raw sequence เป็น feature schema v2 รูป ``(T, 510)``.

    171 ช่องแรกเหมือน input ทุกค่า จึงยังตรวจย้อนหลังกับข้อมูลดั้งเดิมได้
    ความเร็วของมือจะเป็นศูนย์ตรงรอยต่อที่มือหายหรือกลับเข้าภาพ เพื่อไม่ให้
    zero-fill ถูกตีความเป็นการเคลื่อนที่เร็วผิดปกติ
    """

    values = validate_raw_sequence(sequence)
    masks = _visibility_without_copy(values)
    local_hands = np.zeros((len(values), LOCAL_HAND_FEATURE_COUNT), dtype=np.float32)
    geometry = np.zeros((len(values), HAND_GEOMETRY_FEATURE_COUNT), dtype=np.float32)

    for frame in range(len(values)):
        for hand_index, hand_slice in enumerate(_HAND_SLICES):
            if not masks[frame, hand_index]:
                continue
            local, hand_geometry = _local_hand_and_geometry(values[frame, hand_slice])
            local_start = hand_index * HAND_FEATURE_COUNT
            geometry_start = hand_index * 20
            local_hands[frame, local_start : local_start + HAND_FEATURE_COUNT] = local
            geometry[frame, geometry_start : geometry_start + 20] = hand_geometry

    velocity = np.zeros_like(values)
    if len(values) > 1:
        velocity[1:] = values[1:] - values[:-1]
        for hand_index, hand_slice in enumerate(_HAND_SLICES):
            valid_pair = masks[1:, hand_index] & masks[:-1, hand_index]
            velocity[1:, hand_slice] *= valid_pair[:, None]

    result = np.concatenate(
        (values, local_hands, geometry, masks.astype(np.float32), velocity), axis=1
    ).astype(np.float32, copy=False)
    if result.shape[1] != OUTPUT_FEATURE_COUNT:
        raise RuntimeError("จำนวน feature ที่สร้างไม่ตรงกับ schema")
    return result


def prepare_raw_sequence(
    sequence: np.ndarray | Sequence[Sequence[float]],
    *,
    config: FeaturePipelineConfig | None = None,
    training: bool = False,
    seed: int | np.random.Generator | None = None,
) -> np.ndarray:
    """interpolate, ตัดช่วง (ถ้าเปิด), resample และ augment ข้อมูลดิบ."""

    options = config or FeaturePipelineConfig()
    values = interpolate_short_hand_gaps(sequence, max_gap=options.max_missing_gap)
    if options.trim_motion:
        values = trim_motion_window(
            values,
            motion_threshold=options.motion_threshold,
            padding=options.trim_padding,
            minimum_frames=options.minimum_trimmed_frames,
        )
    values = resample_sequence(values, options.target_length)
    return augment_sequence(
        values,
        training=training,
        seed=seed,
        config=options.augmentation,
    )


def process_sequence(
    sequence: np.ndarray | Sequence[Sequence[float]],
    *,
    config: FeaturePipelineConfig | None = None,
    training: bool = False,
    seed: int | np.random.Generator | None = None,
) -> np.ndarray:
    """เตรียม raw sequence แล้วคืน feature v2 ที่พร้อมส่งเข้าโมเดล."""

    prepared = prepare_raw_sequence(sequence, config=config, training=training, seed=seed)
    return extract_temporal_features(prepared)


class TemporalFeaturePipeline:
    """อ็อบเจ็กต์ขนาดเล็กสำหรับผูก config เดียวกันใน train และ inference."""

    schema_version = FEATURE_SCHEMA_VERSION
    input_feature_count = INPUT_FEATURE_COUNT
    output_feature_count = OUTPUT_FEATURE_COUNT

    def __init__(self, config: FeaturePipelineConfig | None = None):
        self.config = config or FeaturePipelineConfig()

    def prepare_raw(
        self,
        sequence: np.ndarray | Sequence[Sequence[float]],
        *,
        training: bool = False,
        seed: int | np.random.Generator | None = None,
    ) -> np.ndarray:
        return prepare_raw_sequence(
            sequence, config=self.config, training=training, seed=seed
        )

    def transform(
        self,
        sequence: np.ndarray | Sequence[Sequence[float]],
        *,
        training: bool = False,
        seed: int | np.random.Generator | None = None,
    ) -> np.ndarray:
        return process_sequence(sequence, config=self.config, training=training, seed=seed)


def feature_columns() -> list[str]:
    """คืนชื่อช่องทั้งหมดตามลำดับของ ``extract_temporal_features``."""

    raw_names = raw_feature_columns()
    local_names = [
        f"{hand}_local_{point}_{axis}"
        for hand in _HAND_NAMES
        for point in range(HAND_POINTS)
        for axis in "xyz"
    ]
    geometry_names = []
    for hand in _HAND_NAMES:
        for finger, _ in _FINGER_CHAINS:
            geometry_names.extend(
                f"{hand}_{finger}_joint_angle_{joint}" for joint in range(3)
            )
        geometry_names.extend(
            f"{hand}_{finger}_tip_to_wrist" for finger, _ in _FINGER_CHAINS
        )
    visibility_names = ["left_hand_visible", "right_hand_visible"]
    velocity_names = [f"velocity_{name}" for name in raw_names]
    names = raw_names + local_names + geometry_names + visibility_names + velocity_names
    if len(names) != OUTPUT_FEATURE_COUNT:
        raise RuntimeError("จำนวนชื่อ feature ไม่ตรงกับ schema")
    return names


def schema_metadata() -> dict[str, object]:
    """คืน metadata สั้น ๆ สำหรับบันทึกร่วมกับโมเดลในอนาคต."""

    return {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "input_feature_count": INPUT_FEATURE_COUNT,
        "output_feature_count": OUTPUT_FEATURE_COUNT,
        "preserves_raw_prefix": True,
        "left_right_mirroring": False,
    }
