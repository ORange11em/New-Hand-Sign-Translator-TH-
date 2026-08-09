"""เครื่องสถานะสำหรับยืนยันผลทำนาย ลดผลสั่น และกันคำเดิมยิงซ้ำ."""

from dataclasses import dataclass
from enum import Enum
import math


class DetectionPhase(str, Enum):
    """สถานะของผลตั้งแต่ยังไม่พบ จนยืนยันและรอให้ผู้ใช้ปล่อยท่า."""

    IDLE = "idle"
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    COOLDOWN = "cooldown"


@dataclass(frozen=True)
class DetectionResult:
    """ค่าที่หน้ากล้องใช้แสดงผล พร้อมสัญญาณว่าผู้ใช้ปล่อยท่าแล้ว."""

    phase: DetectionPhase
    label: str = ""
    confidence: float = 0.0
    released: bool = False


class GestureStateMachine:
    """ยืนยันคำจากผลซ้ำหลายเฟรมและปฏิเสธผลที่ไม่มั่นใจ.

    คำที่ยืนยันแล้วจะถูกซ่อนทันทีเมื่อเฟรมใหม่ไม่น่าเชื่อถือ และรีเซ็ตภายใน
    เมื่อความไม่แน่นอนนานเกิน ``release_seconds`` หลังปล่อยคำแล้วสถานะ cooldown
    จะกันคำเดิมซ้ำจนกว่าผู้ใช้ปล่อยมือหรือเปลี่ยนเป็นอีกท่า
    """

    def __init__(self, min_confidence=0.65, confirm_frames=4, release_seconds=0.35):
        if not 0.0 < min_confidence <= 1.0:
            raise ValueError("min_confidence must be in (0, 1]")
        if confirm_frames < 1:
            raise ValueError("confirm_frames must be at least 1")
        if release_seconds < 0:
            raise ValueError("release_seconds cannot be negative")

        self.min_confidence = float(min_confidence)
        self.confirm_frames = int(confirm_frames)
        self.release_seconds = float(release_seconds)
        self.reset()

    def reset(self):
        """กลับสู่ IDLE และล้างผู้สมัครกับตัวจับเวลาปล่อยท่า."""
        self.phase = DetectionPhase.IDLE
        self.label = ""
        self.confidence = 0.0
        self._candidate_count = 0
        self._candidate_confidence_total = 0.0
        self._invalid_since = None

    @property
    def speech_armed(self):
        """บอกว่ามีคำยืนยันใหม่ที่ยังไม่ถูกเพิ่ม/อ่านออกไป."""
        return self.phase is DetectionPhase.CONFIRMED and bool(self.label)

    def mark_emitted(self, label):
        """ล็อกคำที่ปล่อยแล้วใน cooldown เพื่อไม่ให้เพิ่มซ้ำทุกวินาที."""
        if self.phase is DetectionPhase.CONFIRMED and label == self.label:
            self.phase = DetectionPhase.COOLDOWN
            return True
        return False

    def update(self, label, confidence, landmarks_visible, now):
        """รับผลหนึ่งเฟรมแล้วคืนสถานะที่ปลอดภัยสำหรับแสดงและสร้างประโยค."""
        confidence = float(confidence or 0.0)
        valid = (
            landmarks_visible
            and bool(label)
            and math.isfinite(confidence)
            and confidence >= self.min_confidence
        )

        if not valid:
            return self._handle_rejected(now)

        self._invalid_since = None
        if self.phase is DetectionPhase.IDLE:
            self._start_candidate(label, confidence)
        elif self.phase is DetectionPhase.CANDIDATE:
            if label == self.label:
                self._candidate_count += 1
                self._candidate_confidence_total += confidence
            else:
                self._start_candidate(label, confidence)
        elif self.phase in (DetectionPhase.CONFIRMED, DetectionPhase.COOLDOWN):
            if label != self.label:
                self._start_candidate(label, confidence)
            else:
                self.confidence = self.confidence * 0.65 + confidence * 0.35

        if (
            self.phase is DetectionPhase.CANDIDATE
            and self._candidate_count >= self.confirm_frames
        ):
            self.phase = DetectionPhase.CONFIRMED
            self.confidence = (
                self._candidate_confidence_total / self._candidate_count
            )

        if self.phase in (DetectionPhase.CONFIRMED, DetectionPhase.COOLDOWN):
            return DetectionResult(self.phase, self.label, self.confidence)
        return DetectionResult(self.phase)

    def _start_candidate(self, label, confidence):
        """เริ่มนับผลของคำผู้สมัครใหม่ตั้งแต่หนึ่งเฟรม."""
        self.phase = DetectionPhase.CANDIDATE
        self.label = label
        self.confidence = confidence
        self._candidate_count = 1
        self._candidate_confidence_total = confidence

    def _handle_rejected(self, now):
        """ซ่อนผลเก่า และรีเซ็ตเมื่อไม่เห็นผลที่ใช้ได้นานพอ."""
        if self.phase is DetectionPhase.IDLE:
            return DetectionResult(self.phase)
        if self._invalid_since is None:
            self._invalid_since = now
        released = now - self._invalid_since >= self.release_seconds
        if released:
            self.reset()
            return DetectionResult(DetectionPhase.IDLE, released=True)

        # ห้ามคืน label เก่าในเฟรมที่ถูกปฏิเสธ เพื่อไม่ให้คำค้างถูกแสดงหรือพูดซ้ำ
        return DetectionResult(self.phase)
