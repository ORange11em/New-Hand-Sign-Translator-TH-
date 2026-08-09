"""ทดสอบการเพิ่ม ลบ ล้าง แทนข้อความ และควบคุมคำซ้ำ."""

import unittest

from handvox.sentence import SentenceBuilder


class SentenceBuilderTests(unittest.TestCase):
    def test_add_remove_clear(self):
        builder = SentenceBuilder()
        self.assertTrue(builder.add("สวัสดี"))
        self.assertTrue(builder.add("ขอบคุณ"))
        self.assertEqual(builder.text, "สวัสดี ขอบคุณ")
        self.assertEqual(builder.remove_last(), "ขอบคุณ")
        builder.clear()
        self.assertEqual(builder.text, "")

    def test_adjacent_duplicates_are_optional(self):
        builder = SentenceBuilder(prevent_duplicates=True)
        self.assertTrue(builder.add("ใช่"))
        self.assertFalse(builder.add("ใช่"))
        builder.prevent_duplicates = False
        self.assertTrue(builder.add("ใช่"))

    def test_replace_from_text(self):
        builder = SentenceBuilder()
        builder.replace_from_text("ฉัน ต้องการ น้ำ")
        self.assertEqual(builder.words, ("ฉัน", "ต้องการ", "น้ำ"))


if __name__ == "__main__":
    unittest.main()
