"""Serialized speech output for HandVox."""

import os
from pathlib import Path
from queue import Empty, Full, Queue
import tempfile
import threading
import time
import uuid


class SpeechService:
    """Play one utterance at a time from a small non-blocking queue."""

    _STOP = object()

    def __init__(self, queue_size=4, volume=0.85):
        self._queue = Queue(maxsize=queue_size)
        self._volume = min(1.0, max(0.0, float(volume)))
        self._gtts_class = None
        self._pygame = None
        self._pyttsx3 = None
        self._offline_engine = None
        self._worker = None
        self.engine_name = "none"

        try:
            from gtts import gTTS
            import pygame

            pygame.mixer.init()
            pygame.mixer.music.set_volume(self._volume)
            self._gtts_class = gTTS
            self._pygame = pygame
            self.engine_name = "gTTS"
        except Exception as error:
            print(f"⚠️ เปิด gTTS/pygame ไม่ได้: {error}")

        try:
            import pyttsx3

            self._pyttsx3 = pyttsx3
            if self.engine_name == "none":
                self.engine_name = "offline"
        except Exception as error:
            print(f"⚠️ เปิดเสียงออฟไลน์ไม่ได้: {error}")

        if self.available:
            self._worker = threading.Thread(
                target=self._run, name="handvox-speech", daemon=True
            )
            self._worker.start()

    @property
    def available(self):
        return self._gtts_class is not None or self._pyttsx3 is not None

    def speak(self, text):
        text = str(text).strip()
        if not self.available or not text:
            return False
        try:
            self._queue.put_nowait(text)
            return True
        except Full:
            print("⚠️ คิวเสียงเต็ม ข้ามคำพูดนี้")
            return False

    def close(self, timeout=2.0):
        if self._worker is None:
            return
        while True:
            try:
                self._queue.put_nowait(self._STOP)
                break
            except Full:
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except Empty:
                    pass
        self._worker.join(timeout=timeout)
        self._worker = None

    def _run(self):
        while True:
            try:
                text = self._queue.get(timeout=0.25)
            except Empty:
                continue
            try:
                if text is self._STOP:
                    return
                try:
                    self._speak_once(text)
                except Exception as error:
                    print(f"⚠️ ระบบเสียงทำงานไม่สำเร็จ: {error}")
            finally:
                self._queue.task_done()

    def _speak_once(self, text):
        if self._gtts_class is not None and self._pygame is not None:
            try:
                self._speak_online(text)
                return
            except Exception as error:
                print(f"⚠️ gTTS ใช้งานไม่ได้ กำลังลองเสียงออฟไลน์: {error}")
        self._speak_offline(text)

    def _speak_online(self, text):
        temporary = Path(tempfile.gettempdir()) / f"handvox_{uuid.uuid4().hex}.mp3"
        try:
            self._gtts_class(text=text, lang="th").save(str(temporary))
            self._pygame.mixer.music.load(str(temporary))
            self._pygame.mixer.music.set_volume(self._volume)
            self._pygame.mixer.music.play()
            while self._pygame.mixer.music.get_busy():
                time.sleep(0.05)
            self._pygame.mixer.music.unload()
        finally:
            try:
                self._pygame.mixer.music.unload()
            except Exception:
                pass
            try:
                os.remove(temporary)
            except FileNotFoundError:
                pass

    def _speak_offline(self, text):
        if self._pyttsx3 is None:
            print("⚠️ ไม่มีระบบเสียงที่ใช้งานได้")
            return
        if self._offline_engine is None:
            self._offline_engine = self._pyttsx3.init()
            self._offline_engine.setProperty("volume", self._volume)
        self._offline_engine.say(text)
        self._offline_engine.runAndWait()
