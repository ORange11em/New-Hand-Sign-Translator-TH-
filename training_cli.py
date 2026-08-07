"""Command-line entry point for the reproducible HandVox V2 workflow."""

import argparse
from pathlib import Path

from handvox.errors import HandVoxError
from handvox.paths import EXPERIMENTS_DIR
from handvox.training_workflow import (
    activate_experiment,
    list_experiments,
    preflight,
    save_preflight_report,
    train_and_evaluate,
)


STATUS_LABELS = {"ok": "พร้อม", "warning": "ควรตรวจ", "error": "ต้องแก้"}


def print_preflight(report):
    print("=" * 68)
    print("HandVox V2 - Training Preflight")
    print("=" * 68)
    print(
        f"accepted: {report.accepted_clips}/{report.expected_target_clips} คลิป | "
        f"สถานะ: {'พร้อมเทรน' if report.ready else 'ยังไม่พร้อม'}"
    )
    for item in report.items:
        print(f"[{STATUS_LABELS.get(item.status, item.status)}] {item.message}")


def command_status():
    report = preflight()
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    output = EXPERIMENTS_DIR / "preflight_latest.json"
    save_preflight_report(report, output)
    print_preflight(report)
    print(f"\nบันทึกรายงาน: {output}")
    return 0 if report.ready else 2


def command_train():
    report = preflight()
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    save_preflight_report(report, EXPERIMENTS_DIR / "preflight_latest.json")
    print_preflight(report)
    if not report.ready:
        print("\nยังไม่เริ่มเทรน เพราะมีรายการที่ต้องแก้")
        return 2
    print("\nกำลังเทรนและประเมินแบบสลับสมาชิก 2 คน...")
    experiment_dir, payload = train_and_evaluate()
    aggregate = payload["aggregate"]
    print(f"Accuracy : {aggregate['accuracy']:.4f}")
    print(f"Macro F1: {aggregate['macro_f1']:.4f}")
    print(f"ผลเกณฑ์ : {'ผ่าน' if aggregate['passed'] else 'ยังไม่ผ่าน'}")
    print(f"รายงาน   : {experiment_dir}")
    print("โมเดลหลักยังไม่ถูกเขียนทับ")
    return 0


def command_list():
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


def command_activate(experiment, confirmed):
    directory = Path(experiment)
    if not directory.is_absolute():
        directory = EXPERIMENTS_DIR / directory
    if not confirmed:
        answer = input(
            "คำสั่งนี้จะสำรองโมเดลเดิมและติดตั้งโมเดลที่ผ่านเกณฑ์ พิมพ์ ACTIVATE: "
        ).strip()
        if answer != "ACTIVATE":
            print("ยกเลิก")
            return 1
    backup = activate_experiment(directory)
    print(f"ติดตั้งโมเดลแล้ว สำรองของเดิมไว้ที่ {backup}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="HandVox V2 training workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="ตรวจความพร้อมโดยไม่เทรน")
    subparsers.add_parser("train", help="ตรวจข้อมูล เทรน วัดผล และสร้างรายงาน")
    subparsers.add_parser("list", help="แสดงผลการทดลองที่ผ่านมา")
    activate = subparsers.add_parser("activate", help="ติดตั้งโมเดลที่ผ่านเกณฑ์")
    activate.add_argument("experiment", help="รหัสหรือ path ของผลการทดลอง")
    activate.add_argument("--yes", action="store_true", help="ยืนยันจาก workflow ภายนอก")
    args = parser.parse_args()
    try:
        if args.command == "status":
            return command_status()
        if args.command == "train":
            return command_train()
        if args.command == "list":
            return command_list()
        return command_activate(args.experiment, args.yes)
    except HandVoxError as error:
        print(f"ไม่สำเร็จ: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

