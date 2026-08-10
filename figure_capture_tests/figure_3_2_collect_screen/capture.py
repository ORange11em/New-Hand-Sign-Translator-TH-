"""Safe camera mock-up for figure 3.2; never writes to HandVox datasets."""

import argparse
from pathlib import Path
import sys
import time

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1]))
from common import draw_selected_landmarks, draw_thai, new_holistic, open_camera, save_png
from body_features import extract_features, upper_body_bbox


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gesture", default="สวัสดี")
    parser.add_argument("--clip", type=int, default=7)
    args = parser.parse_args()
    output = HERE / "output"
    camera = open_camera()
    detector = new_holistic()
    state = "ready"
    countdown_started = 0.0
    progress = 0
    auto_saved = False
    window = "Figure 3.2 - Safe Clip Collection Test"
    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                raise RuntimeError("อ่านภาพจากกล้องไม่ได้")
            frame = cv2.flip(frame, 1)
            results = detector.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            display = draw_selected_landmarks(frame.copy(), results)
            height, width = display.shape[:2]
            bbox = upper_body_bbox(results, width, height)
            if bbox:
                cv2.rectangle(display, bbox[:2], bbox[2:], (70, 255, 130), 2)

            if state == "countdown":
                remaining = 3 - int(time.time() - countdown_started)
                if remaining <= 0:
                    state = "recording"
                    progress = 0
                else:
                    display = draw_thai(display, str(remaining), (width // 2, height // 2),
                                        92, (0, 220, 255), "mm")
            elif state == "recording":
                if extract_features(results) is not None and progress < 30:
                    progress += 1
                if progress >= 30:
                    state = "done"

            overlay = display.copy()
            cv2.rectangle(overlay, (0, 0), (width, 126), (20, 20, 20), -1)
            cv2.addWeighted(overlay, 0.74, display, 0.26, 0, display)
            display = draw_thai(display, f"ท่า: {args.gesture}", (22, 10), 35,
                                (70, 255, 130))
            display = draw_thai(display, f"คลิปที่ {args.clip}/30", (22, 55), 29)
            if state == "ready":
                status = "พร้อม — กด Space เพื่อเริ่มจำลองการเก็บ"
            elif state == "countdown":
                status = "กำลังนับถอยหลัง"
            elif state == "recording":
                status = f"กำลังบันทึกเฟรม {progress}/30"
            else:
                status = "บันทึกครบ 30/30 เฟรม — กด R เพื่อเริ่มใหม่"
            display = draw_thai(display, status, (width - 22, 28), 30,
                                (80, 255, 120), "ra")
            display = draw_thai(display, "S บันทึกภาพ | Q ออก | ไม่เขียน Dataset จริง",
                                (width - 22, 75), 23, (220, 220, 220), "ra")
            if state == "recording" and progress >= 15 and not auto_saved:
                path = save_png(output, "figure_3_2_collect_screen", display)
                print(path)
                auto_saved = True
            cv2.imshow(window, display)
            key = cv2.waitKey(1) & 0xFF
            if key == ord(" ") and state in ("ready", "done"):
                state = "countdown"
                countdown_started = time.time()
                auto_saved = False
            elif key == ord("s"):
                path = save_png(output, "figure_3_2_collect_screen", display)
                print(path)
            elif key == ord("r"):
                state, progress, auto_saved = "ready", 0, False
            elif key in (ord("q"), 27):
                break
    finally:
        detector.close()
        camera.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
