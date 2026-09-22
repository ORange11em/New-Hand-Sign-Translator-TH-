# แผนที่โค้ด HandVox

เอกสารนี้ใช้คู่กับ docstring และคอมเมนต์ภาษาไทยในไฟล์ Python เพื่อช่วยหาได้เร็วว่า
ส่วนใดรับผิดชอบงานอะไร โดยไม่จำเป็นต้องเริ่มอ่านจากทุกบรรทัด

## เส้นทางการทำงานตอนเปิดแอป

1. `app.py` เรียก `handvox/app.py`
2. `handvox/app.py` เริ่ม GUI จาก `handvox/ui.py`
3. `handvox/ui.py` โหลด settings, คำศัพท์, ประวัติ, Dataset และสถานะการเทรน
4. เมื่อกดเปิดกล้อง GUI ใช้ `handvox/processes.py` เปิด `run_detector.py` เป็น process แยก
5. `run_detector.py` ใช้ `body_features.py` ดึง landmark, โมเดลทำนายคำ และ
   `gesture_state.py` ยืนยันผลก่อนส่งให้ระบบสร้างประโยค
6. ประโยคใช้ตรรกะจาก `handvox/sentence.py`, จับเวลาจาก
   `handvox/camera_sentence.py`, บันทึกด้วย `handvox/history.py` และอ่านเสียงผ่าน
   `tts_service.py`

## ไฟล์หลักที่โฟลเดอร์ราก

| ไฟล์ | หน้าที่ |
| --- | --- |
| `app.py` | จุดเริ่มต้นสำหรับเปิด GUI |
| `run_detector.py` | เปิดกล้อง ทำนายท่า แสดงผล สร้าง/อ่าน/บันทึกประโยค |
| `body_features.py` | แปลง pose และมือเป็นคุณลักษณะ 171 ค่า |
| `gesture_state.py` | ยืนยันผลหลายเฟรม ปฏิเสธผลไม่มั่นใจ และกันคำซ้ำ |
| `gesture_config.py` | โหลดท่าที่โมเดลรุ่นปัจจุบันใช้ได้ |
| `tts_service.py` | จัดคิวเสียง gTTS และ fallback แบบออฟไลน์ |
| `sequence_dataset.py` | จัดการไฟล์คลิป `.npz` ของ workflow รุ่นเดิม |
| `collect_data.py` | เก็บคลิปเข้าชุดข้อมูลรุ่นเดิม |
| `train_model.py` | ฝึก SVM รุ่นเดิมและบันทึก model/labels |
| `add_gesture.py` | เพิ่มท่า เก็บคลิป และเทรนใน workflow รุ่นเดิม |
| `remove_gesture.py` | สำรองและลบท่าใน workflow รุ่นเดิม |
| `reset_gestures.py` | สำรองทุกอย่างก่อนเริ่มรายการท่าเปล่า |
| `collect_dataset_v2.py` | เก็บ sequence, preview และ metadata สำหรับ V2; `--external-evaluation` เก็บผู้ใช้ใหม่แยกจากชุดเทรน |
| `training_cli.py` | คำสั่ง status/train/list/activate และ evaluate-external ของ V2 |

## แพ็กเกจ `handvox/`

- `detector_view.py` — วาดหน้ากล้อง 1080×680 แยกภาพกับผลแปล ใช้ cache ข้อความและแปลงสีเพียงสองครั้งต่อเฟรม ไม่แก้ภาพก่อนส่งโมเดล
- `detector_performance.py` — เก็บสถิติเวลาแบบจำกัดหน่วยความจำ แยก FPS ทั้งลูปกับอัตราการทำนาย และส่งออกรายงานโดยไม่เก็บภาพ
- `detector_sequence.py` — ล้าง sequence เก่าเมื่อ landmark หายเกินเวลาปล่อยท่าเดิม โดยไม่เปลี่ยนจำนวนเฟรมหรือ resample
- `tools/profile_detector_replay.py` — replay คลิปเดิมเพื่อวัดก่อน–หลังพร้อม hash ของ input โมเดลและ probabilities ปิดกล้องจริง/เสียง/ประวัติในโหมดนี้

| ไฟล์ | หน้าที่ |
| --- | --- |
| `app.py` | จุดเริ่มต้นภายในแพ็กเกจ |
| `ui.py` | หน้าจอ Tkinter ทั้งหมดและคลาสแอปหลัก |
| `settings.py` | ตรวจ โหลด บันทึก และ reset การตั้งค่า |
| `paths.py` | รวมตำแหน่งไฟล์ทุกชนิดไว้จุดเดียว |
| `errors.py` | ข้อผิดพลาดที่แสดงกับผู้ใช้ได้ |
| `processes.py` | เปิดสคริปต์กล้อง/เก็บข้อมูลเป็น process แยก |
| `sentence.py` | เพิ่ม ลบ ล้าง และแทนคำในประโยค |
| `camera_sentence.py` | จับเวลาค้างท่าและปล่อยคำเพียงหนึ่งครั้ง |
| `history.py` | บันทึกประวัติประโยคแบบ JSON |
| `gesture_catalog.py` | แยกท่าที่ใช้ได้ออกจากแผนคำศัพท์ใหม่ |
| `diagnostics.py` | ตรวจ Python โมเดล Dataset และคำศัพท์สำหรับ Dashboard |
| `dataset_v2.py` | ตรวจและจัดเก็บ metadata.jsonl ของคลิป V2 |
| `training_config.py` | แปลง training_config.json เป็น dataclass และตรวจแผน |
| `training_workflow.py` | preflight, เทรน, วัดผล, สร้างรายงาน และติดตั้งโมเดล |

## โครงสร้าง `handvox/ui.py`

| คลาส | หน้าที่ |
| --- | --- |
| `ScrollableFrame` | ทำพื้นที่เนื้อหาเลื่อนแนวตั้งได้ |
| `Disclosure` | ซ่อนรายละเอียดระบบและตัวเลือกขั้นสูงจนกว่าจะกาง |
| `BasePage` | หัวข้อและรูปแบบร่วมของทุกหน้า |
| `DashboardPage` | สถานะโปรเจกต์และปุ่มเริ่มกล้อง |
| `SentencePage` | สร้างประโยคโดยไม่ใช้กล้องและดูประวัติ |
| `GesturesPage` | ดู active vocabulary และแก้ planned vocabulary |
| `TrainingPage` | แถบเตรียมเทรนห้าขั้น เปิดโฟลเดอร์ข้อมูล และผลทดลองพร้อมปุ่มหลักตามสถานะโมเดล |
| `SettingsPage` | ตั้งค่ากล้อง confidence เวลา เสียง และประโยค |
| `HelpPage` | วิธีใช้และขอบเขตระบบ |
| `HandVoxApp` | ประกอบเมนู หน้า ธีม และบริการร่วมทั้งหมด |

## ขั้นตอนใน `handvox/training_workflow.py`

1. `preflight` ตรวจแหล่งอ้างอิง จำนวนคลิป คุณภาพ session และไฟล์ sequence
2. `_load_accepted_arrays` โหลดเฉพาะคลิปที่ผ่านการตรวจ
3. `train_and_evaluate` เทรนจากผู้ใช้ที่ตั้งไว้ทั้งคู่ แล้วผลัดกันกันทุก session ของแต่ละคนเป็น test โดยไม่ให้ session เดียวกันรั่วข้ามชุด
4. `_metric_payload` คำนวณ Accuracy, Precision, Recall, F1 และ Confusion Matrix
5. `_acceptance_result` ตรวจว่า experiment ผ่านเกณฑ์ขั้นต่ำหรือไม่
6. `_write_*` บันทึก JSON, CSV, Markdown และกราฟลงโฟลเดอร์ experiment ใหม่
7. `activate_experiment` ตรวจและสำรองโมเดลเดิมก่อนติดตั้งผลที่ผ่านเกณฑ์ หรือรับ `allow_unvalidated_trial=True` หลังผู้ใช้ยืนยันติดตั้งแบบทดลอง โดย manifest ที่ติดตั้งมี `deployment.status = experimental_unvalidated` และคงผล `passed=False` ไว้ ไม่แก้ผลต้นฉบับ

กลยุทธ์มาตรฐาน `known_signers_session_holdout` ใช้ `_known_signers_session_holdout_folds`
หมุน session ที่ตั้งไว้ทั้งหมดเป็น test โดยใช้ session ถัดไปเป็น validation สำหรับ TCN
แต่ละส่วนมีข้อมูลของผู้ใช้ที่ตั้งไว้ทั้งคู่ และกลุ่ม `signer_id + session_id` ไม่ข้ามชุด
ภายใน fold เดียวกัน ทุกคลิปมีคำทำนายทดสอบเพียงครั้งเดียว ส่วนโมเดลส่งมอบฝึกจาก
accepted ของทั้งสองคนทั้งหมด กลยุทธ์เก่า `leave_one_signer_out` ยังรองรับ และควรอ่าน
คะแนนตามกลยุทธ์ที่บันทึกใน experiment เพราะขอบเขตการวัดต่างกัน

`_predictions_with_recognition_policy` เปลี่ยนคำทำนายของคลาสที่แสดงเป็น `unknown`
เมื่อ confidence ต่ำกว่า 0.72 หรือระยะห่างจากอันดับสองต่ำกว่า 0.12 ตาม config
นโยบายที่บันทึกใน manifest เป็นค่าขั้นต่ำที่ runtime ใช้ คะแนนนี้เป็นการวัดระดับคลิป
และไม่ได้จำลองการยืนยัน 6 เฟรมหรือเวลาค้างท่าของระบบสร้างประโยค

คำสั่ง `evaluate-external` โหลดโมเดลที่บันทึกใน experiment เพื่อวัดคลิป accepted
จาก `dataset_external_v2/` โดยไม่ฝึกใหม่ ตรวจรหัสคนและ sequence ไม่ให้ซ้ำชุดฝึก
และเขียนรายงานลง `external_evaluations/` ภายใน experiment ผลผู้ใช้ใหม่ไม่แก้คะแนน
หรือสถานะผ่านเกณฑ์ของการทดลองเดิม หน้าอ่านผลมีปุ่ม **วัดผู้ใช้ใหม่** สำหรับเก็บข้อมูล
ตรวจคุณภาพ และเรียกการวัดชุดนี้ ดูคำสั่งใช้งานใน `TRAINING_GUIDE.md`

โหมดเพิ่มทีละคำใช้ `build_incremental_training_config` สร้าง config ชั่วคราวจาก
คำในโมเดลปัจจุบันทั้งหมด + คำเป้าหมายหนึ่งคำ + `neutral` และเพิ่มคำต่อเนื่องได้

โหมดทดลองด่วนใช้ `build_quick_trial_config`, `quick_trial_readiness` และ
`train_quick_trial` เพื่อรวม `gesture_sequences.npz` กับคลิป accepted ของคำใหม่
สร้าง experiment แบบ `quick_trial` และต้องส่ง `allow_quick_trial=True` เมื่อติดตั้ง

## ชุดทดสอบ `tests/`

| ไฟล์ | สิ่งที่ทดสอบ |
| --- | --- |
| `test_camera_sentence.py` | การค้างท่า เพิ่มครั้งเดียว และเริ่มใหม่หลังปล่อย |
| `test_sentence.py` | การเพิ่ม ลบ ล้าง และคำซ้ำ |
| `test_history.py` | การเก็บ จำกัดจำนวน ลบ และล้างประวัติ |
| `test_settings.py` | การตรวจค่าและบันทึก/โหลด settings |
| `test_gesture_state.py` | candidate, confirmed, cooldown และ release |
| `test_gesture_catalog.py` | planned vocabulary, URL และชื่อซ้ำ |
| `test_dataset_v2.py` | metadata, path และ inventory |
| `test_training_workflow.py` | preflight, metrics, acceptance และ experiment สังเคราะห์ |

## เครื่องมือใน `tools/`

| ไฟล์ | หน้าที่ |
| --- | --- |
| `build_handvox_chapters.py` | สร้างเอกสาร Word บทที่ 1–5 |
| `audit_final_handvox_docs.py` | ตรวจรายการสำคัญในเอกสารสุดท้าย |
| `inspect_docx.py` | ตรวจโครงสร้างย่อหน้า ตาราง รูป และ style ของ DOCX |
| `evaluate_handvox.py` | สรุปผลโมเดลรุ่นเดิมแบบอ่านอย่างเดียว |
| `capture_training_gui.py` | จับภาพ GUI สำหรับ visual QA โดยไม่เปิดกล้อง |
| `pdf_to_png.py` | แปลง PDF เป็นภาพ PNG รายหน้า |

## ไฟล์กำหนดค่าและข้อมูล

- `training_config.json` กำหนดคำตั้งต้น, neutral, สมาชิก, session, โมเดล และเกณฑ์ผ่าน
- `custom_gestures.json` คือคำที่โมเดลปัจจุบันใช้งานได้
- `planned_gestures.json` คือคำที่ยังเป็นแผนและยังทำนายไม่ได้
- `settings.json` คือค่าที่ผู้ใช้บันทึกจาก GUI
- `conversation_history.json` คือประวัติประโยค
- `dataset_v2/metadata.jsonl` คือทะเบียนคลิป V2 ทีละบรรทัด
- `dataset_external_v2/metadata.jsonl` คือทะเบียนคลิปผู้ใช้ใหม่สำหรับวัดผลภายหลัง
- `experiments/` เก็บผลทุกครั้งแยกกันและไม่เขียนทับโมเดลหลักอัตโนมัติ

## หลักในการอ่านและแก้โค้ด

- ถ้าจะแก้หน้าตา ให้เริ่มที่ `handvox/ui.py`
- ถ้าจะแก้การรับคำจากกล้อง ให้เริ่มที่ `run_detector.py` และ `gesture_state.py`
- ถ้าจะแก้คุณลักษณะ landmark ต้องแก้โดยระวังทั้งการเก็บและการตรวจจับใน
  `body_features.py`
- ถ้าจะแก้จำนวนท่าหรือเกณฑ์ทดลอง ให้แก้ `training_config.json` และผ่าน validation
- อย่าเขียนทับโมเดล V2 ด้วย `train_model.py`; ใช้ Wizard หรือ `training_cli.py`
- หลังแก้ Python ให้รัน `.venv\Scripts\python.exe -m unittest discover -s tests -v`
