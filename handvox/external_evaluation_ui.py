"""Collect and review independent test clips without adding them to training."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import tkinter as tk
from tkinter import messagebox, ttk

from handvox.dataset_v2 import DatasetV2Store, LIGHTING_VALUES
from handvox.external_collection import (
    ADDITIONAL_TEST_SESSIONS,
    ADDITIONAL_CLIPS_PER_CLASS,
    external_session_choices,
    external_session_target,
    next_additional_session,
    session_progress,
)
from handvox.external_evaluation import (
    evaluate_external,
    get_experiment_classes,
    get_training_signers,
)
from handvox.paths import ROOT
from handvox.training_config import load_training_config


def external_result_summary(payload):
    aggregate = payload["aggregate"]
    missing = payload.get("missing_classes", [])
    coverage = f" · ยังขาด {len(missing)} คลาส" if missing else " · ครบทุกคลาส"
    return (
        f"ผลผู้ใช้ใหม่: Accuracy {aggregate['accuracy']:.2%} · "
        f"Macro F1 {aggregate['macro_f1']:.2%}{coverage}"
    )


class ExternalEvaluationDialog(tk.Toplevel):
    def __init__(self, parent, app, experiment):
        experiment_dir = Path(experiment["path"])
        config = load_training_config()
        training_signers = set(get_training_signers(experiment_dir))
        classes = get_experiment_classes(experiment_dir)
        super().__init__(parent)
        self.withdraw()
        self.app = app
        self.experiment_dir = experiment_dir
        self.config = config
        self.training_signers = training_signers
        self.reserved_signers = self.training_signers | set(self.config.collection.signers)
        self.classes = classes
        self.store = DatasetV2Store(ROOT / "dataset_external_v2")
        self.session_choices = external_session_choices(config)
        self.collection_busy = False
        self.form_controls = []
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.future = None
        self.report_dir = None
        self.poll_id = None
        owner = parent.winfo_toplevel()
        self.transient(owner)
        self.title("HandVox — วัดผู้ใช้ใหม่ (ไม่ใช้เทรน)")
        position_x = owner.winfo_rootx() + max(0, (owner.winfo_width() - 1000) // 2)
        position_y = owner.winfo_rooty() + max(0, (owner.winfo_height() - 620) // 2)
        self.geometry(f"1000x720{position_x:+d}{position_y:+d}")
        self.minsize(950, 650)
        self.protocol("WM_DELETE_WINDOW", self.close)
        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=f"โมเดลคงที่: {experiment['id']}",
            font=("Tahoma", 13, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            body,
            text=(
                "ใช้คนใหม่จริงที่ไม่ใช่ "
                + ", ".join(sorted(self.reserved_signers))
                + " · คลิปนี้ใช้วัดผลเท่านั้น ไม่เข้าเทรนหรือเปลี่ยนคะแนนเดิม"
            ),
            wraplength=950,
        ).pack(anchor="w", pady=(8, 12))
        form = ttk.Frame(body)
        form.pack(fill="x")
        signer_number = 3
        while f"person_{signer_number:02d}" in self.reserved_signers:
            signer_number += 1
        self.signer_var = tk.StringVar(value=f"person_{signer_number:02d}")
        self.session_var = tk.StringVar(value=next_additional_session(
            self.store.records(), self.signer_var.get(), self.classes
        ))
        self.gesture_var = tk.StringVar(value=self.classes[0])
        for title, variable, values in (
            ("ผู้ทำท่าใหม่", self.signer_var, None),
            ("รอบถ่าย", self.session_var, self.session_choices),
            ("คำ/คลาส", self.gesture_var, self.classes),
        ):
            ttk.Label(form, text=title).pack(side="left", padx=(0, 6))
            widget = (
                ttk.Entry(form, textvariable=variable, width=15)
                if values is None
                else ttk.Combobox(
                    form, textvariable=variable, values=values, state="readonly", width=17
                )
            )
            widget.pack(side="left", padx=(0, 14))
            self.form_controls.append((widget, "normal" if values is None else "readonly"))
        conditions = ttk.Frame(body)
        conditions.pack(fill="x", pady=(10, 0))
        ttk.Label(conditions, text="แสงขณะถ่าย").pack(side="left", padx=(0, 6))
        self.lighting_var = tk.StringVar(value="unknown")
        lighting = ttk.Combobox(
            conditions, textvariable=self.lighting_var, values=LIGHTING_VALUES,
            state="readonly", width=17,
        )
        lighting.pack(side="left")
        self.form_controls.append((lighting, "readonly"))
        ttk.Label(
            conditions, text="รอบใหม่ = ถ่ายคนละรอบจริง เปลี่ยนเสื้อ/สถานที่/แสงได้",
        ).pack(side="left", padx=14)
        self.progress_var = tk.StringVar()
        ttk.Label(body, textvariable=self.progress_var, wraplength=950).pack(
            anchor="w", pady=(10, 0)
        )
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=12)
        self.capture_button = ttk.Button(actions, text="ถ่ายให้ครบเป้าต่อท่า", command=self.collect)
        self.capture_button.pack(side="left")
        self.extra_capture_button = ttk.Button(
            actions, text="เพิ่มอีก 1 คลิป", command=lambda: self.collect("extra")
        )
        self.extra_capture_button.pack(side="left", padx=6)
        self.next_gesture_button = ttk.Button(
            actions, text="เลือกท่าที่ยังขาด", command=self.select_next_gesture
        )
        self.next_gesture_button.pack(side="left")
        self.evaluate_button = ttk.Button(actions, text="วัดผลโมเดลเดิม", command=self.evaluate)
        self.evaluate_button.pack(side="right")
        self.report_button = ttk.Button(actions, text="เปิดรายงาน", command=self.open_report)
        self.report_button.pack(side="right", padx=6)
        self.report_button.state(["disabled"])
        self.summary_var = tk.StringVar(value="ยังไม่มีผลผู้ใช้ใหม่ — ถ่ายคลิปและตรวจคุณภาพก่อน")
        ttk.Label(body, textvariable=self.summary_var, wraplength=950).pack(anchor="w", pady=(0, 8))
        table_frame = ttk.Frame(body)
        self.tree = ttk.Treeview(
            table_frame, columns=("signer", "session", "class", "quality"), show="headings"
        )
        for column, title in (
            ("signer", "ผู้ทำท่า"), ("session", "รอบถ่าย"),
            ("class", "คำ/คลาส"), ("quality", "สถานะตรวจคลิป"),
        ):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=160)
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        review = ttk.Frame(body)
        ttk.Button(review, text="ดูวิดีโอ", command=self.preview).pack(side="left")
        ttk.Button(review, text="ยอมรับคลิป", command=lambda: self.set_quality("accepted")).pack(side="left", padx=6)
        ttk.Button(review, text="ไม่ใช้คลิป", command=lambda: self.set_quality("rejected")).pack(side="left")
        ttk.Label(
            body, text="neutral = พักมือ · unknown = ท่านอกคำศัพท์",
            wraplength=950,
        ).pack(side="bottom", anchor="w", pady=(12, 0))
        review.pack(side="bottom", fill="x", pady=(10, 0))
        table_frame.pack(fill="both", expand=True)
        self.refresh()
        self.select_next_gesture()
        for variable in (self.signer_var, self.session_var, self.gesture_var):
            variable.trace_add("write", lambda *_: self.update_progress())
        self.load_latest_result()
        self.deiconify()

    def load_latest_result(self):
        reports = sorted((self.experiment_dir / "external_evaluations").glob("*/metrics.json"), reverse=True)
        for report in reports:
            try:
                payload = json.loads(report.read_text(encoding="utf-8"))
                if payload.get("evaluation_scope") != "external_new_signers":
                    continue
                self.summary_var.set(external_result_summary(payload) + f" · {payload.get('created_at', '')}")
                self.report_dir = report.parent
                self.report_button.state(["!disabled"])
                return
            except (OSError, ValueError, KeyError, TypeError):
                continue

    def refresh(self):
        try:
            self.records = {record.clip_id: record for record in self.store.records()}
            self.tree.delete(*self.tree.get_children())
            labels = {"accepted": "ผ่านตรวจ", "pending": "รอตรวจ", "rejected": "ไม่ใช้"}
            for record in self.records.values():
                self.tree.insert("", "end", iid=record.clip_id, values=(
                    record.signer_id, record.session_id, record.gesture_name, labels[record.quality]
                ))
            self.update_progress()
            if not self.collection_busy and (self.future is None or self.future.done()):
                self.evaluate_button.state(
                    ["!disabled"] if any(record.quality == "accepted" for record in self.records.values())
                    else ["disabled"]
                )
        except Exception as error:
            messagebox.showerror("อ่านคลิปไม่สำเร็จ", str(error), parent=self)

    def update_progress(self):
        signer = self.signer_var.get().strip()
        session = self.session_var.get()
        target = external_session_target(self.config, session)
        progress = session_progress(self.records.values(), signer, session, self.classes, target)
        plan = [session_progress(
            self.records.values(), signer, name, self.classes, ADDITIONAL_CLIPS_PER_CLASS
        ) for name in ADDITIONAL_TEST_SESSIONS]
        plan_captured = sum(item["captured"] for item in plan)
        plan_total = sum(item["total"] for item in plan)
        current = progress["counts"][self.gesture_var.get()]
        self.progress_var.set(
            f"{signer} · {session}: ถ่ายแล้ว {progress['captured']}/{progress['total']} คลิป"
            f" · ผ่านตรวจ {progress['accepted']} · ยังขาด {progress['remaining']}\n"
            f"ท่านี้ {current}/{target} คลิป · แผนเพิ่ม session 05–07: "
            f"{plan_captured}/{plan_total} คลิป (ไม่นับคลิปเดิม session 01–04)"
        )
        self.capture_button.configure(text=f"ถ่ายให้ครบ {target} คลิปต่อท่า")
        if not self.collection_busy:
            self.capture_button.state(["disabled"] if current >= target else ["!disabled"])

    def select_next_gesture(self):
        progress = session_progress(
            self.records.values(), self.signer_var.get().strip(), self.session_var.get(),
            self.classes, external_session_target(self.config, self.session_var.get()),
        )
        if progress["next_gesture"] is not None:
            self.gesture_var.set(progress["next_gesture"])
        self.update_progress()

    def collect(self, mode="standard"):
        signer = self.signer_var.get().strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", signer) or signer.casefold() in {
            name.casefold() for name in self.reserved_signers
        }:
            messagebox.showwarning("ผู้ทำท่าไม่ถูกต้อง", "ใช้รหัสคนใหม่จริง เช่น person_03 ห้ามใช้คนในชุดเทรน", parent=self)
            return
        if not messagebox.askyesno(
            "เปิดกล้องเก็บชุดทดสอบใหม่",
            f"เปิดกล้องถ่าย {self.gesture_var.get()} / {signer} / {self.session_var.get()}?\n"
            "ผู้ทำท่าต้องไม่อยู่ในชุดฝึกของโมเดลนี้ คลิปจะเก็บเป็นชุดทดสอบรอตรวจคุณภาพ\n"
            "เริ่มนับถอยหลัง 3 วินาที กด Q เพื่อหยุดได้",
            parent=self,
        ):
            return
        try:
            process = self.app.launcher.launch("collect_v2", (
                "--external-evaluation", "--experiment", str(self.experiment_dir),
                "--signer", signer, "--session", self.session_var.get(),
                "--gesture", self.gesture_var.get(), "--mode", mode,
                "--lighting", self.lighting_var.get(),
            ))
            self.set_busy(True)
            self.poll_id = self.after(500, lambda: self.poll_collection(process))
        except Exception as error:
            messagebox.showerror("เปิดกล้องไม่สำเร็จ", str(error), parent=self)

    def poll_collection(self, process):
        if process.poll() is None:
            self.poll_id = self.after(500, lambda: self.poll_collection(process))
            return
        self.set_busy(False)
        self.refresh()
        if process.returncode:
            messagebox.showerror("เก็บคลิปไม่สำเร็จ", "ตรวจข้อความในหน้าต่างเก็บคลิป แล้วลองใหม่", parent=self)
        else:
            self.select_next_gesture()

    def preview(self):
        selected = self.tree.selection()
        if not selected:
            return
        record = self.records[selected[0]]
        try:
            path = self.store.resolve_data_path(record.preview_file)
            if not record.preview_file or not path.is_file():
                raise ValueError("คลิปนี้ไม่มีวิดีโอตัวอย่าง")
            os.startfile(path)
        except Exception as error:
            messagebox.showerror("เปิดวิดีโอไม่สำเร็จ", str(error), parent=self)

    def set_quality(self, quality):
        selected = self.tree.selection()
        if not selected or self.collection_busy or (self.future is not None and not self.future.done()):
            return
        if quality == "accepted" and not messagebox.askyesno(
            "ยืนยันตรวจคุณภาพ", f"ตรวจวิดีโอและป้ายคำของ {len(selected)} คลิปแล้วใช่ไหม?", parent=self
        ):
            return
        try:
            self.store.set_quality(selected, quality)
            self.refresh()
        except Exception as error:
            messagebox.showerror("ตรวจคลิปไม่สำเร็จ", str(error), parent=self)

    def set_busy(self, busy):
        self.collection_busy = busy
        state = ["disabled"] if busy else ["!disabled"]
        self.capture_button.state(state)
        self.extra_capture_button.state(state)
        self.next_gesture_button.state(state)
        self.evaluate_button.state(state)
        for widget, normal_state in self.form_controls:
            widget.configure(state="disabled" if busy else normal_state)
        if not busy:
            self.update_progress()

    def evaluate(self):
        if not messagebox.askyesno(
            "วัดผู้ใช้ใหม่โดยไม่เทรน", "ใช้เฉพาะคลิปที่ยอมรับแล้วกับโมเดลเดิมที่เลือก\nคะแนนนี้ไม่เปลี่ยนสิทธิ์ติดตั้ง ต้องการวัดผลหรือไม่?", parent=self
        ):
            return
        self.set_busy(True)
        self.summary_var.set("กำลังวัดผลชุดใหม่ โดยไม่ฝึกหรือเปลี่ยนโมเดล...")
        self.future = self.executor.submit(evaluate_external, self.experiment_dir, self.store)
        self.poll_id = self.after(250, self.poll_evaluation)

    def poll_evaluation(self):
        if not self.future.done():
            self.poll_id = self.after(250, self.poll_evaluation)
            return
        self.set_busy(False)
        try:
            self.report_dir, payload = self.future.result()
            self.summary_var.set(external_result_summary(payload))
            self.report_button.state(["!disabled"])
        except Exception as error:
            self.summary_var.set("ยังไม่มีผลใหม่ — แก้ไขข้อมูลตามข้อความแจ้งแล้ววัดอีกครั้ง")
            messagebox.showerror("วัดผู้ใช้ใหม่ไม่สำเร็จ", str(error), parent=self)

    def open_report(self):
        if self.report_dir is not None:
            os.startfile(self.report_dir)

    def close(self):
        if self.poll_id is not None:
            self.after_cancel(self.poll_id)
        self.executor.shutdown(wait=False)
        self.destroy()
