"""ทดสอบการตรวจค่า บันทึก โหลด และ fallback ของ settings."""

import json
from pathlib import Path
import tempfile
import unittest

from handvox.errors import ConfigurationError
from handvox.settings import AppSettings, SettingsStore


class SettingsStoreTests(unittest.TestCase):
    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = SettingsStore(path)
            expected = AppSettings(camera_index=2, min_confidence=0.72, auto_tts=False)
            store.save(expected)
            self.assertEqual(store.load(), expected)

    def test_invalid_settings_fall_back_without_overwriting_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({"min_confidence": 5}), encoding="utf-8")
            store = SettingsStore(path)
            settings = store.load_or_default()
            self.assertEqual(settings, AppSettings())
            self.assertIsNotNone(store.last_error)
            self.assertIn("5", path.read_text(encoding="utf-8"))

    def test_validation_rejects_bad_camera_index(self):
        with self.assertRaises(ConfigurationError):
            AppSettings(camera_index=-1).validate()

    def test_auto_add_words_defaults_to_enabled(self):
        settings = AppSettings.from_dict({})
        self.assertTrue(settings.auto_add_words)
        self.assertTrue(settings.prefer_gpu)

    def test_validation_rejects_non_boolean_auto_add_words(self):
        with self.assertRaises(ConfigurationError):
            AppSettings(auto_add_words="yes").validate()

    def test_validation_rejects_non_boolean_gpu_preference(self):
        with self.assertRaises(ConfigurationError):
            AppSettings(prefer_gpu="cuda").validate()


if __name__ == "__main__":
    unittest.main()
