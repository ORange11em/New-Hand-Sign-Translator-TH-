# HandVox experiment results

`training_cli.py train` จะสร้างโฟลเดอร์ใหม่ตามวันเวลาให้ทุกการทดลอง โดยไม่เขียนทับผลเดิม

ไฟล์ `experiment_index.csv` ที่ระดับบนจะรวม Accuracy, Macro F1 และผลผ่านเกณฑ์ของทุกการทดลอง เพื่อเปรียบเทียบหลายรอบในตารางเดียว

ไฟล์ที่เหมาะสำหรับนำไปทำเอกสาร:

- `report.md` — สรุปผลภาษาไทย
- `metrics.json` — ค่าทั้งหมดแบบ machine-readable
- `summary.csv` — ค่าสรุปหนึ่งแถวสำหรับนำไปรวมตารางหลายการทดลอง
- `fold_summary.csv` — ผลทดสอบแยกตามสมาชิกที่ถูกกันไว้
- `per_class_metrics.csv` — Precision, Recall และ F1 ของแต่ละท่า
- `confusion_matrix.csv` และ `confusion_matrix.png`
- `per_class_f1.png`
- `dataset_inventory.csv` — จำนวนข้อมูลที่ใช้จริง
- `training_config.snapshot.json` — ค่าที่ใช้ในการทดลองนั้น
- `preflight.json` — หลักฐานว่าข้อมูลผ่านการตรวจอะไรบ้าง

`model.pkl` และ `labels.pkl` ถูกเก็บไว้ในเครื่องแต่ไม่ถูกนำเข้า Git เนื่องจากเป็นไฟล์ไบนารีขนาดใหญ่ โมเดลหลักจะไม่ถูกแทนที่อัตโนมัติ
