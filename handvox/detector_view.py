"""Compact camera presentation, isolated from capture and recognition."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import unicodedata

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from gesture_state import DetectionPhase


@dataclass(frozen=True)
class DetectionPresentation:
    label: str = "รอท่ามือ"
    status: str = "ให้กล้องเห็นมือและช่วงตัวครบ"
    tone: str = "muted"
    progress: float = 0.0
    progress_label: str = ""


def detection_presentation(decision, *, visible, frame_count, sequence_length,
                           neutral=False, unknown=False, policy_rejected=False,
                           hold_progress=0.0, hold_action="เพิ่มคำ"):
    if not visible:
        return DetectionPresentation()
    if decision.label:
        return DetectionPresentation(
            decision.label, "ยืนยันคำแล้ว", "confirmed", hold_progress,
            f"ค้างท่าเพื่อ{hold_action}" if hold_progress > 0 else "พร้อมเพิ่มคำ",
        )
    if decision.phase is DetectionPhase.COOLDOWN:
        return DetectionPresentation(
            "พักมือก่อน", "พร้อมรับคำถัดไปเมื่อปล่อยท่า", "muted",
            decision.neutral_progress, "กำลังรอท่าพัก",
        )
    if decision.phase is DetectionPhase.CANDIDATE and decision.candidate_label:
        return DetectionPresentation(
            decision.candidate_label, "กำลังยืนยัน · ยังไม่เพิ่มลงประโยค", "pending",
            decision.confirm_progress, "ยืนยันคำ",
        )
    if frame_count < sequence_length:
        return DetectionPresentation(
            "รอข้อมูล", f"กำลังอ่านการเคลื่อนไหว {frame_count}/{sequence_length} เฟรม",
            "muted", frame_count / max(1, sequence_length), "เตรียมตรวจจับ",
        )
    if neutral:
        return DetectionPresentation("พร้อมรับคำ", "ตรวจพบท่าพัก", "muted")
    if policy_rejected or decision.reason in {"low_margin", "low_confidence"}:
        return DetectionPresentation("ยังไม่แน่ใจ", "ลองทำท่าให้ชัดขึ้น", "pending")
    if unknown or decision.reason == "unknown":
        return DetectionPresentation("ยังไม่รู้จักท่า", "ยังไม่เพิ่มคำลงประโยค", "pending")
    return DetectionPresentation("กำลังตรวจจับ", "แสดงท่าให้เห็นต่อเนื่อง", "muted")


@dataclass(frozen=True)
class DetectorViewState:
    detection: DetectionPresentation = DetectionPresentation()
    sentence: str = ""
    word_count: int = 0
    confidence: float = 0.0
    fps: float = 0.0
    device: str = "CPU"
    experimental: bool = False
    auto_add: bool = False
    speech_status: str = "เสียงปิดอยู่"
    features_visible: bool = False
    can_add: bool = False
    can_speak: bool = False
    details: bool = False
    timing: tuple[str, ...] = ()
    feedback: str = ""


class DetectorView:
    size = (1080, 680)
    camera_bounds = (32, 158, 712, 540)
    background = "#0b1220"
    panel = "#141f31"
    border = "#29364a"
    foreground = "#edf3fb"
    muted = "#a7b5c9"
    tones = {"muted": "#a7b5c9", "pending": "#f4c777", "confirmed": "#71dbb4"}
    button_bounds = {
        "add": (760, 474, 1040, 516),
        "remove": (760, 526, 896, 566),
        "speak": (906, 526, 1040, 566),
        "save": (760, 576, 896, 616),
        "clear": (906, 576, 1040, 616),
        "details": (568, 620, 708, 648),
        "close": (962, 22, 1060, 56),
    }

    def __init__(self, font_scale=1.0):
        self.font_scale = min(1.75, max(0.75, float(font_scale)))
        self.font_path = next((path for path in (
            "C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/THSarabunNew.ttf",
            "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ) if Path(path).exists()), None)
        self._cached_state = None
        self._cached_chrome = None

    @lru_cache(maxsize=48)
    def font(self, size):
        return ImageFont.truetype(self.font_path, size) if self.font_path else ImageFont.load_default()

    @lru_cache(maxsize=384)
    def text_mask(self, text, size, width, height):
        draw = ImageDraw.Draw(Image.new("L", (1, 1)))
        selected_size = max(10, round(size * self.font_scale))
        while selected_size > 10:
            font = self.font(selected_size)
            bounds = draw.textbbox((0, 0), text, font=font)
            if bounds[2] - bounds[0] <= width and bounds[3] - bounds[1] <= height:
                break
            selected_size -= 1
        font = self.font(selected_size)
        display = text
        while display and draw.textbbox((0, 0), display, font=font)[2] > width:
            display = display[:-2] + "…" if len(display) > 2 else ""
        bounds = draw.textbbox((0, 0), display, font=font)
        mask = Image.new("L", (max(1, bounds[2] - bounds[0]), max(1, bounds[3] - bounds[1])))
        ImageDraw.Draw(mask).text((-bounds[0], -bounds[1]), display, font=font, fill=255)
        return mask

    def text(self, draw, text, position, *, size=16, color=None, width=280, height=26):
        draw.bitmap(position, self.text_mask(text, size, width, height), fill=color or self.foreground)

    @lru_cache(maxsize=64)
    def sentence_lines(self, sentence, width=252):
        font = self.font(round(18 * min(self.font_scale, 1.25)))
        lines = [""]
        clusters = []
        for character in sentence:
            if clusters and unicodedata.category(character).startswith("M"):
                clusters[-1] += character
            else:
                clusters.append(character)
        for cluster in clusters:
            if font.getlength(lines[-1] + cluster) > width:
                lines.append("")
            lines[-1] += cluster
        if len(lines) > 2:
            return ("…" + lines[-2][1:], lines[-1])
        return tuple(lines)

    @staticmethod
    def enabled_actions(state):
        actions = {"details", "close"}
        if state.can_add:
            actions.add("add")
        if state.word_count:
            actions.update(("remove", "save", "clear"))
            if state.can_speak:
                actions.add("speak")
        return actions

    def action_regions(self, state):
        return {action: bounds for action, bounds in self.button_bounds.items()
                if action in self.enabled_actions(state)}

    def action_at(self, state, horizontal, vertical):
        for action, bounds in self.action_regions(state).items():
            if bounds[0] <= horizontal < bounds[2] and bounds[1] <= vertical < bounds[3]:
                return action
        return None

    def chrome(self, state):
        canvas = Image.new("RGB", self.size, self.background)
        draw = ImageDraw.Draw(canvas)
        self.text(draw, "HandVox", (20, 24), size=26, width=142, height=32)
        self.text(draw, "แปลภาษามือ", (175, 32), size=16, width=180, color=self.muted)
        speed = f"ประมวลผล {state.fps:.1f} FPS" if state.fps > 0 else "กำลังวัด FPS"
        self.text(draw, speed, (740, 32), size=15, width=208,
                  color=self.tones["pending"] if 0 < state.fps < 10 else self.muted)
        if state.experimental:
            draw.rounded_rectangle((20, 76, 1060, 108), radius=7, fill="#342b1c")
            self.text(draw, "โมเดลทดลอง · ยังไม่ผ่านเกณฑ์ โปรดตรวจคำก่อนใช้", (32, 83),
                      size=15, color="#f4c777", width=1016, height=22)
        else:
            self.text(draw, "ทำท่าให้ชัด แล้วตรวจคำก่อนเพิ่มลงประโยค", (20, 83),
                      color=self.muted, width=800)
        for bounds in ((20, 120, 724, 660), (740, 120, 1060, 660)):
            draw.rounded_rectangle(bounds, radius=12, fill=self.panel, outline=self.border)
        self.text(draw, "ภาพกล้อง", (36, 132), size=14, width=100, color=self.muted)
        self.text(draw, "ให้เห็นมือและช่วงตัวครบ", (495, 132), size=13, width=215, color=self.muted)
        draw.rectangle(self.camera_bounds, fill="#070c14")
        guidance = "ตรวจพบมือและช่วงตัว" if state.features_visible else "ยังไม่เห็นมือพร้อมช่วงตัว"
        self.text(draw, guidance, (36, 553), size=17, width=440)
        self.text(draw, "จัดแสงด้านหน้า และให้มืออยู่ในภาพตลอดท่า", (36, 582),
                  size=14, width=658, color=self.muted)
        if state.details:
            for index, line in enumerate(state.timing[:2]):
                self.text(draw, line, (36, 606 + index * 23), size=13,
                          width=670 if index == 0 else 514, height=20, color=self.muted)
        else:
            self.text(draw, state.device + " · " + state.speech_status, (36, 623),
                      size=13, width=514, color=self.muted)
        self.text(draw, "คำที่ตรวจพบ", (760, 140), size=14, color=self.muted)
        tone = self.tones[state.detection.tone]
        self.text(draw, state.detection.label, (760, 174), size=34, height=42, color=tone)
        self.text(draw, state.detection.status, (760, 228), size=14, color=self.muted)
        confidence = min(1.0, max(0.0, state.confidence))
        draw.rounded_rectangle((760, 260, 1040, 265), radius=2, fill=self.border)
        if confidence > 0:
            draw.rounded_rectangle((760, 260, 760 + max(2, round(280 * confidence)), 265), radius=2, fill=tone)
        self.text(draw, f"ความมั่นใจของโมเดล {confidence:.0%}" if confidence else "ยังไม่มีผลทำนาย",
                  (760, 275), size=13, color=self.muted)
        progress = min(1.0, max(0.0, state.detection.progress))
        self.text(draw, state.detection.progress_label, (760, 302), size=13, color=tone)
        if progress > 0:
            draw.rectangle((760, 325, 760 + max(1, round(280 * progress)), 328), fill=tone)
        draw.line((760, 346, 1040, 346), fill=self.border)
        mode = "ประโยค · เพิ่มอัตโนมัติ" if state.auto_add else "ประโยค · เพิ่มด้วยปุ่ม"
        self.text(draw, mode, (760, 358), size=14, width=229, color=self.muted)
        self.text(draw, f"{state.word_count} คำ", (997, 358), size=12, width=44, color=self.muted)
        draw.rounded_rectangle((760, 388, 1040, 461), radius=8, fill=self.background)
        lines = self.sentence_lines(state.sentence or "ยังไม่มีคำในประโยค")
        for index, line in enumerate(lines):
            self.text(draw, line, (774, 401 + index * 27), size=18, width=252, height=24,
                      color=self.foreground if state.sentence else self.muted)
        labels = {"add": "เพิ่มคำ   Space", "remove": "ลบคำล่าสุด", "speak": "อ่านประโยค",
                  "save": "บันทึก", "clear": "ล้างประโยค",
                  "details": "ซ่อนรายละเอียด" if state.details else "รายละเอียด · D",
                  "close": "ปิด · Esc"}
        enabled = self.enabled_actions(state)
        for action, bounds in self.button_bounds.items():
            active = action in enabled
            fill = "#2764da" if action == "add" and active else "#202e44" if active else "#182337"
            foreground = "#f2f6fc" if active else "#738299"
            if action == "clear" and active:
                foreground = "#f2a3ab"
            draw.rounded_rectangle(bounds, radius=7, fill=fill)
            self.text(draw, labels[action], (bounds[0] + 12, bounds[1] + 9),
                      size=16 if action == "add" else 14, width=bounds[2] - bounds[0] - 24,
                      height=bounds[3] - bounds[1] - 16, color=foreground)
        self.text(draw, state.feedback or "พักมือก่อนทำคำเดิมซ้ำ", (760, 632),
                  size=13, color=self.muted, height=20)
        return canvas

    def render(self, frame, state, bbox=None):
        if state != self._cached_state:
            self._cached_chrome = self.chrome(state)
            self._cached_state = state
        canvas = self._cached_chrome.copy()
        left, top, right, bottom = self.camera_bounds
        height, width = frame.shape[:2]
        ratio = min((right - left) / width, (bottom - top) / height)
        preview_size = (max(1, round(width * ratio)), max(1, round(height * ratio)))
        preview = cv2.resize(frame, preview_size, interpolation=cv2.INTER_AREA)
        origin = (left + (right - left - preview_size[0]) // 2,
                  top + (bottom - top - preview_size[1]) // 2)
        canvas.paste(Image.fromarray(cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)), origin)
        if bbox:
            draw = ImageDraw.Draw(canvas)
            horizontal_start = max(left, min(right - 1, round(origin[0] + bbox[0] * ratio)))
            vertical_start = max(top, min(bottom - 1, round(origin[1] + bbox[1] * ratio)))
            horizontal_end = max(horizontal_start, min(right - 1, round(origin[0] + bbox[2] * ratio)))
            vertical_end = max(vertical_start, min(bottom - 1, round(origin[1] + bbox[3] * ratio)))
            length = min(16, (horizontal_end - horizontal_start) // 2, (vertical_end - vertical_start) // 2)
            for horizontal, vertical, direction_x, direction_y in (
                (horizontal_start, vertical_start, 1, 1), (horizontal_end, vertical_start, -1, 1),
                (horizontal_start, vertical_end, 1, -1), (horizontal_end, vertical_end, -1, -1),
            ):
                draw.line(((horizontal + direction_x * length, vertical), (horizontal, vertical),
                           (horizontal, vertical + direction_y * length)), fill="#a7b5c9", width=2)
        return cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)
