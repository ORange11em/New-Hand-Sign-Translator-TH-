"""ชนิดข้อผิดพลาดของ HandVox ที่ GUI สามารถนำไปแสดงกับผู้ใช้ได้อย่างปลอดภัย."""


class HandVoxError(Exception):
    """คลาสฐานของปัญหาที่คาดหมายและอธิบายกับผู้ใช้ได้."""


class ConfigurationError(HandVoxError):
    """ค่าตั้งต้นหรือไฟล์ configuration ไม่ถูกต้อง."""


class DataFileError(HandVoxError):
    """ไฟล์ข้อมูลอ่านไม่ได้ ขาดฟิลด์ หรือไม่ผ่านการตรวจสอบ."""


class LaunchError(HandVoxError):
    """ไม่สามารถเปิดสคริปต์ย่อย หรือสคริปต์นั้นกำลังทำงานอยู่."""
