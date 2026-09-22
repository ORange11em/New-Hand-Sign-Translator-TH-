"""หน้าจอหลักทั้งหมดของ HandVox สร้างด้วย Tkinter.

ไฟล์นี้ประกอบด้วยหน้า Dashboard, สร้างประโยค, คำศัพท์,
ตัวช่วยเตรียมเทรน, ตั้งค่า และวิธีใช้ รวมถึงคลาส HandVoxApp ที่เชื่อมทุกหน้า
เข้ากับบริการเสียง การเปิดสคริปต์ และไฟล์ข้อมูลของโปรเจกต์
"""

from __future__ import annotations

import json
import logging
import os
import tkinter as tk
import traceback
import webbrowser
from dataclasses import asdict
from datetime import datetime
from tkinter import messagebox, ttk

from handvox.dataset_v2 import DatasetV2Store
from handvox.diagnostics import DiagnosticItem, run_diagnostics
from handvox.gesture_catalog import (
    PLANNED_STATUSES,
    GestureCatalog,
    PlannedGesture,
)
from handvox.history import HistoryStore
from handvox.paths import LOG_FILE, ROOT
from handvox.processes import ScriptLauncher
from handvox.sentence import SentenceBuilder
from handvox.settings import AppSettings, SettingsStore
from handvox.training_config import (
    build_incremental_training_config,
    build_quick_trial_config,
    incremental_targets,
    load_training_config,
    session_clip_target,
)
from handvox.training_workflow import (
    activate_experiment,
    list_experiments,
    preflight,
    quick_trial_readiness,
)


COLORS = {
    "nav": "#111827",
    "nav_hover": "#1f2937",
    "accent": "#2563eb",
    "accent_hover": "#1d4ed8",
    "background": "#f3f4f6",
    "card": "#ffffff",
    "text": "#111827",
    "muted": "#6b7280",
    "border": "#d1d5db",
    "success": "#15803d",
    "warning": "#b45309",
    "danger": "#b91c1c",
    "info_soft": "#dbeafe",
    "success_soft": "#dcfce7",
    "warning_soft": "#fef3c7",
    "danger_soft": "#fee2e2",
    "neutral_soft": "#e5e7eb",
}


def experiment_failure_summary(experiment):
    if experiment is None:
        return "เลือกผลการทดลองเพื่อดูเงื่อนไขติดตั้ง"
    if experiment.get("passed"):
        return "ผ่านเกณฑ์ของวิธีวัดนี้ · ยังไม่ใช่ผลวัดผู้ใช้ใหม่"
    try:
        directory = experiment["path"]
        metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
        config = json.loads((directory / "training_config.snapshot.json").read_text(encoding="utf-8"))
        acceptance = config["acceptance"]
        critical = set(config.get("critical_gestures", []))
        visible = set(config["visible_gestures"])
        failed_classes = []
        for row in metrics["aggregate"]["per_class"]:
            name = row["class_name"]
            if name not in visible:
                continue
            minimum = acceptance["minimum_class_recall"]
            if name in critical:
                minimum = max(minimum, acceptance["minimum_critical_recall"])
            if row["recall"] < minimum:
                failed_classes.append(f"{name}: Recall {row['recall']:.2%} < {minimum:.0%}")
        if failed_classes:
            return "ผลยังไม่ผ่าน — " + " · ".join(failed_classes) + " · ดูรายละเอียดในรายงาน"
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    return "ผลยังไม่ผ่านเกณฑ์ · เปิดรายงานเพื่อดูรายการที่ต้องปรับ · ติดตั้งได้เฉพาะแบบทดลอง"


# ── เครื่องมือ UI ที่ใช้ร่วมกันทุกหน้า ──────────────────────
def clear_children(widget: tk.Misc) -> None:
    """ลบ widget ลูกทั้งหมดก่อนวาดรายการใหม่จากข้อมูลล่าสุด."""
    for child in widget.winfo_children():
        child.destroy()


def section_card(parent: tk.Misc, padding: int = 18) -> ttk.Frame:
    """สร้างกรอบ card มาตรฐานตามสีและระยะห่างของแอป."""
    return ttk.Frame(parent, style="OutlinedCard.TFrame", padding=padding)


def installed_experiment_id() -> str:
    try:
        manifest = json.loads((ROOT / "model_manifest.json").read_text(encoding="utf-8"))
        return str(manifest.get("experiment_id", ""))
    except (OSError, ValueError, TypeError, AttributeError):
        return ""


def experiment_primary_action(experiment, installed_id="") -> tuple[str, str]:
    if experiment is None:
        return "ติดตั้งโมเดล", "none"
    if installed_id and experiment.get("id") == installed_id:
        return "เปิดกล้องโมเดลนี้", "camera"
    if experiment.get("passed"):
        return "ติดตั้งโมเดล", "install"
    return "ติดตั้งแบบทดลอง", "trial"


def experiment_time_label(value) -> str:
    try:
        return datetime.fromisoformat(str(value)).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return str(value)


class Disclosure(ttk.Frame):
    """Keep secondary controls available without occupying the main workflow."""

    def __init__(self, parent, title, expanded=False):
        super().__init__(parent, style="Card.TFrame")
        self.title = title
        self.expanded = expanded
        self.toggle_button = ttk.Button(
            self, command=lambda: self.set_expanded(not self.expanded)
        )
        self.toggle_button.pack(anchor="w")
        self.body = ttk.Frame(self, style="Card.TFrame", padding=(0, 10, 0, 0))
        self.set_expanded(expanded)

    def set_expanded(self, expanded):
        self.expanded = expanded
        self.toggle_button.configure(text=("− " if expanded else "+ ") + self.title)
        if expanded:
            self.body.pack(fill="both", expand=True)
        else:
            self.body.pack_forget()


def experiment_preserves_active_words(experiment, active_names) -> bool:
    """คืน True เมื่อผลทดลองมีคำในโมเดลปัจจุบันครบและติดตั้งได้โดยคำไม่หาย."""
    try:
        manifest = json.loads(
            (experiment["path"] / "model_manifest.json").read_text(encoding="utf-8")
        )
        experiment_names = {
            str(item["name"]).strip() for item in manifest["visible_gestures"]
        }
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return False
    return set(active_names).issubset(experiment_names)


def training_plan_progress(config, records) -> dict[str, int]:
    """สรุปความครบแบบแยกคำ คน และรอบ เพื่อไม่ให้คลิปรวมสูงหลอกสถานะ."""
    records = tuple(records)
    capture_groups_complete = 0
    capture_groups_total = (
        len(config.all_classes)
        * len(config.collection.signers)
        * len(config.collection.sessions)
    )
    accepted_scopes_complete = 0
    accepted_scopes_total = len(config.all_classes) * len(config.collection.signers)
    for gesture_name in config.all_classes:
        for signer_id in config.collection.signers:
            accepted_total = 0
            accepted_sessions = set()
            for session_id in config.collection.sessions:
                relevant = [
                    record
                    for record in records
                    if record.gesture_name == gesture_name
                    and record.signer_id == signer_id
                    and record.session_id == session_id
                    and record.quality != "rejected"
                ]
                if len(relevant) >= session_clip_target(config, session_id):
                    capture_groups_complete += 1
                accepted = sum(record.quality == "accepted" for record in relevant)
                accepted_total += accepted
                if accepted:
                    accepted_sessions.add(session_id)
            if (
                accepted_total
                >= config.collection.minimum_accepted_per_signer_per_class
                and accepted_sessions.issuperset(config.collection.sessions)
            ):
                accepted_scopes_complete += 1
    return {
        "capture_groups_complete": capture_groups_complete,
        "capture_groups_total": capture_groups_total,
        "accepted_scopes_complete": accepted_scopes_complete,
        "accepted_scopes_total": accepted_scopes_total,
    }


class ScrollableFrame(ttk.Frame):
    """พื้นที่เนื้อหาที่เลื่อนแนวตั้งได้และปรับความกว้างตามหน้าต่าง."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="Page.TFrame")
        self.canvas = tk.Canvas(
            self,
            background=COLORS["background"],
            highlightthickness=0,
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas, style="Page.TFrame")
        self._window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.body.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure(self._window, width=event.width),
        )
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")


class BasePage(ttk.Frame):
    """โครงหัวข้อและคำอธิบายร่วมที่ทุกหน้าในแอปสืบทอด."""

    def __init__(self, parent: tk.Misc, app: "HandVoxApp", title: str, subtitle: str) -> None:
        super().__init__(parent, style="Page.TFrame", padding=(28, 24))
        self.app = app
        ttk.Label(self, text=title, style="Title.TLabel").pack(anchor="w")
        ttk.Label(self, text=subtitle, style="Subtitle.TLabel").pack(anchor="w", pady=(4, 20))

    def refresh(self) -> None:
        pass


# ── หน้า 1: ภาพรวมและตรวจความพร้อม ─────────────────────────
class DashboardPage(BasePage):
    """แสดงจำนวนท่า/คลิปและผล diagnostics โดยไม่เปิดกล้อง."""

    def __init__(self, parent: tk.Misc, app: "HandVoxApp") -> None:
        super().__init__(
            parent,
            app,
            "ภาพรวม",
            "เปิดกล้องเพื่อใช้โมเดลที่ติดตั้งอยู่",
        )

        action_row = ttk.Frame(self, style="Page.TFrame")
        action_row.pack(fill="x", pady=(0, 18))
        ttk.Button(
            action_row,
            text="เริ่มตรวจจับภาษามือ",
            style="Accent.TButton",
            command=app.open_detector,
        ).pack(side="left")
        ttk.Button(action_row, text="ตรวจสอบอีกครั้ง", command=self.refresh).pack(side="right")

        summary = ttk.Frame(self, style="Page.TFrame")
        summary.pack(fill="x", pady=(0, 18))
        for column in range(3):
            summary.columnconfigure(column, weight=1, uniform="summary")
        self.active_var = tk.StringVar(value="-")
        self.planned_var = tk.StringVar(value="-")
        self.dataset_var = tk.StringVar(value="-")
        self._summary_card(summary, 0, "ท่าที่โมเดลรู้จัก", self.active_var)
        self._summary_card(summary, 1, "คำที่รอเพิ่ม", self.planned_var)
        self._summary_card(summary, 2, "คลิปที่เก็บไว้", self.dataset_var)

        card = section_card(self)
        card.pack(fill="x")
        self.system_summary_var = tk.StringVar(value="กำลังตรวจระบบ...")
        ttk.Label(
            card,
            textvariable=self.system_summary_var,
            style="CardTitle.TLabel",
        ).pack(anchor="w", pady=(0, 12))
        self.diagnostics_details = Disclosure(card, "รายละเอียดระบบ")
        self.diagnostics_details.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            self.diagnostics_details.body,
            columns=("status", "name", "detail"),
            show="headings",
            height=7,
        )
        self.tree.heading("status", text="สถานะ")
        self.tree.heading("name", text="รายการ")
        self.tree.heading("detail", text="รายละเอียด")
        self.tree.column("status", width=90, anchor="center", stretch=False)
        self.tree.column("name", width=210, stretch=False)
        self.tree.column("detail", width=600)
        self.tree.tag_configure("ok", foreground=COLORS["success"])
        self.tree.tag_configure("warning", foreground=COLORS["warning"])
        self.tree.tag_configure("error", foreground=COLORS["danger"])
        self.tree.pack(fill="both", expand=True)

    @staticmethod
    def _summary_card(parent: ttk.Frame, column: int, label: str, value: tk.StringVar) -> None:
        card = section_card(parent, padding=16)
        card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 0 if column == 2 else 6))
        ttk.Label(card, text=label, style="CardMuted.TLabel").pack(anchor="w")
        ttk.Label(card, textvariable=value, style="Metric.TLabel").pack(anchor="w", pady=(6, 0))

    def refresh(self) -> None:
        try:
            items = run_diagnostics()
            self.app.active_gestures = self.app.catalog.load_active()
            config = load_training_config()
            active_names = {item.name for item in self.app.active_gestures}
            planned_names = [item.name for item in self.app.catalog.load_planned()]
            waiting = len(
                incremental_targets(config, active_names, planned_names)
            )
            dataset_summary = self.app.dataset_store.summary()
            self.active_var.set(str(len(self.app.active_gestures)))
            self.planned_var.set(str(waiting))
            self.dataset_var.set(str(dataset_summary["clips"]))
            issues = [item for item in items if item.status != "ok"]
            model_detail = next((item.message for item in items if item.name == "โมเดล"), "")
            self.system_summary_var.set(
                f"มี {len(issues)} รายการที่ควรตรวจ" if issues
                else f"พร้อมเปิดกล้อง · {model_detail}"
            )
            if issues:
                self.diagnostics_details.set_expanded(True)
            for row in self.tree.get_children():
                self.tree.delete(row)
            labels = {"ok": "พร้อม", "warning": "ควรดู", "error": "ผิดพลาด"}
            for item in items:
                self._insert_diagnostic(item, labels)
        except Exception as exc:
            self.app.show_error("อ่านสถานะโปรเจกต์ไม่สำเร็จ", exc)

    def _insert_diagnostic(self, item: DiagnosticItem, labels: dict[str, str]) -> None:
        self.tree.insert(
            "",
            "end",
            values=(labels.get(item.status, item.status), item.name, item.message),
            tags=(item.status,),
        )


# ── หน้า 2: สร้างประโยคโดยไม่ใช้กล้อง ─────────────────────
class SentencePage(BasePage):
    """สร้าง แก้ อ่าน คัดลอก และบันทึกประโยคจากคลังคำปัจจุบัน."""

    def __init__(self, parent: tk.Misc, app: "HandVoxApp") -> None:
        super().__init__(
            parent,
            app,
            "สร้างประโยค",
            "ทดลองลำดับคำ พูด และบันทึกประวัติได้โดยไม่ใช้กล้อง",
        )
        self.builder = SentenceBuilder(
            prevent_duplicates=app.settings.prevent_duplicate_words
        )
        self.sentence_var = tk.StringVar(value="ยังไม่มีคำในประโยค")
        self.manual_word = tk.StringVar()

        editor = section_card(self)
        editor.pack(fill="x", pady=(0, 18))
        ttk.Label(editor, text="ประโยคปัจจุบัน", style="CardTitle.TLabel").pack(anchor="w")
        self.sentence_label = ttk.Label(
            editor,
            textvariable=self.sentence_var,
            style="Sentence.TLabel",
            wraplength=850,
        )
        self.sentence_label.pack(anchor="w", fill="x", pady=(10, 14))
        controls = ttk.Frame(editor, style="Card.TFrame")
        controls.pack(fill="x")
        ttk.Entry(controls, textvariable=self.manual_word, width=24).pack(side="left")
        ttk.Button(controls, text="เพิ่มคำ", command=self.add_manual_word).pack(side="left", padx=(8, 18))
        ttk.Button(controls, text="ย้อนคำ", command=self.remove_last).pack(side="left")
        ttk.Button(controls, text="ล้าง", command=self.clear_sentence).pack(side="left", padx=8)
        ttk.Button(controls, text="คัดลอก", command=self.copy_sentence).pack(side="left")
        ttk.Button(controls, text="พูดประโยค", style="Accent.TButton", command=self.speak).pack(side="right")
        ttk.Button(controls, text="บันทึกประวัติ", command=self.save_history).pack(side="right", padx=8)

        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True)
        words_tab = ttk.Frame(tabs, style="Card.TFrame", padding=16)
        history_tab = ttk.Frame(tabs, style="Card.TFrame", padding=16)
        tabs.add(words_tab, text="คลังคำที่ใช้ได้")
        tabs.add(history_tab, text="ประวัติประโยค")

        self.words_frame = ttk.Frame(words_tab, style="Card.TFrame")
        self.words_frame.pack(fill="both", expand=True)

        history_actions = ttk.Frame(history_tab, style="Card.TFrame")
        history_actions.pack(fill="x", pady=(0, 10))
        ttk.Button(history_actions, text="โหลดใหม่", command=self.refresh_history).pack(side="left")
        ttk.Button(history_actions, text="ลบรายการที่เลือก", command=self.delete_history).pack(side="right")
        ttk.Button(history_actions, text="ล้างทั้งหมด", command=self.clear_history).pack(side="right", padx=8)
        self.history_tree = ttk.Treeview(
            history_tab,
            columns=("time", "text", "source"),
            show="headings",
            height=10,
        )
        self.history_tree.heading("time", text="เวลา")
        self.history_tree.heading("text", text="ประโยค")
        self.history_tree.heading("source", text="ที่มา")
        self.history_tree.column("time", width=155, stretch=False)
        self.history_tree.column("text", width=620)
        self.history_tree.column("source", width=120, stretch=False)
        self.history_tree.pack(fill="both", expand=True)
        self.history_tree.bind("<Double-1>", self.use_history_sentence)

    def refresh(self) -> None:
        self.builder.prevent_duplicates = self.app.settings.prevent_duplicate_words
        clear_children(self.words_frame)
        gestures = self.app.catalog.load_active()
        if not gestures:
            ttk.Label(
                self.words_frame,
                text="ยังไม่มีคำที่โมเดลใช้งานได้",
                style="CardMuted.TLabel",
            ).pack(anchor="w")
        else:
            columns = 5
            for column in range(columns):
                self.words_frame.columnconfigure(column, weight=1)
            for index, gesture in enumerate(gestures):
                button = ttk.Button(
                    self.words_frame,
                    text=gesture.name,
                    command=lambda name=gesture.name: self.add_word(name),
                )
                button.grid(
                    row=index // columns,
                    column=index % columns,
                    sticky="ew",
                    padx=5,
                    pady=5,
                )
        self.refresh_history()

    def add_manual_word(self) -> None:
        word = self.manual_word.get().strip()
        if word:
            self.add_word(word)
            self.manual_word.set("")

    def add_word(self, word: str) -> None:
        if not self.builder.add(word):
            self.app.set_status("ไม่ได้เพิ่มคำซ้ำที่อยู่ติดกัน")
        self._update_sentence()

    def remove_last(self) -> None:
        self.builder.remove_last()
        self._update_sentence()

    def clear_sentence(self) -> None:
        self.builder.clear()
        self._update_sentence()

    def _update_sentence(self) -> None:
        self.sentence_var.set(self.builder.text or "ยังไม่มีคำในประโยค")

    def copy_sentence(self) -> None:
        if not self.builder.text:
            return
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(self.builder.text)
        self.app.set_status("คัดลอกประโยคแล้ว")

    def speak(self) -> None:
        if not self.builder.text:
            messagebox.showinfo("ยังไม่มีประโยค", "เพิ่มคำก่อนสั่งให้อ่านประโยค")
            return
        if self.app.speak(self.builder.text):
            if self.app.settings.save_spoken_sentences:
                self._save_history("manual-tts")
            self.app.set_status("ส่งประโยคเข้าคิวเสียงแล้ว")

    def save_history(self) -> None:
        if not self.builder.text:
            messagebox.showinfo("ยังไม่มีประโยค", "เพิ่มคำก่อนบันทึกประวัติ")
            return
        self._save_history("manual")
        self.app.set_status("บันทึกประโยคแล้ว")

    def _save_history(self, source: str) -> None:
        self.app.history_store.add(
            self.builder.text,
            source=source,
            limit=self.app.settings.history_limit,
        )
        self.refresh_history()

    def refresh_history(self) -> None:
        for row in self.history_tree.get_children():
            self.history_tree.delete(row)
        for entry in self.app.history_store.load():
            display_time = entry.created_at
            try:
                display_time = datetime.fromisoformat(entry.created_at).strftime("%d/%m/%Y %H:%M")
            except ValueError:
                pass
            self.history_tree.insert(
                "",
                "end",
                iid=entry.id,
                values=(display_time, entry.text, entry.source),
            )

    def delete_history(self) -> None:
        selected = self.history_tree.selection()
        if selected:
            self.app.history_store.delete(selected[0])
            self.refresh_history()

    def clear_history(self) -> None:
        if messagebox.askyesno("ล้างประวัติ", "ต้องการลบประวัติประโยคทั้งหมดหรือไม่?"):
            self.app.history_store.clear()
            self.refresh_history()

    def use_history_sentence(self, _event: tk.Event) -> None:
        selected = self.history_tree.selection()
        if selected:
            values = self.history_tree.item(selected[0], "values")
            if len(values) >= 2:
                self.builder.replace_from_text(str(values[1]))
                self._update_sentence()


# ── หน้า 3: คำศัพท์ที่ใช้ได้และแผนคำใหม่ ───────────────────
class GesturesPage(BasePage):
    """แสดงคลังคำเดียว แยกเพียงคำที่ใช้ได้แล้วกับคำที่รอเพิ่ม."""

    def __init__(self, parent: tk.Misc, app: "HandVoxApp") -> None:
        super().__init__(
            parent,
            app,
            "คำศัพท์ภาษามือ",
            "เพิ่มคำได้ต่อเนื่อง โดยคำเดิมยังอยู่และคำใหม่เข้าคิวเทรนทีละคำ",
        )
        self.editing_id: str | None = None
        self.plan_items = {}
        tabs = ttk.Notebook(self)
        self.tabs = tabs
        tabs.pack(fill="both", expand=True)
        active_tab = ttk.Frame(tabs, style="Card.TFrame", padding=16)
        planned_tab = ttk.Frame(tabs, style="Card.TFrame", padding=16)
        tabs.add(active_tab, text="คำที่เทรนแล้ว")
        tabs.add(planned_tab, text="คำที่รอเพิ่ม")

        ttk.Label(
            active_tab,
            text=(
                "รายการนี้อ่านจากโมเดลที่ติดตั้งอยู่จริง · "
                "สีเขียว: อยู่ในโมเดลและใช้กับกล้องได้ · "
                "สีน้ำเงิน: พร้อมติดตั้ง · สีส้ม: ต้องเทรนใหม่จากโมเดลล่าสุด"
            ),
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(0, 10))
        self.trained_summary_var = tk.StringVar(value="กำลังโหลดผลการเทรน...")
        trained_summary = ttk.Frame(active_tab, style="Card.TFrame")
        trained_summary.pack(fill="x", pady=(0, 10))
        ttk.Label(
            trained_summary,
            textvariable=self.trained_summary_var,
            style="CardTitle.TLabel",
        ).pack(side="left")
        ttk.Button(
            trained_summary,
            text="เปิดผลการเทรน",
            command=self.go_to_training_results,
        ).pack(side="right")
        ttk.Button(
            trained_summary,
            text="+ เพิ่มท่าใหม่",
            style="Accent.TButton",
            command=self.begin_new_gesture,
        ).pack(side="right", padx=(0, 8))
        active_list = ttk.Frame(active_tab, style="Card.TFrame")
        active_list.pack(fill="both", expand=True)
        active_list.columnconfigure(0, weight=1)
        active_list.rowconfigure(0, weight=1)
        self.active_tree = ttk.Treeview(
            active_list,
            columns=("name", "status", "description"),
            show="headings",
        )
        self.active_tree.heading("name", text="คำ")
        self.active_tree.heading("status", text="สถานะ")
        self.active_tree.heading("description", text="คำอธิบาย")
        self.active_tree.column("name", width=170, stretch=False)
        self.active_tree.column("status", width=185, stretch=False)
        self.active_tree.column("description", width=500)
        self.active_tree.grid(row=0, column=0, sticky="nsew")
        active_scroll = ttk.Scrollbar(
            active_list, orient="vertical", command=self.active_tree.yview
        )
        active_scroll.grid(row=0, column=1, sticky="ns")
        self.active_tree.configure(yscrollcommand=active_scroll.set)
        self.active_tree.tag_configure("active", foreground=COLORS["success"])
        self.active_tree.tag_configure("trained_pending", foreground=COLORS["accent"])
        self.active_tree.tag_configure("stale_experiment", foreground=COLORS["warning"])

        planned_tab.columnconfigure(0, weight=3)
        planned_tab.columnconfigure(1, weight=2)
        planned_tab.rowconfigure(1, weight=1)
        ttk.Label(
            planned_tab,
            text=(
                "หน้านี้แสดงเฉพาะคำที่ยังไม่อยู่ในโมเดล · เลือกเก็บข้อมูลและ"
                "เทรนเพิ่มได้ทีละคำ โดยคำที่ติดตั้งแล้วอยู่ในแท็บแรก"
            ),
            style="CardMuted.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self.plan_summary_var = tk.StringVar(value="กำลังโหลดแผนคำศัพท์...")
        ttk.Label(
            planned_tab,
            textvariable=self.plan_summary_var,
            style="CardTitle.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        plan_list = ttk.Frame(planned_tab, style="Card.TFrame")
        plan_list.grid(row=1, column=0, sticky="nsew", padx=(0, 16))
        plan_list.columnconfigure(0, weight=1)
        plan_list.rowconfigure(0, weight=1)
        self.planned_tree = ttk.Treeview(
            plan_list,
            columns=("name", "status"),
            show="headings",
        )
        for column, title, width in (
            ("name", "คำที่รอเพิ่ม", 145),
            ("status", "สถานะ", 170),
        ):
            self.planned_tree.heading(column, text=title)
            self.planned_tree.column(column, width=width, stretch=True)
        self.planned_tree.grid(row=0, column=0, sticky="nsew")
        plan_scroll = ttk.Scrollbar(
            plan_list, orient="vertical", command=self.planned_tree.yview
        )
        plan_scroll.grid(row=0, column=1, sticky="ns")
        self.planned_tree.configure(yscrollcommand=plan_scroll.set)
        self.planned_tree.bind("<<TreeviewSelect>>", self._load_selected)
        self.planned_tree.tag_configure("active", foreground=COLORS["success"])
        self.planned_tree.tag_configure("planned", foreground=COLORS["warning"])
        self.planned_tree.tag_configure("missing", foreground=COLORS["danger"])
        self.planned_tree.tag_configure("trained_pending", foreground=COLORS["accent"])
        self.planned_tree.tag_configure("stale_experiment", foreground=COLORS["warning"])

        editor = ttk.Frame(planned_tab, style="Card.TFrame")
        editor.grid(row=1, column=1, sticky="nsew")
        editor.columnconfigure(1, weight=1)
        self.form_vars = {
            "id": tk.StringVar(),
            "name": tk.StringVar(),
            "category": tk.StringVar(),
            "priority": tk.StringVar(value="1"),
            "status": tk.StringVar(value="planned"),
            "reference_url": tk.StringVar(),
        }
        self.form_widgets = {}
        labels = (
            ("id", "รหัสอังกฤษ"),
            ("name", "คำภาษาไทย"),
            ("category", "หมวด"),
            ("priority", "ลำดับ 1–5"),
            ("status", "สถานะ"),
            ("reference_url", "ลิงก์อ้างอิง"),
        )
        for row, (key, label) in enumerate(labels):
            ttk.Label(editor, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=5)
            if key == "status":
                widget = ttk.Combobox(
                    editor,
                    textvariable=self.form_vars[key],
                    values=PLANNED_STATUSES,
                    state="readonly",
                )
            elif key == "priority":
                widget = ttk.Spinbox(editor, textvariable=self.form_vars[key], from_=1, to=5)
            else:
                widget = ttk.Entry(editor, textvariable=self.form_vars[key])
            widget.grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=5)
            self.form_widgets[key] = widget

        ttk.Label(editor, text="หมายเหตุ", style="Card.TLabel").grid(row=6, column=0, sticky="nw", pady=5)
        self.notes = tk.Text(editor, height=5, wrap="word", relief="solid", borderwidth=1)
        self.notes.grid(row=6, column=1, sticky="nsew", padx=(10, 0), pady=5)
        editor.rowconfigure(6, weight=1)
        buttons = ttk.Frame(editor, style="Card.TFrame")
        buttons.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(
            buttons,
            text="+ เพิ่มท่าใหม่",
            command=self.begin_new_gesture,
        ).pack(side="left")
        self.reference_button = ttk.Button(
            buttons, text="เปิดอ้างอิง", command=self.open_reference
        )
        self.reference_button.pack(side="left", padx=8)
        self.delete_button = ttk.Button(buttons, text="ลบ", command=self.delete_selected)
        self.delete_button.pack(side="right")
        self.save_button = ttk.Button(
            buttons, text="บันทึก", style="Accent.TButton", command=self.save_form
        )
        self.save_button.pack(side="right", padx=8)

    def refresh(self) -> None:
        for row in self.active_tree.get_children():
            self.active_tree.delete(row)
        active_gestures = self.app.catalog.load_active()
        active_names = {gesture.name for gesture in active_gestures}
        for index, gesture in enumerate(active_gestures):
            self.active_tree.insert(
                "",
                "end",
                iid=f"active_{index}",
                values=(gesture.name, "ใช้งานได้แล้ว", gesture.description),
                tags=("active",),
            )
        pending_experiments = {}
        for experiment in list_experiments():
            target = experiment.get("target_gesture", "")
            if (
                experiment["passed"]
                and target
                and target not in active_names
                and target not in pending_experiments
            ):
                pending_experiments[target] = experiment
        for index, (target, experiment) in enumerate(pending_experiments.items()):
            compatible = experiment_preserves_active_words(
                experiment, active_names
            )
            self.active_tree.insert(
                "",
                "end",
                iid=f"pending_{index}",
                values=(
                    target,
                    (
                        "เทรนเสร็จ · พร้อมติดตั้ง"
                        if compatible
                        else "ผลเก่า · ต้องเทรนใหม่"
                    ),
                    f"Accuracy {experiment['accuracy']:.4f} · Macro F1 {experiment['macro_f1']:.4f}",
                ),
                tags=("trained_pending" if compatible else "stale_experiment",),
            )
        ready_count = sum(
            experiment_preserves_active_words(item, active_names)
            for item in pending_experiments.values()
        )
        stale_count = len(pending_experiments) - ready_count
        self.trained_summary_var.set(
            f"ใช้งานกับกล้องได้ {len(active_gestures)} คำ"
            + (f" · พร้อมติดตั้ง {ready_count} คำ" if ready_count else "")
            + (f" · ต้องเทรนใหม่ {stale_count} คำ" if stale_count else "")
            + (" · ไม่มีผลค้างติดตั้ง" if not pending_experiments else "")
        )
        for row in self.planned_tree.get_children():
            self.planned_tree.delete(row)
        config = load_training_config()
        all_items = self.app.catalog.load_plan_view(config.visible_gestures)
        waiting_items = [item for item in all_items if item.row_type != "active"]
        self.plan_items = {item.key: item for item in waiting_items}
        for item in waiting_items:
            pending_experiment = (
                pending_experiments.get(item.name)
                if item.row_type in {"planned", "missing"}
                else None
            )
            compatible = bool(
                pending_experiment
                and experiment_preserves_active_words(
                    pending_experiment, active_names
                )
            )
            if compatible:
                status = "เทรนเสร็จ · พร้อมติดตั้ง"
                tag = "trained_pending"
            elif pending_experiment:
                status = "ผลเก่า · ต้องเทรนใหม่"
                tag = "stale_experiment"
            else:
                status = item.status
                tag = item.row_type
            self.planned_tree.insert(
                "",
                "end",
                iid=item.key,
                values=(
                    item.name,
                    status,
                ),
                tags=(tag,),
            )
        active_count = len(active_gestures)
        waiting_count = len(waiting_items)
        self.tabs.tab(0, text=f"ใช้งานในกล้อง ({len(active_gestures)})")
        self.tabs.tab(
            1,
            text=f"คำที่รอเพิ่ม ({waiting_count})",
        )
        self.plan_summary_var.set(
            f"รอเพิ่มทั้งหมด {waiting_count} คำ · ใช้งานในกล้องแล้ว {active_count} คำ"
            + (f" · พร้อมติดตั้ง {ready_count}" if ready_count else "")
            + (f" · ต้องเทรนใหม่ {stale_count}" if stale_count else "")
        )

    def show_planned(self) -> None:
        self.tabs.select(1)

    def show_active(self, gesture_name: str = "") -> None:
        """เปิดรายการคำในโมเดลและเลือกคำที่เพิ่งติดตั้งให้เห็นทันที."""
        self.tabs.select(0)
        self.refresh()
        if not gesture_name:
            return
        for row_id in self.active_tree.get_children():
            values = self.active_tree.item(row_id, "values")
            if values and values[0] == gesture_name:
                self.active_tree.selection_set(row_id)
                self.active_tree.see(row_id)
                break

    def go_to_training_results(self) -> None:
        """พาไปขั้นอ่านผลเพื่อจัดการผลที่พร้อมติดตั้งหรือควรเทรนใหม่."""
        self.app.show_page("training")
        page = self.app.pages.get("training")
        if isinstance(page, TrainingPage):
            page.show_step(4)

    def _set_form_mode(self, editable: bool, deletable: bool = False) -> None:
        """ล็อกฟอร์มของคำในโมเดล และเปิดฟอร์มของคำที่ยังวางแผนได้."""
        for key, widget in self.form_widgets.items():
            if editable:
                widget.configure(state="readonly" if key == "status" else "normal")
            else:
                widget.configure(state="disabled")
        self.notes.configure(state="normal" if editable else "disabled")
        self.save_button.state(["!disabled"] if editable else ["disabled"])
        self.delete_button.state(["!disabled"] if deletable else ["disabled"])
        self.reference_button.state(["!disabled"] if editable else ["disabled"])

    def _reset_form(self) -> None:
        self._set_form_mode(True, deletable=False)
        self.editing_id = None
        for key, variable in self.form_vars.items():
            variable.set("1" if key == "priority" else "planned" if key == "status" else "")
        self.notes.delete("1.0", "end")

    def new_form(self) -> None:
        self._reset_form()
        self.planned_tree.selection_remove(self.planned_tree.selection())

    def begin_new_gesture(self) -> None:
        """เปิดฟอร์มคำใหม่ ซึ่งจะเข้ารายการรอเพิ่มโดยยังไม่แก้โมเดล."""
        self.tabs.select(1)
        self.new_form()
        self.form_vars["priority"].set("5")
        self.notes.insert(
            "1.0",
            "คำใหม่ — ตรวจรูปแบบและลิงก์อ้างอิงก่อนเก็บข้อมูล",
        )
        self.form_widgets["name"].focus_set()
        self.app.set_status(
            "กรอกข้อมูลท่าใหม่แล้วกดบันทึก — ท่านี้จะเข้ารายการรอเพิ่มและยังไม่เปลี่ยนโมเดล"
        )

    def _load_selected(self, _event: tk.Event | None = None) -> None:
        selected = self.planned_tree.selection()
        if not selected:
            return
        row = self.plan_items.get(selected[0])
        if row is None:
            return
        self._reset_form()
        if row.row_type == "active":
            active = next(
                (item for item in self.app.catalog.load_active() if item.name == row.name),
                None,
            )
            self.form_vars["id"].set("อยู่ในโมเดล")
            self.form_vars["name"].set(row.name)
            self.form_vars["category"].set(row.category)
            self.form_vars["priority"].set("—")
            self.form_vars["status"].set("trained")
            self.notes.insert(
                "1.0",
                active.description if active else "คำนี้ใช้งานได้ในโมเดลปัจจุบันแล้ว",
            )
            self._set_form_mode(False)
            return
        if row.row_type == "missing":
            self.form_vars["name"].set(row.name)
            self.form_vars["category"].set("รอเพิ่มข้อมูล")
            self.notes.insert("1.0", "เพิ่มรายละเอียดและลิงก์อ้างอิงก่อนเก็บข้อมูล")
            return
        gesture = next(
            (
                item
                for item in self.app.catalog.load_planned()
                if item.id == row.planned_id
            ),
            None,
        )
        if gesture is None:
            return
        self.editing_id = gesture.id
        values = asdict(gesture)
        for key, variable in self.form_vars.items():
            variable.set(str(values[key]))
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", gesture.notes)
        self._set_form_mode(True, deletable=True)

    def save_form(self) -> None:
        try:
            entered_id = self.form_vars["id"].get().strip().lower()
            if self.editing_id is not None and entered_id != self.editing_id:
                raise ValueError(
                    "ไม่สามารถเปลี่ยนรหัสของรายการเดิมได้ หากต้องการรหัสใหม่ให้สร้างรายการใหม่"
                )
            gesture = PlannedGesture(
                id=entered_id,
                name=self.form_vars["name"].get().strip(),
                category=self.form_vars["category"].get().strip(),
                priority=int(self.form_vars["priority"].get()),
                status=self.form_vars["status"].get().strip(),
                reference_url=self.form_vars["reference_url"].get().strip(),
                notes=self.notes.get("1.0", "end").strip(),
            )
            self.app.catalog.upsert_planned(gesture)
            self.refresh()
            row_id = next(
                (
                    item.key
                    for item in self.plan_items.values()
                    if item.planned_id == gesture.id
                ),
                "",
            )
            if row_id:
                self.planned_tree.selection_set(row_id)
                self.planned_tree.see(row_id)
            self.editing_id = gesture.id
            training_page = self.app.pages.get("training")
            if isinstance(training_page, TrainingPage):
                training_page.select_target(gesture.name)
                try:
                    training_page.refresh()
                except Exception:
                    logging.exception("รีเฟรชหน้าเตรียมเทรนหลังเพิ่มคำไม่สำเร็จ")
            self.app.set_status(
                f"บันทึกแผนคำว่า {gesture.name} แล้ว และเลือกไว้ในหน้าเตรียมเทรน"
            )
        except Exception as exc:
            self.app.show_error("บันทึกคำศัพท์ไม่สำเร็จ", exc)

    def delete_selected(self) -> None:
        selected = self.planned_tree.selection()
        if not selected:
            return
        row = self.plan_items.get(selected[0])
        if row is None or not row.planned_id:
            messagebox.showinfo(
                "ลบจากแผนไม่ได้",
                "คำที่อยู่ในโมเดลต้องคงอยู่ในคลังคำเพื่อป้องกันคำหาย",
            )
            return
        name = self.planned_tree.item(selected[0], "values")[0]
        if messagebox.askyesno("ลบคำศัพท์", f"ลบคำว่า {name} ออกจากแผนหรือไม่?"):
            self.app.catalog.delete_planned(row.planned_id)
            self.refresh()
            self.new_form()
            training_page = self.app.pages.get("training")
            if isinstance(training_page, TrainingPage):
                try:
                    training_page.refresh()
                except Exception:
                    logging.exception("รีเฟรชหน้าเตรียมเทรนหลังลบคำไม่สำเร็จ")

    def open_reference(self) -> None:
        url = self.form_vars["reference_url"].get().strip()
        if not url:
            messagebox.showinfo("ยังไม่มีลิงก์", "เพิ่มลิงก์อ้างอิงก่อน")
            return
        if not url.startswith(("https://", "http://")):
            messagebox.showerror("ลิงก์ไม่ถูกต้อง", "ลิงก์ต้องเริ่มด้วย https:// หรือ http://")
            return
        webbrowser.open(url)


class TrainingPage(BasePage):
    """นำผู้ใช้ยืนยันคำ เก็บ/ตรวจคลิป เทรน และอ่านผลตามลำดับ."""

    STEP_TITLES = (
        "1  ยืนยันท่า",
        "2  เก็บข้อมูล",
        "3  ตรวจคลิป",
        "4  เทรนและวัดผล",
        "5  อ่านผล",
    )
    QUALITY_FILTERS = {
        "รอตรวจ": "pending",
        "ผ่านแล้ว": "accepted",
        "ไม่ผ่าน": "rejected",
        "ทั้งหมด": "all",
    }

    def __init__(self, parent: tk.Misc, app: "HandVoxApp") -> None:
        super().__init__(
            parent,
            app,
            "เตรียมเทรน",
            "ข้อมูลฝึกแยกจากชุดวัดผู้ใช้ใหม่",
        )
        self.base_config = load_training_config()
        active_names = [item.name for item in app.catalog.load_active()]
        planned_names = [item.name for item in app.catalog.load_planned()]
        available_targets = incremental_targets(
            self.base_config,
            active_names,
            planned_names,
        )
        self.target_var = tk.StringVar(
            value=available_targets[0] if available_targets else ""
        )
        self.target_summary_var = tk.StringVar(value="กำลังเตรียมขอบเขตรอบนี้...")
        self.model_status_var = tk.StringVar(value="กำลังตรวจโมเดลที่ติดตั้ง...")
        self.quick_summary_var = tk.StringVar(value="กำลังตรวจโหมดทดลองด่วน...")
        self.config = (
            build_incremental_training_config(
                self.target_var.get(),
                self.base_config,
                active_names,
                planned_names,
            )
            if self.target_var.get()
            else self.base_config
        )
        self.signer_var = tk.StringVar(value=self.config.collection.signers[0])
        self.session_var = tk.StringVar(value=self.config.collection.sessions[0])
        self.gesture_var = tk.StringVar(
            value=self.target_var.get() or self.config.all_classes[0]
        )
        self.lighting_var = tk.StringVar(value="normal")
        self.quality_filter_var = tk.StringVar(value="รอตรวจ")
        self.collection_progress_var = tk.DoubleVar(value=0)
        self.collection_summary_var = tk.StringVar(value="ยังไม่มีข้อมูลในชุดนี้")
        self.collection_plan_var = tk.StringVar(value="กำลังอ่านแผนเก็บข้อมูล...")
        self.session_guide_var = tk.StringVar(value="")
        self.scope_summary_var = tk.StringVar(value="กำลังตรวจรายการท่า...")
        self.readiness_summary_var = tk.StringVar(value="กำลังตรวจความพร้อม...")
        self.quality_stat_vars = {
            "accepted": tk.StringVar(value="0"),
            "pending": tk.StringVar(value="0"),
            "rejected": tk.StringVar(value="0"),
        }
        self._last_report = None
        self._last_experiments = []
        self._build_tabs()


    def _build_tabs(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        self.scope_tab = ttk.Frame(self.notebook, style="Card.TFrame", padding=14)
        self.collection_tab = ttk.Frame(self.notebook, style="Card.TFrame", padding=14)
        self.quality_tab = ttk.Frame(self.notebook, style="Card.TFrame", padding=14)
        self.readiness_tab = ttk.Frame(self.notebook, style="Card.TFrame", padding=14)
        self.experiments_tab = ttk.Frame(self.notebook, style="Card.TFrame", padding=14)
        for page, title in zip(
            (
                self.scope_tab,
                self.collection_tab,
                self.quality_tab,
                self.readiness_tab,
                self.experiments_tab,
            ),
            self.STEP_TITLES,
        ):
            self.notebook.add(page, text=title)
        self._build_scope_tab()
        self._build_collection_tab()
        self._build_quality_tab()
        self._build_readiness_tab()
        self._build_experiments_tab()

    def _build_scope_tab(self) -> None:
        round_box = tk.Frame(
            self.scope_tab,
            background=COLORS["info_soft"],
            highlightbackground="#93c5fd",
            highlightthickness=1,
        )
        round_box.pack(fill="x", pady=(0, 12))
        tk.Label(
            round_box,
            text="สถานะโมเดลปัจจุบัน",
            font=("Leelawadee UI", 10, "bold"),
            foreground=COLORS["accent"],
            background=COLORS["info_soft"],
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(9, 4))
        tk.Label(
            round_box,
            textvariable=self.model_status_var,
            font=("Leelawadee UI", 10, "bold"),
            foreground=COLORS["success"],
            background=COLORS["info_soft"],
            justify="left",
            anchor="w",
            wraplength=690,
        ).grid(row=0, column=1, columnspan=2, sticky="ew", padx=(8, 12), pady=(9, 4))
        tk.Label(
            round_box,
            text="คำใหม่ที่จะเพิ่ม",
            font=("Leelawadee UI", 9, "bold"),
            foreground=COLORS["text"],
            background=COLORS["info_soft"],
        ).grid(row=1, column=0, sticky="w", padx=12, pady=4)
        self.target_combo = ttk.Combobox(
            round_box,
            textvariable=self.target_var,
            state="readonly",
            width=24,
        )
        self.target_combo.grid(row=1, column=1, sticky="w", padx=(8, 12), pady=4)
        self.target_combo.bind("<<ComboboxSelected>>", self._on_target_changed)
        tk.Label(
            round_box,
            textvariable=self.target_summary_var,
            font=("Leelawadee UI", 9),
            foreground=COLORS["text"],
            background=COLORS["info_soft"],
            justify="left",
            anchor="w",
            wraplength=610,
        ).grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=(2, 9))
        round_box.columnconfigure(2, weight=1)

        header = ttk.Frame(self.scope_tab, style="Card.TFrame")
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="ตรวจให้ทั้งสองคนทำท่าตรงกันก่อนเก็บข้อมูล", style="CardTitle.TLabel").pack(side="left")
        ttk.Button(
            header,
            text="เปิดแผนคำศัพท์",
            style="Accent.TButton",
            command=self.go_to_gesture_plan,
        ).pack(side="right")
        ttk.Label(
            self.scope_tab,
            textvariable=self.scope_summary_var,
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(0, 10))
        self.scope_tree = ttk.Treeview(
            self.scope_tab,
            columns=("gesture", "type", "reference", "status"),
            show="headings",
            height=10,
        )
        for column, title, width in (
            ("gesture", "คำศัพท์", 165),
            ("type", "ที่มา", 150),
            ("reference", "แหล่งอ้างอิง", 180),
            ("status", "ความพร้อม", 350),
        ):
            self.scope_tree.heading(column, text=title)
            self.scope_tree.column(column, width=width, stretch=column == "status")
        self.scope_tree.tag_configure("ok", foreground=COLORS["success"])
        self.scope_tree.tag_configure("warning", foreground=COLORS["warning"])
        scope_scroll = ttk.Scrollbar(
            self.scope_tab, orient="vertical", command=self.scope_tree.yview
        )
        self.scope_tree.configure(yscrollcommand=scope_scroll.set)
        scope_scroll.pack(side="right", fill="y")
        self.scope_tree.pack(side="left", fill="both", expand=True)
        self.scope_tree.bind("<Double-1>", lambda _event: self.go_to_gesture_plan())

    def _build_collection_tab(self) -> None:
        info = tk.Frame(self.collection_tab, background=COLORS["info_soft"])
        info.pack(fill="x", pady=(0, 12))
        tk.Label(
            info,
            textvariable=self.collection_plan_var,
            font=("Leelawadee UI", 10, "bold"),
            foreground=COLORS["accent"],
            background=COLORS["info_soft"],
            anchor="w",
            padx=12,
            pady=9,
        ).pack(fill="x")
        body = ttk.Frame(self.collection_tab, style="Card.TFrame")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        form = section_card(body, 14)
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        form.columnconfigure(1, weight=1)
        fields = (
            ("ผู้ทำท่า", self.signer_var, self.config.collection.signers),
            ("รอบเก็บข้อมูล", self.session_var, self.config.collection.sessions),
            # รายการเก็บข้อมูลแสดงคำในโมเดล + คำใหม่ + neutral + unknown
            # เพื่อให้เพิ่มคำต่อเนื่องโดยไม่ทำคำเดิมหาย
            ("ท่าที่จะถ่ายในคลิปนี้", self.gesture_var, self.config.all_classes),
            ("สภาพแสง", self.lighting_var, ("normal", "bright", "dim", "backlit", "unknown")),
        )
        self.collection_combos = []
        for row, (label, variable, values) in enumerate(fields):
            ttk.Label(form, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=7)
            combo = ttk.Combobox(
                form,
                textvariable=variable,
                values=values,
                state="readonly",
                width=29,
            )
            combo.grid(row=row, column=1, sticky="ew", padx=(14, 0), pady=7)
            combo.bind("<<ComboboxSelected>>", lambda _event: self.update_collection_summary())
            self.collection_combos.append(combo)
        capture_actions = ttk.Frame(form, style="OutlinedCard.TFrame")
        capture_actions.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        capture_actions.columnconfigure((0, 1), weight=1)
        ttk.Button(
            capture_actions,
            text="เปิดกล้องถ่ายให้ครบชุด",
            style="Accent.TButton",
            command=lambda: self.start_collection("standard"),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(
            capture_actions,
            text="ถ่ายเพิ่ม 1 คลิป",
            command=lambda: self.start_collection("extra"),
        ).grid(row=0, column=1, sticky="ew", padx=(5, 0))

        ttk.Label(
            form,
            text="เลือก neutral เมื่อต้องการพักมือ หรือ unknown สำหรับท่านอกคำศัพท์",
            style="CardMuted.TLabel",
            wraplength=450,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(12, 0))

        status = section_card(body, 14)
        status.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ttk.Label(status, text="ชุดที่เลือก", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            status,
            textvariable=self.collection_summary_var,
            style="Card.TLabel",
            wraplength=300,
            justify="left",
        ).pack(anchor="w", fill="x", pady=(12, 8))
        ttk.Progressbar(
            status,
            variable=self.collection_progress_var,
            maximum=100,
            style="Training.Horizontal.TProgressbar",
        ).pack(fill="x", pady=(0, 14))
        ttk.Label(
            status,
            textvariable=self.session_guide_var,
            style="CardMuted.TLabel",
            justify="left",
            wraplength=300,
        ).pack(anchor="w")

    def _build_quality_tab(self) -> None:
        stats = ttk.Frame(self.quality_tab, style="Card.TFrame")
        stats.pack(fill="x", pady=(0, 10))
        for key, title in (("pending", "รอตรวจ"), ("accepted", "ยอมรับแล้ว"), ("rejected", "ไม่ใช้")):
            ttk.Label(stats, text=title, style="CardMuted.TLabel").pack(side="left", padx=(0, 6))
            ttk.Label(stats, textvariable=self.quality_stat_vars[key], style="Card.TLabel").pack(
                side="left", padx=(0, 24)
            )
        ttk.Button(stats, text="เปิดโฟลเดอร์ข้อมูล", command=self.open_dataset_folder).pack(side="right")

        actions = ttk.Frame(self.quality_tab, style="Card.TFrame")
        actions.pack(fill="x", pady=(0, 10))
        ttk.Label(actions, text="แสดง:", style="Card.TLabel").pack(side="left")
        filter_combo = ttk.Combobox(
            actions,
            textvariable=self.quality_filter_var,
            values=tuple(self.QUALITY_FILTERS),
            state="readonly",
            width=13,
        )
        filter_combo.pack(side="left", padx=(7, 14))
        filter_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_quality())
        ttk.Button(actions, text="เปิดวิดีโอ", command=self.open_preview).pack(side="left")
        ttk.Button(
            actions,
            text="ถ่ายแทน",
            command=self.retake_selected_clip,
        ).pack(side="left", padx=8)
        ttk.Button(
            actions,
            text="ไม่ผ่าน",
            style="Danger.TButton",
            command=lambda: self.set_selected_quality("rejected"),
        ).pack(side="right")
        ttk.Button(
            actions,
            text="ยอมรับ",
            style="Success.TButton",
            command=lambda: self.set_selected_quality("accepted"),
        ).pack(side="right", padx=8)
        ttk.Button(
            actions,
            text="รอตรวจ",
            style="Muted.TButton",
            command=lambda: self.set_selected_quality("pending"),
        ).pack(side="right")
        self.quality_tree = ttk.Treeview(
            self.quality_tab,
            columns=("gesture", "signer", "session", "mode", "quality", "time", "preview"),
            show="headings",
            selectmode="extended",
            height=9,
        )
        for column, title, width in (
            ("gesture", "คำ/คลาส", 145),
            ("signer", "ผู้ทำท่า", 100),
            ("session", "รอบ", 100),
            ("mode", "ประเภทคลิป", 100),
            ("quality", "สถานะ", 90),
            ("time", "วันเวลา", 210),
            ("preview", "วิดีโอ", 80),
        ):
            self.quality_tree.heading(column, text=title)
            self.quality_tree.column(column, width=width, stretch=column == "time")
        self.quality_tree.tag_configure("accepted", foreground=COLORS["success"])
        self.quality_tree.tag_configure("pending", foreground=COLORS["warning"])
        self.quality_tree.tag_configure("rejected", foreground=COLORS["danger"])
        quality_scroll = ttk.Scrollbar(
            self.quality_tab, orient="vertical", command=self.quality_tree.yview
        )
        self.quality_tree.configure(yscrollcommand=quality_scroll.set)
        quality_scroll.pack(side="right", fill="y")
        self.quality_tree.pack(side="left", fill="both", expand=True)
        self.quality_tree.bind("<Double-1>", lambda _event: self.open_preview())

    def _build_readiness_tab(self) -> None:
        advanced = Disclosure(self.readiness_tab, "ตัวเลือกขั้นสูง: เทรนด่วน")
        advanced.pack(fill="x", pady=(0, 10))
        quick_box = tk.Frame(
            advanced.body,
            background=COLORS["warning_soft"],
            highlightbackground="#f59e0b",
            highlightthickness=1,
        )
        quick_box.pack(fill="x", pady=(0, 10))
        tk.Label(
            quick_box,
            text="โหมดด่วน: ทดลอง 1 ท่าก่อนข้อมูลมาตรฐานครบ",
            font=("Leelawadee UI", 11, "bold"),
            foreground=COLORS["warning"],
            background=COLORS["warning_soft"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(9, 2))
        tk.Label(
            quick_box,
            textvariable=self.quick_summary_var,
            font=("Leelawadee UI", 9),
            foreground=COLORS["text"],
            background=COLORS["warning_soft"],
            justify="left",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 9))
        self.quick_train_button = ttk.Button(
            quick_box,
            text="เทรนด่วนจากคำใหม่",
            style="Accent.TButton",
            command=self.start_quick_training,
        )
        self.quick_train_button.grid(row=0, column=1, rowspan=2, padx=12, pady=10)
        quick_box.columnconfigure(0, weight=1)
        self.readiness_banner = tk.Frame(self.readiness_tab, background=COLORS["danger_soft"])
        self.readiness_banner.pack(fill="x", pady=(0, 10))
        self.readiness_label = tk.Label(
            self.readiness_banner,
            textvariable=self.readiness_summary_var,
            font=("Leelawadee UI", 10, "bold"),
            foreground=COLORS["danger"],
            background=COLORS["danger_soft"],
            anchor="w",
            padx=12,
            pady=9,
        )
        self.readiness_label.pack(side="left", fill="x", expand=True)
        actions = ttk.Frame(self.readiness_tab, style="Card.TFrame")
        actions.pack(fill="x", pady=(0, 10))
        ttk.Button(actions, text="ตรวจอีกครั้ง", command=self.refresh).pack(side="left")
        self.train_button = ttk.Button(
            actions,
            text="เริ่มเทรนและสร้างรายงาน",
            style="Success.TButton",
            command=self.start_training,
        )
        self.train_button.pack(side="right")
        self.readiness_tree = ttk.Treeview(
            self.readiness_tab,
            columns=("status", "message"),
            show="headings",
            height=10,
        )
        self.readiness_tree.heading("status", text="ผลตรวจ")
        self.readiness_tree.heading("message", text="สิ่งที่ต้องทำ")
        self.readiness_tree.column("status", width=95, anchor="center", stretch=False)
        self.readiness_tree.column("message", width=760)
        self.readiness_tree.tag_configure("ok", foreground=COLORS["success"])
        self.readiness_tree.tag_configure("warning", foreground=COLORS["warning"])
        self.readiness_tree.tag_configure("error", foreground=COLORS["danger"])
        readiness_scroll = ttk.Scrollbar(
            self.readiness_tab, orient="vertical", command=self.readiness_tree.yview
        )
        self.readiness_tree.configure(yscrollcommand=readiness_scroll.set)
        readiness_scroll.pack(side="right", fill="y")
        self.readiness_tree.pack(side="left", fill="both", expand=True)

    def _build_experiments_tab(self) -> None:
        actions = ttk.Frame(self.experiments_tab, style="Card.TFrame")
        actions.pack(fill="x", pady=(0, 12))
        self.open_report_button = ttk.Button(
            actions, text="เปิดรายงาน", command=self.open_experiment_report
        )
        self.open_report_button.pack(side="left")
        self.external_evaluation_button = ttk.Button(
            actions, text="วัดผู้ใช้ใหม่", command=self.open_external_evaluation
        )
        self.external_evaluation_button.pack(side="left", padx=8)
        self.activate_button = ttk.Button(
            actions, text="ติดตั้งโมเดล", style="Accent.TButton", command=self.activate_selected
        )
        self.activate_button.pack(side="right")
        for button in (self.open_report_button, self.external_evaluation_button, self.activate_button):
            button.state(["disabled"])
        self.experiment_detail_var = tk.StringVar(value="เลือกผลการทดลอง")
        ttk.Label(
            self.experiments_tab, textvariable=self.experiment_detail_var,
            style="CardMuted.TLabel", wraplength=880,
        ).pack(fill="x", pady=(0, 12))
        self.experiment_tree = ttk.Treeview(
            self.experiments_tab,
            columns=("created", "target", "mode", "accuracy", "f1", "passed"),
            show="headings", height=12,
        )
        for column, title, width in (
            ("created", "วันที่เทรน", 160),
            ("target", "คำที่เพิ่ม", 95),
            ("mode", "วิธีวัด", 155),
            ("accuracy", "Accuracy", 105),
            ("f1", "Macro F1", 105),
            ("passed", "สถานะ", 195),
        ):
            self.experiment_tree.heading(column, text=title)
            self.experiment_tree.column(column, width=width, stretch=column == "passed")
        self.experiment_tree.tag_configure("passed", foreground=COLORS["success"])
        self.experiment_tree.tag_configure("failed", foreground=COLORS["danger"])
        self.experiment_tree.tag_configure("installed", foreground=COLORS["accent"])
        scrollbar = ttk.Scrollbar(
            self.experiments_tab, orient="vertical", command=self.experiment_tree.yview
        )
        self.experiment_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.experiment_tree.pack(side="left", fill="both", expand=True)
        self.experiment_tree.bind("<<TreeviewSelect>>", self._update_experiment_actions)

    def show_step(self, index: int) -> None:
        self.notebook.select(index)

    def go_to_gesture_plan(self) -> None:
        self.app.show_page("gestures")
        page = self.app.pages.get("gestures")
        if isinstance(page, GesturesPage):
            page.show_planned()


    def _session_target(self, session_id: str) -> int:
        return session_clip_target(self.config, session_id)

    def _refresh_collection_plan_text(self) -> None:
        """อธิบายจำนวนคลิปและเป้าหมายแต่ละรอบจาก config จริง ไม่ใช้เลขฝังใน UI."""
        sessions = self.config.collection.sessions
        targets = [self._session_target(session) for session in sessions]
        if len(set(targets)) == 1:
            target_text = f"รอบละ {targets[0]} คลิป"
        else:
            target_text = "แต่ละรอบ " + ", ".join(
                f"{session}={target}" for session, target in zip(sessions, targets)
            )
        self.collection_plan_var.set(
            f"เลือกคน รอบ และคำให้ตรงก่อนถ่าย · {target_text} รวม {len(sessions)} รอบ "
            "· ถ่ายเพิ่มหรือถ่ายแทนคลิปเดิมได้โดยข้อมูลไม่หาย"
        )
        suggestions = (
            "ตำแหน่งและแสงปกติ",
            "เปลี่ยนเสื้อหรือพื้นหลัง",
            "เปลี่ยนระยะหรือมุมกล้อง",
            "เปลี่ยนสภาพแสง",
        )
        guide_lines = [
            f"{session}: {suggestions[index] if index < len(suggestions) else 'เปลี่ยนสภาพแวดล้อม'}"
            for index, session in enumerate(sessions)
        ]
        self.session_guide_var.set(
            "\n".join(guide_lines)
            + "\n\nคลิปใหม่จะเป็น pending จนกว่าจะตรวจวิดีโอ"
        )

    def update_collection_summary(self) -> None:
        records = self.app.dataset_store.records()
        selected = [
            item
            for item in records
            if item.gesture_name == self.gesture_var.get()
            and item.signer_id == self.signer_var.get()
            and item.session_id == self.session_var.get()
            and item.quality != "rejected"
        ]
        accepted = sum(item.quality == "accepted" for item in selected)
        pending = sum(item.quality == "pending" for item in selected)
        target = self._session_target(self.session_var.get())
        usable = accepted + pending
        self.collection_progress_var.set(min(100, usable / max(target, 1) * 100))
        remaining = max(0, target - usable)
        if remaining:
            status = f"เหลือเก็บอีก {remaining} คลิป"
        elif usable > target:
            status = f"ครบเป้าหมายแล้ว · มีคลิปเสริม {usable - target} คลิป"
        elif pending:
            status = "เก็บครบชุดแล้ว · ไปตรวจคลิปที่ยังรอตรวจ"
        else:
            status = "เก็บและตรวจผ่านครบชุดนี้แล้ว"
        self.collection_summary_var.set(
            f"{self.gesture_var.get()} · {self.signer_var.get()} · {self.session_var.get()}\n"
            f"มี {usable}/{target} คลิป (ผ่าน {accepted}, รอตรวจ {pending})\n"
            + status
        )

    def _active_names(self) -> tuple[str, ...]:
        """คืนชื่อคำที่โมเดลติดตั้งอยู่ในขณะนี้."""
        return tuple(item.name for item in self.app.catalog.load_active())

    def _planned_names(self) -> tuple[str, ...]:
        """คืนชื่อคำที่ผู้ใช้บันทึกไว้และยังเลือกเพิ่มเข้าโมเดลได้."""
        return tuple(item.name for item in self.app.catalog.load_planned())

    def select_target(self, gesture_name: str) -> None:
        """เลือกคำที่เพิ่งบันทึกไว้ล่วงหน้า เพื่อให้เปิดหน้าเทรนแล้วเห็นทันที."""
        self.target_var.set(str(gesture_name).strip())

    def _reload_round_config(self) -> None:
        """สร้าง config รอบปัจจุบันจากคำเดิมและคำเป้าหมายหนึ่งคำ."""
        self.base_config = load_training_config()
        active_names = self._active_names()
        planned_names = self._planned_names()
        targets = incremental_targets(
            self.base_config,
            active_names,
            planned_names,
        )
        self.target_combo.configure(
            values=targets,
            state="readonly" if targets else "disabled",
        )
        target = self.target_var.get()
        if target not in targets:
            target = targets[0] if targets else ""
            self.target_var.set(target)
        self.config = (
            build_incremental_training_config(
                target,
                self.base_config,
                active_names,
                planned_names,
            )
            if target
            else self.base_config
        )
        collection_order = (
            (target,) + tuple(
                name for name in self.config.all_classes if name != target
            )
            if target
            else self.config.all_classes
        )
        self.collection_combos[0].configure(values=self.config.collection.signers)
        self.collection_combos[1].configure(values=self.config.collection.sessions)
        self.collection_combos[2].configure(values=collection_order)
        if hasattr(self, "collection_plan_var"):
            self._refresh_collection_plan_text()
        if self.gesture_var.get() not in self.config.all_classes:
            self.gesture_var.set(target or self.config.all_classes[0])
        new_clip_count = (
            len(self.config.collection.signers)
            * self.config.collection.target_clips_per_signer_per_class
        )
        if target:
            self.model_status_var.set(
                f"ใช้กับกล้องได้ {len(active_names)} คำ · "
                f"กำลังเตรียมเพิ่ม “{target}” · รอเพิ่มทั้งหมด {len(targets)} คำ"
            )
            self.target_summary_var.set(
                f"รอบนี้เพิ่ม “{target}” · เทรนรวม {len(self.config.visible_gestures)} คำ "
                "+ Neutral + Unknown "
                f"· เป้าหมายสะสม {self.config.expected_clip_count} คลิป\n"
                f"หลังมีข้อมูลฐานแล้ว รอบถัดไปเก็บเพิ่มเฉพาะคำใหม่ประมาณ {new_clip_count} คลิป"
            )
        else:
            self.model_status_var.set(
                f"ใช้กับกล้องได้ {len(active_names)} คำ · ไม่มีคำสูญหาย"
            )
            self.target_summary_var.set(
                "ไม่มีคำที่รอเพิ่ม ช่องเลือกจึงถูกปิด · "
                "กด + เพิ่มท่าใหม่จากหน้าคำศัพท์ได้ทุกเมื่อ"
            )

    def _on_target_changed(self, _event=None) -> None:
        """เปลี่ยนขอบเขตรอบโดยไม่ลบคลิปหรือเริ่มเทรน."""
        self.gesture_var.set(self.target_var.get())
        self._reload_round_config()
        self.refresh()
        self.show_step(0)

    def refresh(self) -> None:
        self._reload_round_config()
        records = self.app.dataset_store.records()
        report = preflight(self.config, self.app.dataset_store)
        quick_config = build_quick_trial_config(
            self.target_var.get(),
            self.base_config,
            self._active_names(),
            self._planned_names(),
        ) if self.target_var.get() else None
        quick_report = (
            quick_trial_readiness(quick_config, self.app.dataset_store)
            if quick_config
            else None
        )
        all_experiments = list_experiments()
        experiments = [
            item for item in all_experiments
            if item.get("target_gesture") == self.target_var.get()
        ]
        self._last_report = report
        self._last_experiments = experiments
        scope_ready_count = self._refresh_scope()
        self._refresh_quality(records)
        self._refresh_readiness(report)
        self._refresh_quick_readiness(quick_report)
        self._refresh_experiments(all_experiments)
        self.update_collection_summary()
        self._refresh_workflow_summary(scope_ready_count, records, report, experiments)

    def _refresh_scope(self) -> int:
        active_order = tuple(item.name for item in self.app.catalog.load_active())
        active_names = set(active_order)
        planned = {item.name: item for item in self.app.catalog.load_planned()}
        ready_count = 0
        for row in self.scope_tree.get_children():
            self.scope_tree.delete(row)
        round_names = set(self.config.visible_gestures)
        display_names = tuple(self.base_config.visible_gestures) + tuple(
            name
            for name in (
                *active_order,
                *self.config.visible_gestures,
                *self._planned_names(),
            )
            if name not in self.base_config.visible_gestures
        )
        display_names = tuple(dict.fromkeys(display_names))
        for name in display_names:
            if name in active_names:
                ready = True
                source = "โมเดลปัจจุบัน"
                reference = "—"
                status = "ใช้งานกับกล้องได้แล้ว"
            elif name not in round_names:
                ready = False
                source = "รอเพิ่ม"
                reference = "—"
                status = "เลือกเป็นคำเป้าหมายได้ในรอบถัดไป"
            else:
                item = planned.get(name)
                has_reference = bool(item and item.reference_url)
                verified = bool(item and item.status in {"verified", "collected", "trained"})
                ready = has_reference and verified
                source = "คำใหม่"
                reference = "มีลิงก์" if has_reference else "ยังไม่มีลิงก์"
                if not has_reference:
                    status = "เพิ่มแหล่งอ้างอิงก่อน"
                elif not verified:
                    status = "ตรวจรูปแบบแล้วเปลี่ยนเป็น verified"
                else:
                    status = "พร้อมเก็บข้อมูล"
            if name in round_names:
                ready_count += int(ready)
            self.scope_tree.insert(
                "",
                "end",
                values=(name, source, reference, status),
                tags=("ok" if ready else "warning",),
            )
        remaining = len(self.config.visible_gestures) - ready_count
        waiting_count = sum(
            name not in round_names
            for name in incremental_targets(
                self.base_config,
                active_names,
                self._planned_names(),
            )
        )
        if self.target_var.get():
            self.scope_summary_var.set(
                f"รอบ “{self.target_var.get()}” พร้อม {ready_count}/{len(self.config.visible_gestures)} คำ"
                + (
                    " — ยืนยันแหล่งอ้างอิงของคำเป้าหมายก่อน"
                    if remaining
                    else " — รูปแบบท่ารอบนี้ครบแล้ว"
                )
                + f" · คำอื่นที่รอเพิ่ม {waiting_count}"
            )
        else:
            self.scope_summary_var.set(
                f"โมเดลปัจจุบันใช้งานได้ {len(active_names)} คำ · "
                f"คำที่รอเพิ่ม {waiting_count} คำ"
            )
        return ready_count

    def _refresh_quality(self, records=None) -> None:
        records = records if records is not None else self.app.dataset_store.records()
        # ให้หน้าตรวจคุณภาพเห็นคลิปของทั้งแผน แม้คลิปนั้นจะเก็บล่วงหน้าไว้
        # สำหรับคำที่ยังไม่ถูกเลือกเป็นเป้าหมายของรอบเทรนปัจจุบัน
        known_names = set(self.base_config.all_classes).union(
            self._active_names(),
            self._planned_names(),
        )
        records = [item for item in records if item.gesture_name in known_names]
        counts = {
            quality: sum(item.quality == quality for item in records)
            for quality in ("accepted", "pending", "rejected")
        }
        for key, variable in self.quality_stat_vars.items():
            variable.set(str(counts[key]))
        wanted = self.QUALITY_FILTERS[self.quality_filter_var.get()]
        for row in self.quality_tree.get_children():
            self.quality_tree.delete(row)
        superseded_ids = {
            item.supersedes_clip_id for item in records if item.supersedes_clip_id
        }
        for record in reversed(records):
            if wanted != "all" and record.quality != wanted:
                continue
            self.quality_tree.insert(
                "",
                "end",
                iid=record.clip_id,
                values=(
                    record.gesture_name,
                    record.signer_id,
                    record.session_id,
                    (
                        "ถูกแทนแล้ว"
                        if record.clip_id in superseded_ids
                        else {
                            "standard": "ชุดหลัก",
                            "extra": "ถ่ายเพิ่ม",
                            "retake": "ถ่ายใหม่",
                        }.get(record.capture_mode, record.capture_mode)
                    ),
                    record.quality,
                    experiment_time_label(record.recorded_at),
                    "มี" if record.preview_file else "ไม่มี",
                ),
                tags=(record.quality,),
            )

    def _refresh_readiness(self, report) -> None:
        error_count = sum(item.status == "error" for item in report.items)
        warning_count = sum(item.status == "warning" for item in report.items)
        if report.ready:
            soft, strong = COLORS["success_soft"], COLORS["success"]
            message = f"พร้อมเทรน — accepted {report.accepted_clips}/{report.expected_target_clips} คลิป"
            self.train_button.state(["!disabled"])
            self.train_button.configure(text="เริ่มเทรนและสร้างรายงาน")
        else:
            soft, strong = COLORS["danger_soft"], COLORS["danger"]
            message = f"ยังเริ่มไม่ได้ — ต้องแก้ {error_count} รายการ และมีคำเตือน {warning_count} รายการ"
            self.train_button.state(["disabled"])
            self.train_button.configure(text="ยังเทรนไม่ได้ — แก้รายการสีแดงก่อน")
        self.readiness_banner.configure(background=soft)
        self.readiness_label.configure(background=soft, foreground=strong)
        self.readiness_summary_var.set(message)
        for row in self.readiness_tree.get_children():
            self.readiness_tree.delete(row)
        labels = {"ok": "พร้อม", "warning": "ควรตรวจ", "error": "ต้องแก้"}
        ordered = sorted(report.items, key=lambda item: {"error": 0, "warning": 1, "ok": 2}.get(item.status, 3))
        for item in ordered:
            self.readiness_tree.insert(
                "",
                "end",
                values=(labels.get(item.status, item.status), item.message),
                tags=(item.status,),
            )

    def _refresh_quick_readiness(self, report) -> None:
        """แสดงความพร้อมของโหมดด่วนแยกจากเกณฑ์มาตรฐาน."""
        if report is None:
            self.quick_summary_var.set("เพิ่มคำครบตามแผนแล้ว")
            self.quick_train_button.state(["disabled"])
            return
        target_clips = sum(
            item.gesture_name == self.target_var.get() and item.quality == "accepted"
            for item in self.app.dataset_store.records()
        )
        if report.ready:
            self.quick_summary_var.set(
                f"พร้อม: มีคลิป accepted ของ “{self.target_var.get()}” {target_clips} คลิป "
                "จากอย่างน้อย 2 กลุ่มผู้ทำท่า+รอบ · ข้อมูลคำเดิมใช้ฝึกเท่านั้น "
                "ผลวัดนี้เป็นผลเบื้องต้น"
            )
            self.quick_train_button.state(["!disabled"])
        else:
            errors = [item.message for item in report.items if item.status == "error"]
            detail = " · ".join(errors[:2]) if errors else "ข้อมูลยังไม่ผ่านเงื่อนไข"
            self.quick_summary_var.set(
                f"ยังไม่พร้อม (accepted คำใหม่ {target_clips} คลิป): {detail}"
            )
            self.quick_train_button.state(["disabled"])

    def _refresh_experiments(self, experiments=None) -> None:
        experiments = experiments if experiments is not None else list_experiments()
        self._last_experiments = experiments
        selected = self.experiment_tree.selection()
        installed_id = installed_experiment_id()
        for row in self.experiment_tree.get_children():
            self.experiment_tree.delete(row)
        for item in experiments:
            installed = item["id"] == installed_id
            status = "ผ่านเกณฑ์" if item["passed"] else "ไม่ผ่าน"
            if installed:
                status = "ใช้งานอยู่" if item["passed"] else "ใช้งานอยู่ (ทดลอง)"
            mode = "ด่วน" if item.get("mode") == "quick_trial" else {
                "known_signers_session_holdout": "คนเดิม / แยกรอบ",
                "leave_one_signer_out": "ข้ามคน",
            }.get(item.get("evaluation_strategy"), "มาตรฐาน")
            self.experiment_tree.insert(
                "", "end", iid=item["id"],
                values=(
                    experiment_time_label(item["created_at"]),
                    item.get("target_gesture") or "แผนรวม", mode,
                    f"{item['accuracy']:.2%}", f"{item['macro_f1']:.2%}", status,
                ),
                tags=("installed" if installed else "passed" if item["passed"] else "failed",),
            )
        available_ids = {item["id"] for item in experiments}
        if experiments:
            selection = selected[0] if selected and selected[0] in available_ids else (
                installed_id if installed_id in available_ids else experiments[0]["id"]
            )
            self.experiment_tree.selection_set(selection)
        self._update_experiment_actions()

    def _update_experiment_actions(self, _event=None) -> None:
        item = self._selected_experiment()
        self.experiment_detail_var.set(experiment_failure_summary(item))
        title, action = experiment_primary_action(item, installed_experiment_id())
        self.activate_button.configure(text=title)
        state = ["disabled"] if action == "none" else ["!disabled"]
        for button in (self.open_report_button, self.external_evaluation_button, self.activate_button):
            button.state(state)

    def open_dataset_folder(self) -> None:
        try:
            self.app.dataset_store.initialize()
            os.startfile(self.app.dataset_store.root)
        except Exception as error:
            self.app.show_error("เปิดโฟลเดอร์ข้อมูลไม่สำเร็จ", error)

    def open_external_evaluation(self) -> None:
        item = self._selected_experiment()
        if item is None:
            return
        try:
            from handvox.external_evaluation_ui import ExternalEvaluationDialog

            ExternalEvaluationDialog(self, self.app, item)
        except Exception as error:
            messagebox.showerror("เปิดหน้าวัดผู้ใช้ใหม่ไม่สำเร็จ", str(error), parent=self)

    def _refresh_workflow_summary(self, scope_ready_count, records, report, experiments) -> None:
        progress = training_plan_progress(self.config, records)
        scope_complete = scope_ready_count == len(self.config.visible_gestures)
        collection_complete = (
            progress["capture_groups_complete"]
            == progress["capture_groups_total"]
        )
        quality_complete = (
            progress["accepted_scopes_complete"]
            == progress["accepted_scopes_total"]
        )
        has_experiment = bool(experiments)
        latest_passed = bool(experiments and experiments[0]["passed"])
        stage_states = [
            "complete" if scope_complete else "current",
            "complete" if collection_complete else ("current" if scope_complete else "upcoming"),
            "complete" if quality_complete else ("current" if collection_complete else "upcoming"),
            "complete" if has_experiment else ("current" if report.ready else "upcoming"),
            "complete" if latest_passed else ("review" if has_experiment else "upcoming"),
        ]
        details = (
            f"{scope_ready_count}/{len(self.config.visible_gestures)} พร้อม",
            f"{progress['capture_groups_complete']}/{progress['capture_groups_total']} ชุดครบ",
            f"{progress['accepted_scopes_complete']}/{progress['accepted_scopes_total']} คน×คลาสผ่าน",
            "มีผลแล้ว" if has_experiment else ("พร้อมเริ่ม" if report.ready else "รอข้อมูล"),
            "ผ่านเกณฑ์" if latest_passed else ("ต้องปรับ" if has_experiment else "ยังไม่มีผล"),
        )
        for index, (state, detail) in enumerate(zip(stage_states, details)):
            self._set_step_state(index, state, detail)

    def _set_step_state(self, index: int, state: str, detail: str) -> None:
        suffix = " ✓" if state == "complete" else ""
        self.notebook.tab(index, text=self.STEP_TITLES[index] + suffix)


    def start_collection(self, mode: str = "standard") -> None:
        mode_labels = {
            "standard": "ถ่ายเฉพาะจำนวนที่ยังขาดให้ครบชุด",
            "extra": "ถ่ายข้อมูลเสริมเพิ่ม 1 คลิป แม้ชุดนี้ครบแล้ว",
        }
        if mode not in mode_labels:
            raise ValueError(f"โหมดเก็บข้อมูลไม่ถูกต้อง: {mode}")
        if not messagebox.askyesno(
            "ยืนยันการเปิดกล้อง",
            f"ผู้ทำท่า: {self.signer_var.get()}\n"
            f"รอบ: {self.session_var.get()}\n"
            f"คำ/คลาส: {self.gesture_var.get()}\n\n"
            f"{mode_labels[mode]}\nต้องการเปิดกล้องหรือไม่?",
        ):
            return
        arguments = (
            "--signer", self.signer_var.get(),
            "--session", self.session_var.get(),
            "--gesture", self.gesture_var.get(),
            "--lighting", self.lighting_var.get(),
            "--mode", mode,
        )
        try:
            process = self.app.launcher.launch("collect_v2", arguments)
            self.app.set_status("กำลังเก็บ Dataset V2 — หน้านี้จะอัปเดตเมื่อปิดกล้อง")
            self.after(500, lambda: self._poll_collection(process))
        except Exception as exc:
            self.app.show_error("เปิดเครื่องมือเก็บข้อมูลไม่สำเร็จ", exc)

    def retake_selected_clip(self) -> None:
        """เปิดกล้องถ่ายหนึ่งคลิปแทนรายการที่เลือก โดยไม่ลบหลักฐานเดิม."""
        selected = self.quality_tree.selection()
        if len(selected) != 1:
            messagebox.showinfo("เลือกหนึ่งคลิป", "กรุณาเลือกคลิปที่ต้องการถ่ายใหม่ 1 รายการ")
            return
        clip_id = selected[0]
        records = self.app.dataset_store.records()
        record = next((item for item in records if item.clip_id == clip_id), None)
        if record is None:
            messagebox.showwarning("ไม่พบคลิป", "รายการนี้อาจถูกเปลี่ยนแปลง กรุณากดตรวจอีกครั้ง")
            return
        replacement = next(
            (item for item in records if item.supersedes_clip_id == record.clip_id),
            None,
        )
        if replacement is not None:
            messagebox.showinfo(
                "คลิปนี้ถูกแทนแล้ว",
                "เลือกคลิปล่าสุดที่อยู่ในคอลัมน์ ‘ประเภทคลิป: ถ่ายใหม่’ "
                "หากต้องการถ่ายซ้ำอีกครั้ง",
            )
            return
        if not messagebox.askyesno(
            "ถ่ายคลิปนี้ใหม่",
            f"คำ/คลาส: {record.gesture_name}\nผู้ทำท่า: {record.signer_id}\n"
            f"รอบ: {record.session_id}\n\n"
            "คลิปเดิมจะถูกเก็บไว้และทำเครื่องหมายว่าไม่ใช้เทรนเมื่อถ่ายคลิปใหม่สำเร็จ",
        ):
            return
        arguments = (
            "--signer", record.signer_id,
            "--session", record.session_id,
            "--gesture", record.gesture_name,
            "--lighting", record.lighting,
            "--mode", "retake",
            "--retake-clip", record.clip_id,
        )
        try:
            process = self.app.launcher.launch("collect_v2", arguments)
            self.app.set_status("กำลังถ่ายคลิปใหม่ — คลิปเดิมจะเปลี่ยนสถานะเมื่อบันทึกสำเร็จ")
            self.after(500, lambda: self._poll_collection(process))
        except Exception as exc:
            self.app.show_error("เปิดการถ่ายใหม่ไม่สำเร็จ", exc)

    def _poll_collection(self, process) -> None:
        """รีเฟรชจำนวนคลิปอัตโนมัติเมื่อหน้าต่างเก็บข้อมูลปิด."""
        if process.poll() is None:
            self.after(500, lambda: self._poll_collection(process))
            return
        self.refresh()
        if process.returncode == 0:
            self.app.set_status("เก็บข้อมูลเสร็จแล้ว — ตรวจวิดีโอในขั้นที่ 3")
        else:
            self.app.set_status("การเก็บข้อมูลหยุดก่อนเสร็จ — ตรวจหน้าต่างผลการทำงาน")

    def start_training(self) -> None:
        report = preflight(self.config, self.app.dataset_store)
        if not report.ready:
            messagebox.showwarning("ข้อมูลยังไม่พร้อม", "เปิดขั้นที่ 4 และแก้รายการสีแดงให้หมดก่อน")
            self.show_step(3)
            return
        if not messagebox.askyesno(
            "เริ่มเทรนและวัดผล",
            f"รอบนี้เพิ่มคำ: {self.target_var.get()}\n"
            f"ระบบจะเทรนใหม่รวม {len(self.config.visible_gestures)} คำเดิมและใหม่ "
            "แล้วกัน session ของผู้ใช้ทั้งสองคนไว้วัดผล\n"
            "ถ้าผลผ่าน ระบบจะสำรองโมเดลเดิม ติดตั้งผล และอัปเดตทุกหน้าให้อัตโนมัติ\n"
            "ต้องการดำเนินการต่อหรือไม่?",
        ):
            return
        try:
            target = self.target_var.get()
            process = self.app.launcher.launch(
                "train_v2", ("train", "--target", self.target_var.get())
            )
            self._set_training_busy(True, quick_mode=False)
            self.app.set_status(f"กำลังเทรนคำว่า {target} — UI จะอัปเดตทันทีเมื่อเสร็จ")
            self.after(
                500,
                lambda: self._poll_training(process, target, quick_mode=False),
            )
        except Exception as exc:
            self.app.show_error("เริ่มเทรนไม่สำเร็จ", exc)

    def start_quick_training(self) -> None:
        """เริ่มเทรนจากข้อมูลฐานเดิมและคลิปคำใหม่ โดยไม่รอชุดมาตรฐานครบ."""
        target = self.target_var.get()
        config = build_quick_trial_config(
            target,
            self.base_config,
            self._active_names(),
            self._planned_names(),
        )
        report = quick_trial_readiness(config, self.app.dataset_store)
        if not report.ready:
            errors = [item.message for item in report.items if item.status == "error"]
            messagebox.showwarning(
                "ข้อมูลโหมดด่วนยังไม่พร้อม",
                "\n".join(errors[:4]) if errors else "ข้อมูลยังไม่ผ่านเงื่อนไข",
            )
            self.show_step(2)
            return
        if not messagebox.askyesno(
            "เริ่มเทรนทดลองด่วน",
            f"ระบบจะเพิ่ม “{target}” โดยใช้ข้อมูลฐานคำเดิมเป็นชุดฝึก "
            "และกันกลุ่มคำใหม่ไว้ประเมิน\n"
            "ถ้าผลผ่าน ระบบจะสำรองโมเดลเดิม ติดตั้ง และแสดงคำใหม่ทันที "
            "แต่คะแนนเป็นเพียงผลเบื้องต้น ไม่ใช้เป็นผลวิจัยมาตรฐาน\n\n"
            "ต้องการเริ่มเทรนหรือไม่?",
        ):
            return
        try:
            process = self.app.launcher.launch(
                "train_v2", ("quick-train", "--target", target)
            )
            self._set_training_busy(True, quick_mode=True)
            self.app.set_status(
                f"กำลังเทรนทดลองด่วนคำว่า {target} — UI จะอัปเดตทันทีเมื่อเสร็จ"
            )
            self.after(
                500,
                lambda: self._poll_training(process, target, quick_mode=True),
            )
        except Exception as exc:
            self.app.show_error("เริ่มเทรนทดลองด่วนไม่สำเร็จ", exc)

    def _set_training_busy(self, busy: bool, quick_mode: bool) -> None:
        """ป้องกันการกดเทรนซ้ำและบอกสถานะบนปุ่มระหว่าง process ทำงาน."""
        if quick_mode:
            self.quick_train_button.configure(
                text="กำลังเทรน..." if busy else "เทรนด่วนจากคำใหม่"
            )
            self.quick_train_button.state(["disabled"] if busy else ["!disabled"])
        else:
            self.train_button.configure(
                text="กำลังเทรนและวัดผล..." if busy else "เริ่มเทรนและสร้างรายงาน"
            )
            self.train_button.state(["disabled"] if busy else ["!disabled"])

    def _poll_training(self, process, target: str, quick_mode: bool) -> None:
        """รอ process แบบไม่ค้าง GUI แล้วติดตั้งผลที่ผ่านและรีเฟรชทุกหน้า."""
        return_code = process.poll()
        if return_code is None:
            self.after(
                500,
                lambda: self._poll_training(process, target, quick_mode),
            )
            return
        self._set_training_busy(False, quick_mode)
        expected_mode = "quick_trial" if quick_mode else "standard"
        experiments = list_experiments(target_gesture=target)
        latest = next(
            (item for item in experiments if item.get("mode") == expected_mode),
            None,
        )
        if return_code == 0 and latest is not None:
            self._last_experiments = experiments
            self._refresh_experiments(experiments)
            self.show_step(4)
            self.experiment_tree.selection_set(latest["id"])
            self.experiment_tree.see(latest["id"])
            self._update_experiment_actions()
            if latest["passed"]:
                try:
                    backup = activate_experiment(
                        latest["path"], allow_quick_trial=quick_mode
                    )
                    self.app.reload_model_state()
                    self.app.show_page("gestures")
                    gestures_page = self.app.pages.get("gestures")
                    if isinstance(gestures_page, GesturesPage):
                        gestures_page.show_active(target)
                    self.app.set_status(
                        f"เทรนและติดตั้งคำว่า {target} แล้ว — ทุกหน้าอัปเดตเรียบร้อย"
                    )
                    messagebox.showinfo(
                        "เทรนและอัปเดต UI เสร็จแล้ว",
                        f"เพิ่มคำว่า “{target}” ในโมเดลและคลังคำแล้ว\n"
                        f"สำรองโมเดลเดิมไว้ที่\n{backup}",
                    )
                except Exception as exc:
                    self.app.show_error(
                        "เทรนเสร็จแต่ติดตั้งโมเดลไม่สำเร็จ",
                        exc,
                    )
            else:
                self.app.set_status(
                    f"เทรนคำว่า {target} เสร็จแล้ว แต่ผลยังไม่ผ่าน จึงยังไม่เปลี่ยนโมเดล"
                )
                messagebox.showwarning(
                    "ผลเทรนยังไม่ผ่าน",
                    "สร้างรายงานแล้ว แต่ยังไม่ติดตั้งคำใหม่เพื่อป้องกันโมเดลที่คุณภาพต่ำ",
                )
        else:
            self.refresh()
            self.show_step(4)
            self.app.set_status("เทรนไม่สำเร็จ — ตรวจหน้าต่างผลการทำงาน")

    def set_selected_quality(self, quality: str) -> None:
        selected = self.quality_tree.selection()
        if not selected:
            messagebox.showinfo("ยังไม่ได้เลือกคลิป", "เลือกอย่างน้อยหนึ่งรายการในตารางก่อน")
            return
        try:
            updated = self.app.dataset_store.set_quality(selected, quality)
            self.app.set_status(f"ปรับ {updated} คลิปเป็น {quality} แล้ว")
            self.refresh()
            self.show_step(2)
        except Exception as exc:
            self.app.show_error("ปรับสถานะคลิปไม่สำเร็จ", exc)

    def open_preview(self) -> None:
        selected = self.quality_tree.selection()
        if len(selected) != 1:
            messagebox.showinfo("เลือกหนึ่งคลิป", "กรุณาเลือกคลิปหนึ่งรายการเพื่อเปิดวิดีโอ")
            return
        record = next(
            (item for item in self.app.dataset_store.records() if item.clip_id == selected[0]),
            None,
        )
        if record is None or not record.preview_file:
            messagebox.showinfo("ไม่มีวิดีโอ", "คลิปนี้ไม่มีวิดีโอตัวอย่าง")
            return
        path = self.app.dataset_store.resolve_data_path(record.preview_file)
        if not path.exists():
            messagebox.showerror("ไม่พบไฟล์วิดีโอ", str(path))
            return
        os.startfile(path)

    def _selected_experiment(self):
        selected = self.experiment_tree.selection()
        if len(selected) != 1:
            return None
        return next(
            (item for item in self._last_experiments if item["id"] == selected[0]),
            None,
        )

    def open_experiment_report(self) -> None:
        item = self._selected_experiment()
        if item is None:
            messagebox.showinfo("เลือกผลการทดลอง", "กรุณาเลือกผลการทดลองหนึ่งรายการ")
            return
        report = item["path"] / "report.md"
        os.startfile(report if report.exists() else item["path"])

    def activate_selected(self) -> None:
        item = self._selected_experiment()
        if item is None:
            messagebox.showinfo("เลือกผลการทดลอง", "กรุณาเลือกผลการทดลองหนึ่งรายการ")
            return
        action = experiment_primary_action(item, installed_experiment_id())[1]
        if action == "camera":
            self.app.open_detector()
            return
        if action == "trial":
            self.activate_trial_selected()
            return
        quick_mode = item.get("mode") == "quick_trial"
        if not messagebox.askyesno(
            "ติดตั้งโมเดลใหม่",
            f"ติดตั้งผล {item['id']} หรือไม่?\nโมเดลและรายการคำเดิมจะถูกสำรองก่อนทุกครั้ง"
            + (
                "\n\nนี่เป็นโมเดลทดลองด่วน คะแนนยังไม่ใช่ผลมาตรฐานสำหรับรายงาน"
                if quick_mode else ""
            ),
        ):
            return
        try:
            backup = activate_experiment(
                item["path"], allow_quick_trial=quick_mode
            )
            self.app.reload_model_state()
            self.app.show_page("gestures")
            gestures_page = self.app.pages.get("gestures")
            if isinstance(gestures_page, GesturesPage):
                gestures_page.show_active(item.get("target_gesture", ""))
            messagebox.showinfo("ติดตั้งสำเร็จ", f"สำรองโมเดลเดิมไว้ที่\n{backup}")
            self.app.set_status(f"ติดตั้งโมเดลจากการทดลอง {item['id']} แล้ว")
        except Exception as exc:
            self.app.show_error("ติดตั้งโมเดลไม่สำเร็จ", exc)

    def activate_trial_selected(self) -> None:
        item = self._selected_experiment()
        if item is None or item["passed"]:
            return
        if not messagebox.askyesno(
            "ติดตั้งโมเดลทดลองที่ยังไม่ผ่านเกณฑ์",
            f"ผล {item['id']} ยังไม่ผ่านเกณฑ์ และอาจจำบางคำผิด\n"
            "จะสำรองโมเดลเดิมและแสดงคำเตือนว่าเป็นโมเดลทดลอง\n"
            "ไม่เปลี่ยนคะแนนให้ผ่าน ไม่ใช้แทนการสื่อสารสำคัญโดยไม่มีคนตรวจ\n\n"
            "ยืนยันติดตั้งเพื่อทดลองหรือไม่?", parent=self,
        ):
            return
        try:
            backup = activate_experiment(
                item["path"], allow_quick_trial=item.get("mode") == "quick_trial",
                allow_unvalidated_trial=True,
            )
            self.app.reload_model_state()
            self.app.set_status("ติดตั้งแบบทดลองแล้ว — ผลยังไม่ผ่านเกณฑ์")
            messagebox.showinfo(
                "ติดตั้งแบบทดลองแล้ว",
                f"ผลประเมินยังไม่ผ่านและไม่ถูกแก้ไข\nสำรองของเดิม: {backup}\n"
                "เปิดกล้องได้จากหน้า ภาพรวม → เริ่มตรวจจับภาษามือ", parent=self,
            )
        except Exception as error:
            self.app.show_error("ติดตั้งแบบทดลองไม่สำเร็จ", error)



# ── หน้า 6: การตั้งค่ากล้อง การยืนยันผล และเสียง ───────────
class SettingsPage(BasePage):
    """แก้และตรวจ AppSettings ก่อนบันทึกใช้ในการเปิด detector ครั้งถัดไป."""

    def __init__(self, parent: tk.Misc, app: "HandVoxApp") -> None:
        super().__init__(
            parent,
            app,
            "ตั้งค่า",
            "ค่าจะถูกใช้ครั้งถัดไปที่เปิดหน้าตรวจจับ",
        )
        scroll = ScrollableFrame(self)
        scroll.pack(fill="both", expand=True)
        form = section_card(scroll.body)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self.gpu_status_var = tk.StringVar(value="กำลังตรวจโหมดประมวลผล...")
        self.vars: dict[str, tk.Variable] = {
            "camera_index": tk.StringVar(),
            "min_confidence": tk.StringVar(),
            "min_probability_margin": tk.StringVar(),
            "confirm_frames": tk.StringVar(),
            "neutral_release_frames": tk.StringVar(),
            "release_seconds": tk.StringVar(),
            "speak_hold_seconds": tk.StringVar(),
            "auto_add_words": tk.BooleanVar(),
            "auto_tts": tk.BooleanVar(),
            "tts_volume": tk.StringVar(),
            "font_scale": tk.StringVar(),
            "prevent_duplicate_words": tk.BooleanVar(),
            "save_spoken_sentences": tk.BooleanVar(),
            "history_limit": tk.StringVar(),
            "prefer_gpu": tk.BooleanVar(),
        }
        rows = (
            ("camera_index", "หมายเลขกล้อง", "0 คือกล้องหลัก"),
            ("min_confidence", "ความมั่นใจขั้นต่ำ", "0.00–1.00; ค่าเริ่มต้น 0.72"),
            (
                "min_probability_margin",
                "ระยะห่างอันดับ 1–2",
                "ต่ำกว่านี้จะแสดงว่าไม่แน่ใจ",
            ),
            ("confirm_frames", "จำนวนเฟรมยืนยัน", "ต้องเห็นท่าติดต่อกันกี่เฟรม"),
            (
                "neutral_release_frames",
                "จำนวนเฟรม Neutral เพื่อปลดล็อก",
                "ก่อนรับคำเดิมอีกครั้ง",
            ),
            ("release_seconds", "เวลาปล่อยท่า", "วินาทีก่อนยอมรับท่าเดิมอีกครั้ง"),
            ("speak_hold_seconds", "เวลาค้างท่าก่อนเพิ่มคำ/อ่าน", "วินาที"),
            ("tts_volume", "ระดับเสียง", "0.00–1.00"),
            ("font_scale", "ขนาดตัวอักษร", "0.75–1.75"),
            ("history_limit", "จำนวนประวัติสูงสุด", "10–1000 รายการ"),
        )
        for row, (key, label, hint) in enumerate(rows):
            ttk.Label(form, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=8)
            ttk.Entry(form, textvariable=self.vars[key], width=18).grid(
                row=row, column=1, sticky="w", padx=(16, 12), pady=8
            )
            ttk.Label(form, text=hint, style="CardMuted.TLabel").grid(row=row, column=2, sticky="w", pady=8)

        bool_start = len(rows)
        for offset, (key, label) in enumerate(
            (
                ("auto_add_words", "เพิ่มคำลงประโยคอัตโนมัติเมื่อค้างท่าจนครบเวลา"),
                ("auto_tts", "อ่านคำที่ตรวจจับได้อัตโนมัติเมื่อค้างท่า"),
                ("prevent_duplicate_words", "ป้องกันคำเดิมซ้ำติดกัน"),
                ("save_spoken_sentences", "บันทึกประโยคที่สั่งพูดลงประวัติ"),
                (
                    "prefer_gpu",
                    "หน้าใช้งานจริง: ลองใช้ GPU ก่อน และกลับไป CPU อัตโนมัติเมื่อไม่พร้อม",
                ),
            )
        ):
            ttk.Checkbutton(form, text=label, variable=self.vars[key]).grid(
                row=bool_start + offset, column=0, columnspan=3, sticky="w", pady=6
            )
        gpu_status = tk.Label(
            form,
            textvariable=self.gpu_status_var,
            background=COLORS["info_soft"],
            foreground=COLORS["accent"],
            anchor="w",
            justify="left",
            padx=12,
            pady=9,
        )
        gpu_status.grid(
            row=bool_start + 5,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(12, 0),
        )
        actions = ttk.Frame(form, style="Card.TFrame")
        actions.grid(row=bool_start + 6, column=0, columnspan=3, sticky="ew", pady=(18, 0))
        ttk.Button(actions, text="คืนค่าเริ่มต้น", command=self.reset).pack(side="left")
        ttk.Button(actions, text="บันทึกการตั้งค่า", style="Accent.TButton", command=self.save).pack(side="right")

    def refresh(self) -> None:
        for key, value in asdict(self.app.settings).items():
            self.vars[key].set(value)
        config = load_training_config()
        requested = str(config.training.parameters.get("device", "auto"))
        camera_mode = "ลองใช้ GPU" if self.app.settings.prefer_gpu else "ใช้ CPU"
        self.gpu_status_var.set(
            f"การเทรน TCN: device={requested} (auto จะเลือก CUDA เมื่อพร้อม) · "
            f"หน้าใช้งานจริง: {camera_mode} · หาก CUDA ใช้ไม่ได้ระบบจะ fallback เป็น CPU"
        )

    def _settings_from_form(self) -> AppSettings:
        return AppSettings(
            camera_index=int(self.vars["camera_index"].get()),
            min_confidence=float(self.vars["min_confidence"].get()),
            min_probability_margin=float(self.vars["min_probability_margin"].get()),
            confirm_frames=int(self.vars["confirm_frames"].get()),
            neutral_release_frames=int(self.vars["neutral_release_frames"].get()),
            release_seconds=float(self.vars["release_seconds"].get()),
            speak_hold_seconds=float(self.vars["speak_hold_seconds"].get()),
            auto_add_words=bool(self.vars["auto_add_words"].get()),
            auto_tts=bool(self.vars["auto_tts"].get()),
            tts_volume=float(self.vars["tts_volume"].get()),
            font_scale=float(self.vars["font_scale"].get()),
            prevent_duplicate_words=bool(self.vars["prevent_duplicate_words"].get()),
            save_spoken_sentences=bool(self.vars["save_spoken_sentences"].get()),
            history_limit=int(self.vars["history_limit"].get()),
            prefer_gpu=bool(self.vars["prefer_gpu"].get()),
        )

    def save(self) -> None:
        try:
            settings = self._settings_from_form()
            self.app.settings_store.save(settings)
            self.app.apply_settings(settings)
            self.refresh()
            self.app.set_status("บันทึกการตั้งค่าแล้ว")
            messagebox.showinfo("บันทึกแล้ว", "การตั้งค่าใหม่จะใช้กับหน้าตรวจจับครั้งถัดไป")
        except Exception as exc:
            self.app.show_error("บันทึกการตั้งค่าไม่สำเร็จ", exc)

    def reset(self) -> None:
        if messagebox.askyesno("คืนค่าเริ่มต้น", "ต้องการคืนค่าการตั้งค่าทั้งหมดหรือไม่?"):
            settings = self.app.settings_store.reset()
            self.app.apply_settings(settings)
            self.refresh()


# ── หน้า 7: วิธีใช้และขอบเขตของระบบ ────────────────────────
class HelpPage(BasePage):
    """แสดงคำอธิบายขอบเขต ลำดับงาน และตำแหน่งไฟล์ช่วยเหลือ."""

    def __init__(self, parent: tk.Misc, app: "HandVoxApp") -> None:
        super().__init__(
            parent,
            app,
            "วิธีใช้และขอบเขต",
            "HandVox มุ่งเป็นแอปช่วยแปลคำภาษามือที่ใช้ในชีวิตประจำวัน",
        )
        scroll = ScrollableFrame(self)
        scroll.pack(fill="both", expand=True)
        sections = (
            (
                "ลำดับพัฒนาที่ใช้อยู่",
                "1. ทำ GUI และระบบแอปให้ครบ\n"
                "2. จัดการคำศัพท์และเตรียม Dataset V2\n"
                "3. เลือกคำใหม่ครั้งละ 1 คำ แล้วเก็บคำจริง + Neutral + Unknown "
                "จากสมาชิก 2 คน แบ่ง 4 รอบ\n"
                "4. ตรวจคุณภาพ เทรน TCN ด้วย GPU เมื่อพร้อม และวัดผลแบบสลับคน",
            ),
            (
                "สิ่งที่ทำได้ตอนนี้โดยไม่ใช้กล้อง",
                "สร้างประโยคจากคลังคำ ทดลองเสียง บันทึกประวัติ จัดลำดับคำศัพท์ "
                "ปรับค่าระบบ ตรวจไฟล์โมเดล เตรียมมาตรฐาน Dataset V2 และตรวจ preflight",
            ),
            (
                "ความหมายของรายการคำศัพท์",
                "แท็บ ‘คำที่เทรนแล้ว’ แยกคำที่ใช้งานกับกล้องได้ออกจากผลที่เทรนผ่านแต่รอติดตั้ง "
                "ส่วนแท็บ ‘คำที่รอเพิ่ม’ เป็นคิวเดียว ทุกคำใหม่เลือกเก็บข้อมูลและเทรนต่อได้ทีละคำ",
            ),
            (
                "ผลการเทรนและเอกสาร",
                "ทุกการทดลองจะสร้างโฟลเดอร์ใหม่ใน experiments พร้อม Accuracy, Precision, "
                "Recall, F1, Confusion Matrix, CSV, JSON, PNG และรายงาน Markdown "
                "ถ้าผลผ่าน ระบบจะสำรองโมเดลเดิม ติดตั้งโมเดลใหม่ และอัปเดต UI อัตโนมัติ "
                "ถ้าผลไม่ผ่านจะเก็บเฉพาะรายงานและไม่เปลี่ยนโมเดล",
            ),
            (
                "เมื่อพร้อมใช้กล้อง",
                "กด ‘เริ่มตรวจจับภาษามือ’ ที่หน้าภาพรวม แอปจะถามยืนยันก่อนเปิดกล้อง "
                "ค้างท่าที่ระบบยืนยันจนครบเวลาเพื่อเพิ่มคำลงประโยคอัตโนมัติ แล้วปล่อยมือ "
                "กลับสู่ Neutral ก่อนทำคำเดิมซ้ำ ถ้าความมั่นใจต่ำจะแสดง ‘ไม่แน่ใจ’ "
                "ปุ่มบนหน้ากล้องใช้เพิ่ม ลบ อ่าน บันทึก และล้างได้ และจะลองใช้ GPU "
                "ตามค่าที่ตั้งไว้โดย fallback เป็น CPU ได้",
            ),
            (
                "ไฟล์บันทึกข้อผิดพลาด",
                f"ถ้า GUI พบข้อผิดพลาด รายละเอียดทางเทคนิคจะอยู่ที่ {LOG_FILE}",
            ),
        )
        for title, body in sections:
            card = section_card(scroll.body)
            card.pack(fill="x", pady=(0, 12))
            ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(card, text=body, style="HelpBody.TLabel", wraplength=850).pack(
                anchor="w", fill="x", pady=(8, 0)
            )


# ── ตัวแอปหลัก: เมนู ธีม หน้า และบริการร่วม ───────────────
class HandVoxApp:
    """ประกอบหน้าทั้งหมด จัดเมนู สถานะ และเชื่อมบริการภายนอก."""

    NAV_ITEMS = (
        ("dashboard", "ภาพรวม"),
        ("sentence", "สร้างประโยค"),
        ("gestures", "คำศัพท์"),
        ("training", "เตรียมเทรน"),
        ("settings", "ตั้งค่า"),
        ("help", "วิธีใช้"),
    )

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.settings_store = SettingsStore()
        self.settings = self.settings_store.load_or_default()
        self.history_store = HistoryStore()
        self.catalog = GestureCatalog()
        self.dataset_store = DatasetV2Store()
        self.launcher = ScriptLauncher()
        self.active_gestures = self.catalog.load_active()
        self._speech = None
        self.pages: dict[str, BasePage] = {}
        self.nav_buttons: dict[str, tk.Button] = {}
        self.status_var = tk.StringVar(value="พร้อมใช้งาน — ยังไม่ได้เปิดกล้อง")
        if self.settings_store.last_error:
            self.status_var.set("settings.json ไม่ถูกต้อง — ใช้ค่าเริ่มต้นชั่วคราว")

        self._configure_window()
        self._configure_styles()
        self._build_layout()
        self.root.report_callback_exception = self._report_callback_exception
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.show_page("dashboard")

    def _configure_window(self) -> None:
        self.root.title("HandVox — ผู้ช่วยภาษามือในชีวิตประจำวัน")
        self.root.geometry("1180x760")
        self.root.minsize(980, 650)
        self.root.configure(background=COLORS["background"])

    def _configure_styles(self) -> None:
        scale = self.settings.font_scale
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        base_font = ("Leelawadee UI", max(9, round(10 * scale)))
        heading_font = ("Leelawadee UI", max(18, round(24 * scale)), "bold")
        title_font = ("Leelawadee UI", max(11, round(13 * scale)), "bold")
        metric_font = ("Leelawadee UI", max(18, round(25 * scale)), "bold")
        sentence_font = ("Leelawadee UI", max(16, round(21 * scale)), "bold")
        style.configure(".", font=base_font)
        style.configure("Page.TFrame", background=COLORS["background"])
        style.configure("Card.TFrame", background=COLORS["card"])
        style.configure(
            "OutlinedCard.TFrame",
            background=COLORS["card"],
            borderwidth=1,
            relief="solid",
        )
        style.configure("Title.TLabel", background=COLORS["background"], foreground=COLORS["text"], font=heading_font)
        style.configure("Subtitle.TLabel", background=COLORS["background"], foreground=COLORS["muted"])
        style.configure("Card.TLabel", background=COLORS["card"], foreground=COLORS["text"])
        style.configure("CardTitle.TLabel", background=COLORS["card"], foreground=COLORS["text"], font=title_font)
        style.configure("CardMuted.TLabel", background=COLORS["card"], foreground=COLORS["muted"])
        style.configure("Metric.TLabel", background=COLORS["card"], foreground=COLORS["accent"], font=metric_font)
        style.configure("Sentence.TLabel", background=COLORS["card"], foreground=COLORS["text"], font=sentence_font)
        style.configure("HelpBody.TLabel", background=COLORS["card"], foreground=COLORS["text"], justify="left")
        style.configure("TButton", padding=(12, 7))
        style.configure("Accent.TButton", foreground="#ffffff", background=COLORS["accent"], padding=(14, 8))
        style.map("Accent.TButton", background=[("active", COLORS["accent_hover"]), ("!disabled", COLORS["accent"])])
        style.configure(
            "Success.TButton",
            foreground="#ffffff",
            background=COLORS["success"],
            padding=(14, 8),
        )
        style.map(
            "Success.TButton",
            background=[
                ("disabled", COLORS["neutral_soft"]),
                ("active", "#166534"),
                ("!disabled", COLORS["success"]),
            ],
            foreground=[("disabled", COLORS["muted"]), ("!disabled", "#ffffff")],
        )
        style.configure(
            "Danger.TButton",
            foreground="#ffffff",
            background=COLORS["danger"],
            padding=(12, 7),
        )
        style.map(
            "Danger.TButton",
            background=[("active", "#991b1b"), ("!disabled", COLORS["danger"])],
        )
        style.configure(
            "Muted.TButton",
            foreground=COLORS["text"],
            background=COLORS["neutral_soft"],
        )
        style.map("Muted.TButton", background=[("active", "#d1d5db")])
        style.configure("TNotebook", background=COLORS["background"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 8), font=title_font)
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLORS["card"]), ("!selected", COLORS["neutral_soft"])],
            foreground=[("selected", COLORS["accent"]), ("!selected", COLORS["muted"])],
        )
        style.configure(
            "Training.Horizontal.TProgressbar",
            troughcolor=COLORS["neutral_soft"],
            background=COLORS["accent"],
            lightcolor=COLORS["accent"],
            darkcolor=COLORS["accent"],
            bordercolor=COLORS["neutral_soft"],
        )
        style.configure("Treeview", rowheight=max(26, round(29 * scale)))
        style.configure("Treeview.Heading", font=("Leelawadee UI", max(9, round(10 * scale)), "bold"))

    def _build_layout(self) -> None:
        shell = tk.Frame(self.root, background=COLORS["background"])
        shell.pack(fill="both", expand=True)
        nav = tk.Frame(shell, background=COLORS["nav"], width=210)
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)
        brand = tk.Label(
            nav,
            text="HANDVOX",
            font=("Segoe UI", 20, "bold"),
            foreground="#ffffff",
            background=COLORS["nav"],
            anchor="w",
            padx=22,
            pady=25,
        )
        brand.pack(fill="x")
        tk.Label(
            nav,
            text="ผู้ช่วยภาษามือ",
            font=("Leelawadee UI", 10),
            foreground="#9ca3af",
            background=COLORS["nav"],
            anchor="w",
            padx=22,
        ).pack(fill="x", pady=(0, 18))
        for key, label in self.NAV_ITEMS:
            button = tk.Button(
                nav,
                text=label,
                font=("Leelawadee UI", 11),
                foreground="#d1d5db",
                background=COLORS["nav"],
                activeforeground="#ffffff",
                activebackground=COLORS["nav_hover"],
                relief="flat",
                borderwidth=0,
                anchor="w",
                padx=22,
                pady=11,
                cursor="hand2",
                command=lambda page=key: self.show_page(page),
            )
            button.pack(fill="x")
            self.nav_buttons[key] = button
        tk.Label(
            nav,
            text="v0.3",
            foreground="#6b7280",
            background=COLORS["nav"],
            anchor="w",
            padx=22,
            pady=18,
        ).pack(side="bottom", fill="x")

        right = tk.Frame(shell, background=COLORS["background"])
        right.pack(side="left", fill="both", expand=True)
        self.page_host = ttk.Frame(right, style="Page.TFrame")
        self.page_host.pack(fill="both", expand=True)
        self.deployment_warning = tk.Label(
            right, text="โมเดลทดลอง: ผลยังไม่ผ่านเกณฑ์ — อาจจำบางคำผิด โปรดตรวจคำก่อนใช้",
            background=COLORS["warning_soft"], foreground=COLORS["warning"],
            font=("Leelawadee UI", 10, "bold"), anchor="w", padx=18, pady=8,
        )
        self._refresh_deployment_warning()
        status = tk.Label(
            right,
            textvariable=self.status_var,
            background="#e5e7eb",
            foreground=COLORS["muted"],
            anchor="w",
            padx=18,
            pady=7,
            font=("Leelawadee UI", 9),
        )
        status.pack(side="bottom", fill="x")

        page_classes = {
            "dashboard": DashboardPage,
            "sentence": SentencePage,
            "gestures": GesturesPage,
            "training": TrainingPage,
            "settings": SettingsPage,
            "help": HelpPage,
        }
        for key, page_class in page_classes.items():
            page = page_class(self.page_host, self)
            page.place(x=0, y=0, relwidth=1, relheight=1)
            self.pages[key] = page

    def show_page(self, key: str) -> None:
        page = self.pages[key]
        page.tkraise()
        for nav_key, button in self.nav_buttons.items():
            selected = nav_key == key
            button.configure(
                background=COLORS["accent"] if selected else COLORS["nav"],
                foreground="#ffffff" if selected else "#d1d5db",
            )
        try:
            page.refresh()
        except Exception as exc:
            self.show_error("โหลดหน้านี้ไม่สำเร็จ", exc)

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def reload_model_state(self) -> None:
        """โหลดโมเดล/คำศัพท์ล่าสุดและวาดหน้าที่ใช้รายการคำใหม่ทันที."""
        self.catalog = GestureCatalog()
        self.active_gestures = self.catalog.load_active()
        if "deployment_warning" in self.__dict__:
            self._refresh_deployment_warning()
        for key in ("dashboard", "sentence", "gestures", "training"):
            page = self.pages.get(key)
            if page is not None:
                try:
                    page.refresh()
                except Exception:
                    logging.exception("รีเฟรชหน้า %s หลังโหลดโมเดลใหม่ไม่สำเร็จ", key)

    def _refresh_deployment_warning(self) -> None:
        try:
            manifest = json.loads((ROOT / "model_manifest.json").read_text(encoding="utf-8"))
            experimental = manifest.get("deployment", {}).get("status") == "experimental_unvalidated"
        except (OSError, ValueError, TypeError, AttributeError):
            experimental = False
        if experimental:
            self.deployment_warning.pack(fill="x", before=self.page_host)
        else:
            self.deployment_warning.pack_forget()

    def apply_settings(self, settings: AppSettings) -> None:
        self.settings = settings
        sentence_page = self.pages.get("sentence")
        if isinstance(sentence_page, SentencePage):
            sentence_page.builder.prevent_duplicates = settings.prevent_duplicate_words
        if self._speech is not None:
            self._speech.close()
            self._speech = None

    def open_detector(self) -> None:
        if not messagebox.askyesno(
            "เปิดกล้อง",
            "การตรวจจับจะเปิดกล้องในหน้าต่างใหม่\nต้องการดำเนินการต่อหรือไม่?",
        ):
            self.set_status("ยกเลิกการเปิดกล้อง")
            return
        try:
            self.launcher.launch("detect")
            self.set_status("เปิดหน้าตรวจจับแล้ว")
        except Exception as exc:
            self.show_error("เปิดหน้าตรวจจับไม่สำเร็จ", exc)

    def speak(self, text: str) -> bool:
        try:
            if self._speech is None:
                from tts_service import SpeechService

                self._speech = SpeechService(volume=self.settings.tts_volume)
            return bool(self._speech.speak(text))
        except Exception as exc:
            self.show_error("ระบบเสียงไม่พร้อมใช้งาน", exc)
            return False

    def show_error(self, title: str, error: Exception) -> None:
        logging.exception("%s: %s", title, error)
        messagebox.showerror(title, f"{error}\n\nดูรายละเอียดเพิ่มเติมได้ที่ {LOG_FILE}")
        self.set_status(title)

    def _report_callback_exception(self, exc_type, exc_value, exc_traceback) -> None:
        detail = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        logging.error("Unhandled GUI exception:\n%s", detail)
        messagebox.showerror(
            "HandVox พบข้อผิดพลาด",
            f"{exc_value}\n\nบันทึกรายละเอียดไว้ที่ {LOG_FILE}",
        )

    def close(self) -> None:
        if self._speech is not None:
            self._speech.close()
        self.root.destroy()


def run() -> None:
    """สร้าง Tk root ตั้งขนาดขั้นต่ำ และเริ่ม event loop ของ HandVox."""
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )
    root = tk.Tk()
    HandVoxApp(root)
    root.mainloop()
