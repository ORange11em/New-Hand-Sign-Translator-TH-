"""จับเวลาค้างท่าเพื่อเพิ่มคำครั้งเดียว โดยทดสอบได้โดยไม่ต้องเปิดกล้อง."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class HoldCaptureResult:
    """ผลการจับเวลา: สัดส่วนความคืบหน้าและคำที่พร้อมปล่อยหนึ่งครั้ง."""

    progress: float = 0.0
    ready_label: str = ""


class GestureHoldTimer:
    """ปล่อยคำหนึ่งครั้งเมื่อค้างท่าที่ยืนยันแล้วครบเวลาที่กำหนด."""

    def __init__(self, hold_seconds=1.0):
        hold_seconds = float(hold_seconds)
        if not math.isfinite(hold_seconds) or hold_seconds <= 0:
            raise ValueError("hold_seconds must be a positive finite number")
        self.hold_seconds = hold_seconds
        self.reset()

    def reset(self):
        """ลืมท่าและเวลารอบก่อน เพื่อเริ่มรับท่าใหม่."""
        self._label = ""
        self._started_at = None
        self._emitted = False

    def update(self, label, armed, now):
        """อัปเดตสถานะเวลาและคืนคำเมื่อค้างครบ โดยไม่ปล่อยคำเดิมซ้ำ."""
        label = str(label or "").strip()
        now = float(now)
        if not math.isfinite(now):
            raise ValueError("now must be finite")
        if not armed or not label:
            self.reset()
            return HoldCaptureResult()

        if label != self._label:
            self._label = label
            self._started_at = now
            self._emitted = False
            return HoldCaptureResult()

        if self._emitted:
            return HoldCaptureResult(progress=1.0)

        elapsed = max(0.0, now - self._started_at)
        progress = min(elapsed / self.hold_seconds, 1.0)
        if progress >= 1.0:
            self._emitted = True
            return HoldCaptureResult(progress=1.0, ready_label=label)
        return HoldCaptureResult(progress=progress)
