"""เปิดสคริปต์ย่อยของ HandVox เป็น process แยกจากหน้าต่าง GUI หลัก."""

import subprocess
import sys

from handvox.errors import LaunchError
from handvox.paths import ROOT


SCRIPT_ALLOWLIST = {
    "detect": "run_detector.py",
    "collect": "collect_data.py",
    "train": "train_model.py",
    "add": "add_gesture.py",
    "remove": "remove_gesture.py",
    "collect_v2": "collect_dataset_v2.py",
    "train_v2": "training_cli.py",
}


class ScriptLauncher:
    """จำกัดสคริปต์ที่เปิดได้และป้องกันการเปิดงานเดิมซ้ำพร้อมกัน."""

    def __init__(self):
        self.processes = {}

    def launch(self, action, arguments=()):
        """เปิด action ที่อยู่ใน allowlist ด้วย Python environment ปัจจุบัน."""
        if action not in SCRIPT_ALLOWLIST:
            raise LaunchError(f"ไม่รู้จักคำสั่ง: {action}")
        current = self.processes.get(action)
        if current is not None and current.poll() is None:
            raise LaunchError("หน้าต่างนี้กำลังทำงานอยู่แล้ว")
        script = (ROOT / SCRIPT_ALLOWLIST[action]).resolve()
        if script.parent != ROOT or not script.exists():
            raise LaunchError(f"ไม่พบ {script.name}")
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        try:
            process = subprocess.Popen(
                [sys.executable, str(script), *map(str, arguments)],
                cwd=ROOT,
                creationflags=flags,
            )
        except OSError as error:
            raise LaunchError(f"เปิด {script.name} ไม่ได้: {error}") from error
        self.processes[action] = process
        return process

    def is_running(self, action):
        """ตรวจว่า process ของ action ยังไม่จบหรือไม่."""
        process = self.processes.get(action)
        return process is not None and process.poll() is None
