"""ทดสอบการตรวจ metadata ความปลอดภัยของ path และ inventory Dataset V2."""

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from handvox.dataset_v2 import ClipMetadata, DatasetV2Store
from handvox.errors import DataFileError


def metadata(clip_id="clip-001"):
    return ClipMetadata(
        clip_id=clip_id,
        gesture_name="น้ำ",
        signer_id="person-01",
        session_id="session-01",
        recorded_at=datetime.now(timezone.utc).isoformat(),
        camera_index=0,
        sequence_file="clips/clip-001.npy",
    )


class DatasetV2StoreTests(unittest.TestCase):
    def test_initialize_and_append(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DatasetV2Store(Path(directory) / "dataset")
            store.append(metadata())
            summary = store.summary()
            self.assertEqual(summary["clips"], 1)
            self.assertEqual(summary["gestures"], {"น้ำ": 1})
            self.assertEqual(summary["signers"], 1)
            self.assertTrue(store.clips_dir.is_dir())

    def test_duplicate_clip_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DatasetV2Store(Path(directory) / "dataset")
            store.append(metadata())
            with self.assertRaises(DataFileError):
                store.append(metadata())

    def test_sequence_path_must_stay_inside_dataset(self):
        item = metadata()
        item.sequence_file = "../outside.npy"
        with self.assertRaises(DataFileError):
            item.validate()

    def test_quality_and_inventory_are_auditable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DatasetV2Store(Path(directory) / "dataset")
            first = metadata("clip-001")
            second = metadata("clip-002")
            second.session_id = "session-02"
            store.append(first)
            store.append(second)
            self.assertEqual(store.set_quality([first.clip_id, second.clip_id], "accepted"), 2)
            inventory = store.inventory(("น้ำ",), ("person-01",))
            self.assertEqual(inventory[0]["accepted"], 2)
            self.assertEqual(inventory[0]["sessions"], 2)

    def test_resolved_path_cannot_escape_dataset(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DatasetV2Store(Path(directory) / "dataset")
            with self.assertRaises(DataFileError):
                store.resolve_data_path("../outside.npy")

    def test_superseded_clip_cannot_be_restored_or_replaced_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DatasetV2Store(Path(directory) / "dataset")
            old = metadata("clip-old")
            replacement = metadata("clip-new")
            store.append(old)
            store.append(replacement)
            store.mark_superseded(old.clip_id, replacement.clip_id)

            records = {item.clip_id: item for item in store.records()}
            self.assertEqual(records[old.clip_id].quality, "rejected")
            self.assertEqual(records[replacement.clip_id].capture_mode, "retake")
            self.assertEqual(
                records[replacement.clip_id].supersedes_clip_id, old.clip_id
            )
            with self.assertRaisesRegex(DataFileError, "ถูกถ่ายแทนแล้ว"):
                store.set_quality([old.clip_id], "accepted")

            another = metadata("clip-another")
            store.append(another)
            with self.assertRaisesRegex(DataFileError, "ถูกแทนที่"):
                store.mark_superseded(old.clip_id, another.clip_id)

    def test_retake_must_keep_gesture_signer_and_session(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DatasetV2Store(Path(directory) / "dataset")
            old = metadata("clip-old")
            wrong = metadata("clip-wrong")
            wrong.session_id = "session-02"
            store.append(old)
            store.append(wrong)
            with self.assertRaisesRegex(DataFileError, "session เดียว"):
                store.mark_superseded(old.clip_id, wrong.clip_id)


if __name__ == "__main__":
    unittest.main()
