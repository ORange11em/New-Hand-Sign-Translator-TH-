"""ตรวจสอบและบันทึกการตั้งค่าที่ GUI กับตัวตรวจจับใช้ร่วมกัน."""

from dataclasses import asdict, dataclass, fields
import json
from pathlib import Path

from handvox.errors import ConfigurationError
from handvox.paths import SETTINGS_FILE


@dataclass
class AppSettings:
    """ค่าปรับพฤติกรรมกล้อง การยืนยันผล เสียง ประโยค และประวัติ."""

    camera_index: int = 0
    min_confidence: float = 0.65
    confirm_frames: int = 4
    release_seconds: float = 0.35
    speak_hold_seconds: float = 1.0
    auto_add_words: bool = True
    auto_tts: bool = True
    tts_volume: float = 0.85
    font_scale: float = 1.0
    prevent_duplicate_words: bool = True
    save_spoken_sentences: bool = True
    history_limit: int = 100

    def validate(self):
        """ตรวจชนิดและช่วงค่าทั้งหมดก่อนให้ส่วนอื่นนำไปใช้."""
        if not isinstance(self.camera_index, int) or not 0 <= self.camera_index <= 20:
            raise ConfigurationError("หมายเลขกล้องต้องอยู่ระหว่าง 0 ถึง 20")
        if not 0.05 <= float(self.min_confidence) <= 1.0:
            raise ConfigurationError("Confidence ต้องอยู่ระหว่าง 0.05 ถึง 1.00")
        if not isinstance(self.confirm_frames, int) or not 1 <= self.confirm_frames <= 30:
            raise ConfigurationError("จำนวนเฟรมยืนยันต้องอยู่ระหว่าง 1 ถึง 30")
        if not 0.0 <= float(self.release_seconds) <= 5.0:
            raise ConfigurationError("เวลารีเซ็ตต้องอยู่ระหว่าง 0 ถึง 5 วินาที")
        if not 0.1 <= float(self.speak_hold_seconds) <= 10.0:
            raise ConfigurationError("เวลาค้างท่าก่อนเพิ่มคำ/อ่านต้องอยู่ระหว่าง 0.1 ถึง 10 วินาที")
        if not 0.0 <= float(self.tts_volume) <= 1.0:
            raise ConfigurationError("ระดับเสียงต้องอยู่ระหว่าง 0 ถึง 1")
        if not 0.75 <= float(self.font_scale) <= 1.75:
            raise ConfigurationError("ขนาดตัวอักษรต้องอยู่ระหว่าง 0.75 ถึง 1.75")
        if not isinstance(self.history_limit, int) or not 10 <= self.history_limit <= 1000:
            raise ConfigurationError("จำนวนประวัติต้องอยู่ระหว่าง 10 ถึง 1,000")
        for name in (
            "auto_add_words",
            "auto_tts",
            "prevent_duplicate_words",
            "save_spoken_sentences",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ConfigurationError(f"{name} ต้องเป็น true หรือ false")
        return self

    @classmethod
    def from_dict(cls, data):
        """สร้าง settings จาก JSON โดยข้าม key รุ่นใหม่ที่โปรแกรมยังไม่รู้จัก."""
        if not isinstance(data, dict):
            raise ConfigurationError("settings.json ต้องเก็บข้อมูลแบบ object")
        allowed = {field.name for field in fields(cls)}
        values = {key: value for key, value in data.items() if key in allowed}
        try:
            return cls(**values).validate()
        except TypeError as error:
            raise ConfigurationError(f"รูปแบบการตั้งค่าไม่ถูกต้อง: {error}") from error


class SettingsStore:
    """อ่านและเขียน settings.json ด้วยการแทนไฟล์แบบ atomic."""

    def __init__(self, path=SETTINGS_FILE):
        self.path = Path(path)
        self.last_error = None

    def load(self):
        """โหลดค่าที่บันทึกไว้ หรือคืนค่าเริ่มต้นเมื่อยังไม่มีไฟล์."""
        if not self.path.exists():
            return AppSettings()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConfigurationError(f"อ่าน {self.path.name} ไม่ได้: {error}") from error
        return AppSettings.from_dict(data)

    def load_or_default(self):
        """โหลดแบบไม่ทำให้แอปล้ม และเก็บข้อความผิดพลาดไว้ใน last_error."""
        self.last_error = None
        try:
            return self.load()
        except ConfigurationError as error:
            self.last_error = str(error)
            return AppSettings()

    def save(self, settings):
        """ตรวจค่าแล้วเขียนไฟล์ชั่วคราวก่อนแทนไฟล์จริง ป้องกันไฟล์ขาดกลางทาง."""
        settings.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def reset(self):
        """คืนค่าเริ่มต้นพร้อมบันทึกลงดิสก์."""
        settings = AppSettings()
        self.save(settings)
        return settings
