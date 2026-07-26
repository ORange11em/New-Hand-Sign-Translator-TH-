"""Shared upper-body and two-hand features for HandVox."""

import math


# Head, shoulders, elbows, wrists, finger bases, and hips: upper-body movement.
POSE_IDS = (0, 2, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 23, 24)
HAND_POINTS = 21
FEATURE_COUNT = (len(POSE_IDS) + HAND_POINTS * 2) * 3


def feature_columns():
    columns = [f"pose_{index}_{axis}" for index in POSE_IDS for axis in "xyz"]
    columns += [f"left_hand_{index}_{axis}" for index in range(HAND_POINTS) for axis in "xyz"]
    columns += [f"right_hand_{index}_{axis}" for index in range(HAND_POINTS) for axis in "xyz"]
    return columns


def _normalizer(pose_landmarks):
    left_shoulder = pose_landmarks.landmark[11]
    right_shoulder = pose_landmarks.landmark[12]
    center = (
        (left_shoulder.x + right_shoulder.x) / 2,
        (left_shoulder.y + right_shoulder.y) / 2,
        (left_shoulder.z + right_shoulder.z) / 2,
    )
    scale = math.sqrt(
        (left_shoulder.x - right_shoulder.x) ** 2
        + (left_shoulder.y - right_shoulder.y) ** 2
        + (left_shoulder.z - right_shoulder.z) ** 2
    )
    return center, max(scale, 1e-6)


def _encode(points, center, scale, expected_count):
    if points is None:
        return [0.0] * (expected_count * 3)
    values = []
    for point in points:
        values.extend(
            ((point.x - center[0]) / scale,
             (point.y - center[1]) / scale,
             (point.z - center[2]) / scale)
        )
    return values


def extract_features(results):
    """Return 171 normalized features, or None until pose and a hand are visible."""
    pose = results.pose_landmarks
    left_hand = results.left_hand_landmarks
    right_hand = results.right_hand_landmarks
    if pose is None or (left_hand is None and right_hand is None):
        return None

    center, scale = _normalizer(pose)
    pose_points = [pose.landmark[index] for index in POSE_IDS]
    return (
        _encode(pose_points, center, scale, len(POSE_IDS))
        + _encode(left_hand.landmark if left_hand else None, center, scale, HAND_POINTS)
        + _encode(right_hand.landmark if right_hand else None, center, scale, HAND_POINTS)
    )


def upper_body_bbox(results, width, height):
    """Bounding box around the detected upper body and hands for display."""
    points = []
    if results.pose_landmarks:
        points.extend(results.pose_landmarks.landmark[index] for index in POSE_IDS)
    if results.left_hand_landmarks:
        points.extend(results.left_hand_landmarks.landmark)
    if results.right_hand_landmarks:
        points.extend(results.right_hand_landmarks.landmark)
    if not points:
        return None

    xs = [point.x for point in points]
    ys = [point.y for point in points]
    return (
        int(max(0, min(xs) - 0.04) * width),
        int(max(0, min(ys) - 0.04) * height),
        int(min(1, max(xs) + 0.04) * width),
        int(min(1, max(ys) + 0.04) * height),
    )
