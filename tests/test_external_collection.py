"""The additional recording plan must never change training or count old clips."""

from types import SimpleNamespace
import unittest

from handvox.external_collection import (
    ADDITIONAL_TEST_SESSIONS,
    external_session_choices,
    external_session_target,
    next_additional_session,
    session_progress,
)
from handvox.training_config import load_training_config, session_clip_target


def clip(gesture="น้ำ", signer="person_03", session="session_05", quality="accepted"):
    return SimpleNamespace(
        gesture_name=gesture, signer_id=signer, session_id=session, quality=quality
    )


class ExternalCollectionTests(unittest.TestCase):
    def test_new_test_sessions_do_not_change_training_plan(self):
        config = load_training_config()
        original = config.collection
        choices = external_session_choices(config)
        self.assertEqual(choices[-3:], ADDITIONAL_TEST_SESSIONS)
        self.assertEqual([external_session_target(config, s) for s in ADDITIONAL_TEST_SESSIONS], [4, 4, 4])
        self.assertEqual(config.collection, original)
        self.assertEqual(config.collection.signers, ("person_01", "person_02"))
        self.assertEqual(len(config.collection.sessions), 4)
        self.assertEqual([session_clip_target(config, s) for s in config.collection.sessions], [4] * 4)

    def test_old_other_person_and_rejected_clips_do_not_fill_new_session(self):
        records = [
            clip(), clip(quality="pending"), clip(quality="rejected"),
            clip(session="session_01"), clip(signer="person_01"), clip(gesture="outside"),
        ]
        progress = session_progress(records, "person_03", "session_05", ("น้ำ", "กิน"), 4)
        self.assertEqual(progress["captured"], 2)
        self.assertEqual(progress["accepted"], 1)
        self.assertEqual(progress["remaining"], 6)
        self.assertEqual(progress["next_gesture"], "น้ำ")

    def test_extra_clips_of_one_class_cannot_hide_a_missing_class(self):
        records = [clip() for _ in range(8)]
        progress = session_progress(records, "person_03", "session_05", ("น้ำ", "กิน"), 4)
        self.assertEqual(progress["captured"], 4)
        self.assertEqual(progress["remaining"], 4)
        self.assertEqual(progress["next_gesture"], "กิน")

    def test_reopen_resumes_first_incomplete_additional_session(self):
        records = [clip() for _ in range(4)]
        self.assertEqual(next_additional_session(records, "person_03", ("น้ำ",)), "session_06")
        records.extend(clip(session="session_06", quality="pending") for _ in range(4))
        self.assertEqual(next_additional_session(records, "person_03", ("น้ำ",)), "session_07")

    def test_nineteen_classes_need_228_new_clips(self):
        classes = tuple(f"class_{i}" for i in range(19))
        plan = [session_progress([], "person_03", s, classes, 4) for s in ADDITIONAL_TEST_SESSIONS]
        self.assertEqual([item["remaining"] for item in plan], [76, 76, 76])
        self.assertEqual(sum(item["total"] for item in plan), 228)


if __name__ == "__main__":
    unittest.main()
