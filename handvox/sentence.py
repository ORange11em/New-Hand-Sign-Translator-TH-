"""ตรรกะเพิ่ม ลบ ล้าง และแทนคำในประโยค โดยไม่ผูกกับ GUI หรือกล้อง."""


class SentenceBuilder:
    """เก็บรายการคำของประโยคและควบคุมการเพิ่มคำซ้ำติดกัน."""

    def __init__(self, words=None, prevent_duplicates=True):
        self._words = []
        self.prevent_duplicates = bool(prevent_duplicates)
        for word in words or ():
            self.add(word)

    @property
    def words(self):
        return tuple(self._words)

    @property
    def text(self):
        return " ".join(self._words)

    def add(self, word):
        """เพิ่มคำที่ไม่ว่าง และคืน True เมื่อเพิ่มสำเร็จ."""
        word = str(word).strip()
        if not word:
            return False
        if self.prevent_duplicates and self._words and self._words[-1] == word:
            return False
        self._words.append(word)
        return True

    def remove_last(self):
        """ลบคำท้ายสุด หรือคืน None เมื่อประโยคว่าง."""
        return self._words.pop() if self._words else None

    def clear(self):
        """ล้างทุกคำในประโยคปัจจุบัน."""
        self._words.clear()

    def replace_from_text(self, text):
        """แทนประโยคเดิมด้วยคำที่แยกจากข้อความตามช่องว่าง."""
        self._words.clear()
        for word in str(text).split():
            self.add(word)

    def __len__(self):
        return len(self._words)

    def __iter__(self):
        return iter(self._words)
