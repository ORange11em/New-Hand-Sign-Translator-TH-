"""Capture figure 2.1: selected HandVox MediaPipe landmarks."""

from pathlib import Path
import sys

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import (draw_legend, draw_selected_landmarks, draw_thai,
                    new_holistic, open_camera, save_png)


def main() -> int:
    output = HERE / "output"
    camera = open_camera()
    detector = new_holistic()
    window = "Figure 2.1 - HandVox Landmarks"
    saved_message = ""
    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                raise RuntimeError("อ่านภาพจากกล้องไม่ได้")
            frame = cv2.flip(frame, 1)
            results = detector.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            frame = draw_selected_landmarks(frame, results)
            frame = draw_legend(frame)
            frame = draw_thai(frame, "57 จุด × 3 พิกัด = 171 คุณลักษณะต่อเฟรม",
                              (frame.shape[1] // 2, frame.shape[0] - 55), 31,
                              (255, 255, 255), "mm")
            frame = draw_thai(frame, "กด S บันทึกภาพ | Q ออก", (20, frame.shape[0] - 38),
                              23, (210, 210, 210))
            if saved_message:
                frame = draw_thai(frame, saved_message, (frame.shape[1] - 20, 28),
                                  23, (90, 255, 120), "ra")
            cv2.imshow(window, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("s"):
                path = save_png(output, "figure_2_1_landmarks", frame)
                saved_message = f"บันทึกแล้ว: {path.name}"
                print(path)
            elif key in (ord("q"), 27):
                break
    finally:
        detector.close()
        camera.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

