"""Open the person_03 test collector against the currently installed 01+02 model."""

import tkinter as tk
from tkinter import messagebox

from handvox.external_evaluation import get_training_signers
from handvox.external_evaluation_ui import ExternalEvaluationDialog
from handvox.paths import EXPERIMENTS_DIR
from handvox.ui import HandVoxApp, installed_experiment_id


def main():
    root = tk.Tk()
    app = HandVoxApp(root)
    try:
        experiment_id = installed_experiment_id()
        directory = (EXPERIMENTS_DIR / experiment_id).resolve()
        if not experiment_id or not directory.is_relative_to(EXPERIMENTS_DIR.resolve()):
            raise ValueError("ไม่พบรหัสโมเดลที่ติดตั้งอยู่")
        if set(get_training_signers(directory)) != {"person_01", "person_02"}:
            raise ValueError("แผนนี้ต้องใช้โมเดลที่ฝึกจาก person_01 และ person_02 เท่านั้น")
        root.update_idletasks()
        ExternalEvaluationDialog(root, app, {"id": experiment_id, "path": str(directory)})
    except Exception as error:
        messagebox.showerror("เปิดหน้าถ่าย 03 ไม่สำเร็จ", str(error), parent=root)
        root.destroy()
        return 1
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
