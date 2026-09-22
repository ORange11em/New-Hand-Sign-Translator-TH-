"""Session targets for additional test clips, independent of the training plan."""

from collections import Counter

from handvox.errors import ConfigurationError
from handvox.training_config import session_clip_target


ADDITIONAL_TEST_SESSIONS = ("session_05", "session_06", "session_07")
ADDITIONAL_CLIPS_PER_CLASS = 4


def external_session_choices(config):
    return tuple(dict.fromkeys((*config.collection.sessions, *ADDITIONAL_TEST_SESSIONS)))


def external_session_target(config, session):
    if session in ADDITIONAL_TEST_SESSIONS:
        return ADDITIONAL_CLIPS_PER_CLASS
    if session in config.collection.sessions:
        return session_clip_target(config, session)
    raise ConfigurationError(f"ไม่พบ session ในแผนเก็บชุดทดสอบ: {session}")


def session_progress(records, signer, session, classes, target):
    """Pending clips fill recording slots; only accepted clips count as reviewed."""
    counts = Counter()
    accepted = Counter()
    for record in records:
        if (
            record.signer_id == signer
            and record.session_id == session
            and record.gesture_name in classes
            and record.quality != "rejected"
        ):
            counts[record.gesture_name] += 1
            if record.quality == "accepted":
                accepted[record.gesture_name] += 1
    total = len(classes) * target
    captured = sum(min(counts[name], target) for name in classes)
    return {
        "counts": counts,
        "captured": captured,
        "accepted": sum(min(accepted[name], target) for name in classes),
        "total": total,
        "remaining": total - captured,
        "next_gesture": next((name for name in classes if counts[name] < target), None),
    }


def next_additional_session(records, signer, classes):
    for session in ADDITIONAL_TEST_SESSIONS:
        if session_progress(records, signer, session, classes, ADDITIONAL_CLIPS_PER_CLASS)["remaining"]:
            return session
    return ADDITIONAL_TEST_SESSIONS[-1]
