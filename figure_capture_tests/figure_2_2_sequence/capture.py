"""Capture 30 valid frames and build the figure 2.2 contact sheet."""

from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1]))
from common import draw_selected_landmarks, draw_thai, new_holistic, open_camera, thai_font
from body_features import extract_features


FRAME_INDEXES = (0, 4, 9, 14, 19, 24, 29)


def build_sheet(frames: list[np.ndarray], output: Path) -> Path:
    thumb_w, thumb_h = 420, 236
    margin, gap, title_h, label_h = 34, 18, 88, 46
    cols, rows = 4, 2
    width = margin * 2 + cols * thumb_w + (cols - 1) * gap
    height = title_h + rows * (thumb_h + label_h) + gap + 82
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((width // 2, 18), "การแทนหนึ่งท่าเป็นลำดับ 30 เฟรม",
              font=thai_font(46), fill="black", anchor="ma")
    for position, frame_index in enumerate(FRAME_INDEXES):
        row, col = divmod(position, cols)
        x = margin + col * (thumb_w + gap)
        y = title_h + row * (thumb_h + label_h + gap)
        rgb = cv2.cvtColor(cv2.resize(frames[frame_index], (thumb_w, thumb_h)),
                           cv2.COLOR_BGR2RGB)
        canvas.paste(Image.fromarray(rgb), (x, y))
        draw.rectangle((x, y, x + thumb_w, y + thumb_h), outline="#555555", width=2)
        draw.text((x + thumb_w // 2, y + thumb_h + 5), f"เฟรม {frame_index + 1}",
                  font=thai_font(28), fill="black", anchor="ma")
        if position < len(FRAME_INDEXES) - 1 and col < cols - 1:
            draw.text((x + thumb_w + gap // 2, y + thumb_h // 2), "→",
                      font=thai_font(34), fill="#1f4e79", anchor="mm")
    draw.text((width // 2, height - 56),
              "30 เฟรม × 171 คุณลักษณะ = เวกเตอร์ 5,130 ค่า",
              font=thai_font(36), fill="#000000", anchor="mm")
    output.mkdir(parents=True, exist_ok=True)
    path = output / "figure_2_2_sequence_30_frames.png"
    canvas.save(path, dpi=(300, 300))
    return path


def main() -> int:
    output = HERE / "output"
    camera = open_camera()
    detector = new_holistic()
    frames: list[np.ndarray] = []
    recording = False
    window = "Figure 2.2 - 30 Frame Sequence"
    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                raise RuntimeError("อ่านภาพจากกล้องไม่ได้")
            frame = cv2.flip(frame, 1)
            results = detector.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            display = draw_selected_landmarks(frame.copy(), results)
            features = extract_features(results)
            if recording and features is not None:
                frames.append(display.copy())
                if len(frames) == 30:
                    path = build_sheet(frames, output)
                    print(path)
                    recording = False
            status = (f"กำลังเก็บเฟรม {len(frames)}/30" if recording
                      else "กด Space เพื่อเริ่มเก็บหนึ่งท่า | R เริ่มใหม่ | Q ออก")
            display = draw_thai(display, status, (20, 22), 31,
                                (80, 255, 120) if recording else (255, 255, 255))
            if len(frames) == 30 and not recording:
                display = draw_thai(display, "สร้างภาพลำดับแล้วในโฟลเดอร์ output",
                                    (20, 65), 27, (80, 255, 120))
            cv2.imshow(window, display)
            key = cv2.waitKey(1) & 0xFF
            if key == ord(" "):
                frames = []
                recording = True
            elif key == ord("r"):
                frames = []
                recording = False
            elif key in (ord("q"), 27):
                break
    finally:
        detector.close()
        camera.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

