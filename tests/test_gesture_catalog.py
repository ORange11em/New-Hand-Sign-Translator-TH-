"""ทดสอบการเพิ่ม ลบ ตรวจ URL และป้องกันชื่อคำศัพท์ซ้ำ."""

import json
from pathlib import Path
import tempfile
import unittest

from handvox.errors import DataFileError
from handvox.gesture_catalog import GestureCatalog, PlannedGesture


class GestureCatalogTests(unittest.TestCase):
    def _catalog(self, directory):
        root = Path(directory)
        active = root / "active.json"
        planned = root / "planned.json"
        active.write_text(
            json.dumps(
                [{"name": "สวัสดี", "description": "ทักทาย", "color": [0, 1, 2]}],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return GestureCatalog(active, planned)

    def test_upsert_and_delete_planned_gesture(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = self._catalog(directory)
            gesture = PlannedGesture("water", "น้ำ", "พื้นฐาน", priority=1)
            catalog.upsert_planned(gesture)
            self.assertEqual(catalog.load_planned()[0].name, "น้ำ")
            self.assertTrue(catalog.delete_planned("water"))
            self.assertEqual(catalog.load_planned(), [])

    def test_planned_name_cannot_overlap_active_model(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = self._catalog(directory)
            with self.assertRaises(DataFileError):
                catalog.upsert_planned(
                    PlannedGesture("hello_again", "สวัสดี", "ทักทาย")
                )

    def test_reference_url_must_be_http(self):
        with self.assertRaises(DataFileError):
            PlannedGesture("water", "น้ำ", "พื้นฐาน", reference_url="example.com").validate()


if __name__ == "__main__":
    unittest.main()
