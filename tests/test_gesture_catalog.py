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

    def test_plan_view_keeps_active_and_planned_words_in_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active_path = root / "active.json"
            planned_path = root / "planned.json"
            active_path.write_text(
                json.dumps(
                    [
                        {
                            "name": "สวัสดี",
                            "description": "ท่าทักทาย",
                            "color": [1, 2, 3],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            planned_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "gestures": [
                            {
                                "id": "water",
                                "name": "น้ำ",
                                "category": "พื้นฐาน",
                                "priority": 1,
                                "status": "verified",
                            },
                            {
                                "id": "medicine",
                                "name": "ยา",
                                "category": "ทั่วไป",
                                "priority": 5,
                                "status": "planned",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            catalog = GestureCatalog(active_path, planned_path)
            rows = catalog.load_plan_view(("สวัสดี", "น้ำ", "กิน"))
            self.assertEqual([row.name for row in rows], ["สวัสดี", "น้ำ", "กิน", "ยา"])
            self.assertEqual(
                [row.row_type for row in rows],
                ["active", "planned", "missing", "planned"],
            )
            self.assertEqual(rows[0].status, "ใช้งานได้แล้ว")
            self.assertEqual(rows[1].status, "ยืนยันแล้ว")
            self.assertEqual(
                rows[3].status,
                "วางแผน",
            )

    def test_plan_view_keeps_every_active_word_after_continuous_additions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active_path = root / "active.json"
            planned_path = root / "planned.json"
            active_path.write_text(
                json.dumps(
                    [
                        {"name": "สวัสดี", "description": "ทักทาย", "color": [1, 2, 3]},
                        {"name": "นอน", "description": "นอน", "color": [3, 2, 1]},
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            catalog = GestureCatalog(active_path, planned_path)

            rows = catalog.load_plan_view(("สวัสดี", "น้ำ"))

            self.assertEqual([row.name for row in rows], ["สวัสดี", "น้ำ", "นอน"])
            self.assertEqual(rows[2].row_type, "active")
            self.assertEqual(rows[2].category, "ใช้งานในโมเดล")


if __name__ == "__main__":
    unittest.main()
