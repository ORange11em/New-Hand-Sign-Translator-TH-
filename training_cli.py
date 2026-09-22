"""คำสั่ง CLI สำหรับตรวจความพร้อม เทรน ดูผล และติดตั้งโมเดล Dataset V2."""

import argparse
from pathlib import Path

from handvox.errors import HandVoxError
from handvox.dataset_v2 import DatasetV2Store
from handvox.external_evaluation import evaluate_external
from handvox.paths import EXPERIMENTS_DIR, ROOT
from handvox.gesture_catalog import GestureCatalog
from handvox.training_config import (
    build_incremental_training_config,
    build_quick_trial_config,
    incremental_targets,
    load_training_config,
)
from handvox.training_workflow import (
    activate_experiment,
    list_experiments,
    preflight,
    quick_trial_readiness,
    save_preflight_report,
    train_and_evaluate,
    train_quick_trial,
)


STATUS_LABELS = {"ok": "พร้อม", "warning": "ควรตรวจ", "error": "ต้องแก้"}


def print_preflight(report):
    """พิมพ์รายงานความพร้อมแบบสั้นสำหรับอ่านใน Command Prompt."""
    print("=" * 68)
    print("HandVox V2 - Training Preflight")
    print("=" * 68)
    print(
        f"accepted: {report.accepted_clips}/{report.expected_target_clips} คลิป | "
        f"สถานะ: {'พร้อมเทรน' if report.ready else 'ยังไม่พร้อม'}"
    )
    for item in report.items:
        print(f"[{STATUS_LABELS.get(item.status, item.status)}] {item.message}")


def round_config(target):
    """สร้าง config รอบปัจจุบันจากคำเดิมในโมเดลและคำใหม่หนึ่งคำ."""
    if not target:
        return load_training_config()
    catalog = GestureCatalog()
    active_names = [item.name for item in catalog.load_active()]
    planned_names = [item.name for item in catalog.load_planned()]
    return build_incremental_training_config(
        target,
        active_names=active_names,
        planned_names=planned_names,
    )


def command_status(target=None):
    """ตรวจและบันทึก preflight_latest.json โดยไม่เริ่มเทรน."""
    config = round_config(target)
    report = preflight(config)
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    output = EXPERIMENTS_DIR / "preflight_latest.json"
    save_preflight_report(report, output)
    print_preflight(report)
    print(f"\nบันทึกรายงาน: {output}")
    return 0 if report.ready else 2


def command_train(target=None):
    """หยุดเมื่อข้อมูลไม่พร้อม มิฉะนั้นสร้าง experiment และรายงานใหม่."""
    config = round_config(target)
    report = preflight(config)
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    save_preflight_report(report, EXPERIMENTS_DIR / "preflight_latest.json")
    print_preflight(report)
    if not report.ready:
        print("\nยังไม่เริ่มเทรน เพราะมีรายการที่ต้องแก้")
        return 2
    print("\nกำลังเทรนและประเมินด้วย session ที่กันไว้ของผู้ใช้ทั้งสอง...")
    experiment_dir, payload = train_and_evaluate(config=config)
    aggregate = payload["aggregate"]
    print(f"Accuracy : {aggregate['accuracy']:.4f}")
    print(f"Macro F1: {aggregate['macro_f1']:.4f}")
    print(f"ผลเกณฑ์ : {'ผ่าน' if aggregate['passed'] else 'ยังไม่ผ่าน'}")
    print(f"รายงาน   : {experiment_dir}")
    print("โมเดลหลักยังไม่ถูกเขียนทับ")
    return 0


def command_quick_train(target):
    """เทรนคำใหม่ทันทีจากข้อมูลฐานเดิม และสร้างโมเดลทดลองสำหรับเปิดกล้อง."""
    catalog = GestureCatalog()
    active_names = [item.name for item in catalog.load_active()]
    planned_names = [item.name for item in catalog.load_planned()]
    config = build_quick_trial_config(
        target,
        active_names=active_names,
        planned_names=planned_names,
    )
    report = quick_trial_readiness(config)
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    save_preflight_report(report, EXPERIMENTS_DIR / "quick_preflight_latest.json")
    print_preflight(report)
    if not report.ready:
        print("\nยังเทรนด่วนไม่ได้ — เก็บและกดยอมรับคลิปคำใหม่อย่างน้อย 4 คลิปก่อน")
        return 2
    print("\nกำลังเทรนทดลองด่วนจากข้อมูลฐานเดิม + คำใหม่...")
    experiment_dir, payload = train_quick_trial(config)
    aggregate = payload["aggregate"]
    print(f"Accuracy : {aggregate['accuracy']:.4f}")
    print(f"Macro F1: {aggregate['macro_f1']:.4f}")
    print(f"ผลเกณฑ์ : {'ผ่าน' if aggregate['passed'] else 'ยังไม่ผ่าน'}")
    print(f"รายงาน   : {experiment_dir}")
    print("หากผ่าน ให้ติดตั้งผลแบบทดลอง แล้วเปิดกล้องทดสอบจริง")
    return 0


def command_list():
    """แสดง Accuracy, Macro F1 และสถานะผ่านของ experiment ที่มีอยู่."""
    experiments = list_experiments()
    if not experiments:
        print("ยังไม่มีผลการทดลอง")
        return 0
    for item in experiments:
        print(
            f"{item['id']} | accuracy={item['accuracy']:.4f} | "
            f"macro_f1={item['macro_f1']:.4f} | "
            f"{'ผ่าน' if item['passed'] else 'ยังไม่ผ่าน'}"
        )
    return 0


def command_targets():
    """แสดงคำที่ยังเพิ่มได้ทีละคำและขอบเขตรอบแรกโดยสรุป."""
    config = load_training_config()
    catalog = GestureCatalog()
    active_names = [item.name for item in catalog.load_active()]
    planned_names = [item.name for item in catalog.load_planned()]
    targets = incremental_targets(config, active_names, planned_names)
    print("คำที่อยู่ในโมเดล:", ", ".join(active_names) or "ยังไม่มี")
    print("คำที่ยังเพิ่มได้:", ", ".join(targets) or "ครบแผนแล้ว")
    return 0


def command_activate(experiment, confirmed, allow_quick_trial=False, allow_unvalidated_trial=False):
    """ขอยืนยันก่อนสำรองโมเดลเดิมและติดตั้ง experiment ที่ผ่านเกณฑ์."""
    directory = Path(experiment)
    if not directory.is_absolute():
        directory = EXPERIMENTS_DIR / directory
    if not confirmed:
        confirmation_word = "INSTALL EXPERIMENTAL" if allow_unvalidated_trial else "ACTIVATE"
        answer = input(
            (
                "คำเตือน: ติดตั้งแบบทดลองแม้ผลยังไม่ผ่าน คะแนนเดิมจะไม่เปลี่ยน "
                if allow_unvalidated_trial else "ติดตั้งโมเดลที่ผ่านเกณฑ์ "
            ) + f"โดยสำรองของเดิมก่อน พิมพ์ {confirmation_word}: "
        ).strip()
        if answer != confirmation_word:
            print("ยกเลิก")
            return 1
    backup = activate_experiment(
        directory, allow_quick_trial=allow_quick_trial,
        allow_unvalidated_trial=allow_unvalidated_trial,
    )
    if allow_unvalidated_trial:
        print("คำเตือน: ขอใช้แบบทดลองเท่านั้น ผลประเมินเดิมยังไม่ถูกเปลี่ยนให้ผ่าน")
    print(f"ติดตั้งโมเดลแล้ว สำรองของเดิมไว้ที่ {backup}")
    return 0


def command_evaluate_external(experiment, dataset):
    """วัดโมเดลที่บันทึกไว้กับข้อมูลผู้ใช้ใหม่และแสดงตำแหน่งรายงาน."""
    directory = Path(experiment)
    if not directory.is_absolute() and not directory.is_dir():
        directory = EXPERIMENTS_DIR / directory
    report_dir, payload = evaluate_external(directory, DatasetV2Store(Path(dataset)))
    aggregate = payload["aggregate"]
    print("ผลวัดผู้ใช้ใหม่:", ", ".join(payload["signers"]))
    print(f"Accuracy : {aggregate['accuracy']:.4f}")
    print(f"Macro F1: {aggregate['macro_f1']:.4f}")
    print(f"จำนวนคลิป: {payload['accepted_clips']}")
    if payload["missing_classes"]:
        print("คลาสที่ยังไม่มีคลิปทดสอบ:", ", ".join(payload["missing_classes"]))
    print(f"รายงาน   : {report_dir}")
    print("ผลวัดผู้ใช้ใหม่บันทึกแยกจากคะแนนและสิทธิ์ติดตั้งของโมเดล")
    return 0


def main(argv=None):
    """แยกคำสั่ง status/train/list/activate และแปลงข้อผิดพลาดเป็น exit code."""
    parser = argparse.ArgumentParser(description="HandVox V2 training workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status", help="ตรวจความพร้อมโดยไม่เทรน")
    status.add_argument("--target", help="คำใหม่หนึ่งคำสำหรับรอบเพิ่มทีละคำ")
    train = subparsers.add_parser("train", help="ตรวจข้อมูล เทรน วัดผล และสร้างรายงาน")
    train.add_argument("--target", help="คำใหม่หนึ่งคำสำหรับรอบเพิ่มทีละคำ")
    quick_train = subparsers.add_parser(
        "quick-train", help="เทรนคำใหม่ทันทีจากข้อมูลฐานเดิมสำหรับทดสอบกล้อง"
    )
    quick_train.add_argument("--target", required=True, help="คำใหม่หนึ่งคำ")
    subparsers.add_parser("list", help="แสดงผลการทดลองที่ผ่านมา")
    subparsers.add_parser("targets", help="แสดงคำที่ยังเลือกเพิ่มทีละคำได้")
    activate = subparsers.add_parser("activate", help="ติดตั้งโมเดลที่ผ่านเกณฑ์")
    activate.add_argument("experiment", help="รหัสหรือ path ของผลการทดลอง")
    activate.add_argument("--yes", action="store_true", help="ยืนยันจาก workflow ภายนอก")
    activate.add_argument(
        "--allow-quick-trial",
        action="store_true",
        help="ยืนยันการติดตั้งผลโหมดทดลองด่วน",
    )
    activate.add_argument(
        "--allow-unvalidated-trial", action="store_true",
        help="ยืนยันติดตั้งแบบทดลองแม้ไม่ผ่านเกณฑ์ โดยไม่เปลี่ยนผลคะแนน",
    )
    external = subparsers.add_parser(
        "evaluate-external", help="วัดโมเดลเดิมกับคลิปผู้ใช้ใหม่โดยไม่เทรนเพิ่ม"
    )
    external.add_argument("experiment", help="รหัสหรือ path ของผลการทดลอง")
    external.add_argument(
        "--dataset",
        default=ROOT / "dataset_external_v2",
        help="โฟลเดอร์ข้อมูลผู้ใช้ใหม่ (ค่าเริ่มต้น dataset_external_v2)",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            return command_status(args.target)
        if args.command == "train":
            return command_train(args.target)
        if args.command == "quick-train":
            return command_quick_train(args.target)
        if args.command == "list":
            return command_list()
        if args.command == "targets":
            return command_targets()
        if args.command == "evaluate-external":
            return command_evaluate_external(args.experiment, args.dataset)
        return command_activate(
            args.experiment, args.yes, args.allow_quick_trial, args.allow_unvalidated_trial
        )
    except HandVoxError as error:
        print(f"ไม่สำเร็จ: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
