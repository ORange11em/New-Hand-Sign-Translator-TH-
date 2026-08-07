from pathlib import Path
import tempfile
import unittest

from handvox.history import HistoryStore


class HistoryStoreTests(unittest.TestCase):
    def test_add_limit_delete_and_clear(self):
        with tempfile.TemporaryDirectory() as directory:
            store = HistoryStore(Path(directory) / "history.json")
            first = store.add("ประโยคแรก", limit=2)
            store.add("ประโยคสอง", limit=2)
            store.add("ประโยคสาม", limit=2)
            entries = store.load()
            self.assertEqual([entry.text for entry in entries], ["ประโยคสาม", "ประโยคสอง"])
            self.assertFalse(store.delete(first.id))
            self.assertTrue(store.delete(entries[0].id))
            store.clear()
            self.assertEqual(store.load(), [])

    def test_empty_text_is_not_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            store = HistoryStore(Path(directory) / "history.json")
            self.assertIsNone(store.add("   "))
            self.assertEqual(store.load(), [])


if __name__ == "__main__":
    unittest.main()

