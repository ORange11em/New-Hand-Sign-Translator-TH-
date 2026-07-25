# test_tts.py — รันไฟล์นี้เพื่อทดสอบเสียงแยกจากโปรแกรมหลัก
# python test_tts.py

import os, time

print("=" * 40)
print("  TTS Debug Test")
print("=" * 40)

# ── Test 1: pyttsx3 ──────────────────────────────
print("\n[1] ทดสอบ pyttsx3...")
try:
    import pyttsx3
    engine = pyttsx3.init()
    engine.setProperty("rate", 150)

    # แสดง voice ที่มีทั้งหมด
    voices = engine.getProperty("voices")
    print(f"    พบเสียง {len(voices)} เสียง:")
    for i, v in enumerate(voices):
        print(f"    [{i}] {v.name}  |  {v.id}")

    print("    กำลังพูดผ่าน pyttsx3...")
    engine.say("สวัสดีครับ ระบบเสียงทำงานได้ปกติ")
    engine.runAndWait()
    print("    ✅ pyttsx3 OK")
except Exception as e:
    print(f"    ❌ pyttsx3 error: {e}")
    print("    → pip install pyttsx3")

# ── Test 2: gTTS + pygame ────────────────────────
print("\n[2] ทดสอบ gTTS + pygame...")
try:
    from gtts import gTTS
    import pygame
    import tempfile

    print("    กำลังสร้างไฟล์เสียง gTTS...")
    tts = gTTS(text="ดีจ้าา", lang="th")
    tmp = os.path.join(tempfile.gettempdir(), "tts_test.mp3")
    tts.save(tmp)
    print(f"    บันทึกไฟล์ที่: {tmp}")
    print(f"    ขนาดไฟล์: {os.path.getsize(tmp)} bytes")

    pygame.mixer.init()
    pygame.mixer.music.load(tmp)
    pygame.mixer.music.play()
    print("    กำลังเล่นเสียง...")
    timeout = time.time() + 8
    while pygame.mixer.music.get_busy():
        time.sleep(0.1)
        if time.time() > timeout:
            print("    ⚠️ timeout รอเสียงนานเกินไป")
            break
    pygame.mixer.music.unload()
    os.remove(tmp)
    print("    ✅ gTTS + pygame OK")
except Exception as e:
    print(f"    ❌ gTTS/pygame error: {e}")

# ── Test 3: winsound (Windows built-in) ─────────
print("\n[3] ทดสอบ winsound (Windows built-in)...")
try:
    import winsound
    print("    เล่น beep...")
    winsound.Beep(1000, 500)
    print("    ✅ winsound OK — ระบบเสียงคอมฯ ทำงานได้")
except Exception as e:
    print(f"    ❌ winsound error: {e}")

print("\n" + "=" * 40)
print("  ดูผลแล้วส่งให้ดูได้เลยครับ")
print("=" * 40)