"""ทดสอบ feature pipeline v2 โดยไม่เชื่อมกับกล้องหรือขั้นเทรนจริง."""

import unittest

import numpy as np

from handvox.feature_pipeline import (
    BASE_OUTPUT_SLICE,
    FEATURE_SCHEMA_VERSION,
    HAND_GEOMETRY_OUTPUT_SLICE,
    INPUT_FEATURE_COUNT,
    LEFT_HAND_FEATURE_SLICE,
    LOCAL_HAND_OUTPUT_SLICE,
    OUTPUT_FEATURE_COUNT,
    RIGHT_HAND_FEATURE_SLICE,
    VELOCITY_OUTPUT_SLICE,
    VISIBILITY_OUTPUT_SLICE,
    AugmentationConfig,
    FeaturePipelineConfig,
    TemporalFeaturePipeline,
    augment_sequence,
    extract_temporal_features,
    feature_columns,
    hand_visibility,
    interpolate_short_hand_gaps,
    process_sequence,
    resample_sequence,
    schema_metadata,
    trim_motion_window,
    validate_raw_sequence,
)


def _hand_points(offset=(0.2, -0.1, 0.05), scale=1.0):
    """สร้างโครงมือที่ไม่เสื่อมสภาพและมี 21 จุดสำหรับการทดสอบ."""

    points = np.zeros((21, 3), dtype=np.float32)
    points[0] = (0.0, 0.0, 0.0)
    chains = (
        (1, 2, 3, 4),
        (5, 6, 7, 8),
        (9, 10, 11, 12),
        (13, 14, 15, 16),
        (17, 18, 19, 20),
    )
    x_positions = (-0.08, -0.04, 0.0, 0.04, 0.08)
    for finger, chain in enumerate(chains):
        for level, point_index in enumerate(chain, start=1):
            points[point_index] = (
                x_positions[finger] + level * 0.006 * (finger - 2),
                level * (0.055 + finger * 0.003),
                level * 0.008,
            )
    return (points * scale + np.asarray(offset, dtype=np.float32)).reshape(-1)


def _raw_sequence(frames=6, *, left=True, right=True):
    values = np.zeros((frames, INPUT_FEATURE_COUNT), dtype=np.float32)
    # Pose ไม่จำเป็นต้องสมจริงทั้งหมด แต่ทำให้มีจุดอ้างอิงที่ไม่เป็นศูนย์
    pose = np.linspace(-0.3, 0.3, LEFT_HAND_FEATURE_SLICE.start, dtype=np.float32)
    values[:, : LEFT_HAND_FEATURE_SLICE.start] = pose
    if left:
        left_points = _hand_points(offset=(0.25, -0.12, 0.03))
        values[:, LEFT_HAND_FEATURE_SLICE] = left_points
    if right:
        right_points = _hand_points(offset=(-0.22, -0.1, -0.02), scale=0.9)
        values[:, RIGHT_HAND_FEATURE_SLICE] = right_points
    return values


class FeatureSchemaTests(unittest.TestCase):
    def test_schema_preserves_raw_prefix_and_has_stable_dimension(self):
        sequence = _raw_sequence(4)
        transformed = extract_temporal_features(sequence)

        self.assertEqual(transformed.shape, (4, OUTPUT_FEATURE_COUNT))
        self.assertEqual(OUTPUT_FEATURE_COUNT, 510)
        np.testing.assert_array_equal(transformed[:, BASE_OUTPUT_SLICE], sequence)
        self.assertEqual(len(feature_columns()), OUTPUT_FEATURE_COUNT)
        self.assertEqual(schema_metadata()["schema_version"], FEATURE_SCHEMA_VERSION)
        self.assertFalse(schema_metadata()["left_right_mirroring"])

    def test_local_hand_features_ignore_global_translation_and_scale(self):
        first = _raw_sequence(1, right=False)
        second = first.copy()
        hand = first[0, LEFT_HAND_FEATURE_SLICE].reshape(21, 3)
        second[0, LEFT_HAND_FEATURE_SLICE] = (
            hand * 1.8 + np.asarray((0.7, -0.4, 0.2), dtype=np.float32)
        ).reshape(-1)

        first_features = extract_temporal_features(first)
        second_features = extract_temporal_features(second)
        left_local = slice(LOCAL_HAND_OUTPUT_SLICE.start, LOCAL_HAND_OUTPUT_SLICE.start + 63)
        left_geometry = slice(
            HAND_GEOMETRY_OUTPUT_SLICE.start,
            HAND_GEOMETRY_OUTPUT_SLICE.start + 20,
        )
        np.testing.assert_allclose(
            first_features[:, left_local], second_features[:, left_local], atol=2e-5
        )
        np.testing.assert_allclose(
            # มุมที่เกือบ 180 องศาไวต่อการปัดเศษของ float32 เล็กน้อย
            first_features[:, left_geometry],
            second_features[:, left_geometry],
            atol=2e-4,
        )

    def test_missing_hand_mask_and_velocity_do_not_create_false_motion(self):
        sequence = _raw_sequence(3)
        sequence[1, LEFT_HAND_FEATURE_SLICE] = 0.0
        sequence[2, RIGHT_HAND_FEATURE_SLICE] += 0.02

        transformed = extract_temporal_features(sequence)
        np.testing.assert_array_equal(
            transformed[:, VISIBILITY_OUTPUT_SLICE],
            np.asarray(((1, 1), (0, 1), (1, 1)), dtype=np.float32),
        )
        left_local = slice(LOCAL_HAND_OUTPUT_SLICE.start, LOCAL_HAND_OUTPUT_SLICE.start + 63)
        np.testing.assert_array_equal(transformed[1, left_local], np.zeros(63))
        velocities = transformed[:, VELOCITY_OUTPUT_SLICE]
        np.testing.assert_array_equal(velocities[1:, LEFT_HAND_FEATURE_SLICE], np.zeros((2, 63)))
        self.assertGreater(np.linalg.norm(velocities[2, RIGHT_HAND_FEATURE_SLICE]), 0)

    def test_raw_validation_rejects_bad_shape_and_non_finite_value(self):
        with self.assertRaises(ValueError):
            validate_raw_sequence(np.zeros((30, INPUT_FEATURE_COUNT - 1)))
        invalid = _raw_sequence(2)
        invalid[0, 0] = np.nan
        with self.assertRaises(ValueError):
            validate_raw_sequence(invalid)


class SequencePreparationTests(unittest.TestCase):
    def test_interpolates_only_short_bounded_hand_gaps(self):
        sequence = _raw_sequence(7, right=False)
        before = sequence[0, LEFT_HAND_FEATURE_SLICE].copy()
        after = before + 0.3
        sequence[1:3, LEFT_HAND_FEATURE_SLICE] = 0.0
        sequence[3, LEFT_HAND_FEATURE_SLICE] = after
        sequence[4:, LEFT_HAND_FEATURE_SLICE] = 0.0  # trailing gap ต้องไม่ถูกเติม

        interpolated = interpolate_short_hand_gaps(sequence, max_gap=2)
        np.testing.assert_allclose(
            interpolated[1, LEFT_HAND_FEATURE_SLICE], before * (2 / 3) + after * (1 / 3)
        )
        np.testing.assert_allclose(
            interpolated[2, LEFT_HAND_FEATURE_SLICE], before * (1 / 3) + after * (2 / 3)
        )
        np.testing.assert_array_equal(
            interpolated[4:, LEFT_HAND_FEATURE_SLICE], np.zeros((3, 63))
        )

    def test_long_missing_gap_is_not_filled(self):
        sequence = _raw_sequence(6, right=False)
        sequence[1:5, LEFT_HAND_FEATURE_SLICE] = 0.0
        result = interpolate_short_hand_gaps(sequence, max_gap=2)
        np.testing.assert_array_equal(result[1:5, LEFT_HAND_FEATURE_SLICE], np.zeros((4, 63)))

    def test_resampling_is_deterministic_and_preserves_endpoints(self):
        sequence = _raw_sequence(3)
        sequence[1] += 0.1
        sequence[2] += 0.25
        first = resample_sequence(sequence, 9)
        second = resample_sequence(sequence, 9)

        self.assertEqual(first.shape, (9, INPUT_FEATURE_COUNT))
        np.testing.assert_array_equal(first, second)
        np.testing.assert_array_equal(first[0], sequence[0])
        np.testing.assert_array_equal(first[-1], sequence[-1])

    def test_motion_trim_removes_stationary_edges(self):
        sequence = _raw_sequence(12)
        # Pose wrist ซ้าย/ขวาอยู่ที่ pose point ลำดับ 11 และ 12
        sequence[4:, 11 * 3] += 0.3
        sequence[4:, 12 * 3] += 0.3
        trimmed = trim_motion_window(
            sequence, motion_threshold=0.05, padding=1, minimum_frames=4
        )

        self.assertLess(len(trimmed), len(sequence))
        np.testing.assert_array_equal(trimmed, sequence[2:6])

    def test_static_sequence_is_kept_instead_of_discarded(self):
        sequence = _raw_sequence(8)
        trimmed = trim_motion_window(sequence, motion_threshold=0.05)
        np.testing.assert_array_equal(trimmed, sequence)


class AugmentationTests(unittest.TestCase):
    def setUp(self):
        self.config = AugmentationConfig(
            rotation_degrees=6.0,
            translation_max=0.03,
            scale_min=0.96,
            scale_max=1.04,
            jitter_std=0.002,
            time_scale_min=0.94,
            time_scale_max=1.06,
            frame_drop_probability=0.2,
        )

    def test_augmentation_requires_explicit_training_flag(self):
        sequence = _raw_sequence(10)
        unchanged = augment_sequence(
            sequence, training=False, seed=42, config=self.config
        )
        np.testing.assert_array_equal(unchanged, sequence)

    def test_seed_is_reproducible_and_different_seeds_change_result(self):
        sequence = _raw_sequence(12)
        # ทำให้ time warp/frame drop สังเกตผลได้ ไม่ใช่ sequence คงที่ทุกเฟรม
        for frame in range(len(sequence)):
            sequence[frame, : LEFT_HAND_FEATURE_SLICE.start] += frame * frame * 0.001

        first = augment_sequence(sequence, training=True, seed=123, config=self.config)
        repeated = augment_sequence(sequence, training=True, seed=123, config=self.config)
        different = augment_sequence(sequence, training=True, seed=124, config=self.config)

        np.testing.assert_array_equal(first, repeated)
        self.assertFalse(np.array_equal(first, different))
        self.assertEqual(first.shape, sequence.shape)
        self.assertTrue(np.isfinite(first).all())

    def test_missing_left_hand_stays_left_and_is_never_mirrored(self):
        sequence = _raw_sequence(10, left=False, right=True)
        augmented = augment_sequence(sequence, training=True, seed=7, config=self.config)

        np.testing.assert_array_equal(
            augmented[:, LEFT_HAND_FEATURE_SLICE], np.zeros((10, 63))
        )
        self.assertTrue(np.all(hand_visibility(augmented)[:, 0] == 0))
        self.assertTrue(np.all(hand_visibility(augmented)[:, 1] == 1))


class PipelineApiTests(unittest.TestCase):
    def test_process_sequence_returns_fixed_length_features(self):
        sequence = _raw_sequence(7)
        options = FeaturePipelineConfig(target_length=11, max_missing_gap=1)
        transformed = process_sequence(sequence, config=options)
        self.assertEqual(transformed.shape, (11, OUTPUT_FEATURE_COUNT))

    def test_pipeline_training_transform_is_seeded(self):
        sequence = _raw_sequence(8)
        pipeline = TemporalFeaturePipeline(FeaturePipelineConfig(target_length=10))
        first = pipeline.transform(sequence, training=True, seed=99)
        second = pipeline.transform(sequence, training=True, seed=99)
        np.testing.assert_array_equal(first, second)
        self.assertEqual(pipeline.schema_version, FEATURE_SCHEMA_VERSION)
        self.assertEqual(pipeline.output_feature_count, OUTPUT_FEATURE_COUNT)


if __name__ == "__main__":
    unittest.main()
