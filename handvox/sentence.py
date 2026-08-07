"""Sentence-building logic independent from any user interface."""


class SentenceBuilder:
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
        word = str(word).strip()
        if not word:
            return False
        if self.prevent_duplicates and self._words and self._words[-1] == word:
            return False
        self._words.append(word)
        return True

    def remove_last(self):
        return self._words.pop() if self._words else None

    def clear(self):
        self._words.clear()

    def replace_from_text(self, text):
        self._words.clear()
        for word in str(text).split():
            self.add(word)

    def __len__(self):
        return len(self._words)

    def __iter__(self):
        return iter(self._words)
