"""จุดเริ่มต้นของแพ็กเกจ GUI และตัวดักข้อผิดพลาดระดับโปรแกรม."""

from handvox.ui import run


def main() -> None:
    """ส่งต่อไปยังฟังก์ชัน run ของ GUI เพื่อให้เรียกผ่าน python -m ได้."""
    run()


if __name__ == "__main__":
    main()
