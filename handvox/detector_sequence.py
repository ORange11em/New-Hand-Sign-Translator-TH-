"""Keep motion from before a sustained landmark loss out of the next gesture."""


def expire_missing_motion(frames, timestamps, *, now, release_seconds):
    """Call only on missing landmarks, using the recognizer's existing release timeout."""
    if timestamps and now - timestamps[-1] >= release_seconds:
        frames.clear()
        timestamps.clear()
        return True
    return False
