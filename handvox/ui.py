"""หน้าจอหลักทั้งหมดของ HandVox สร้างด้วย Tkinter.

ไฟล์นี้ประกอบด้วยหน้า Dashboard, สร้างประโยค, คำศัพท์, Dataset V2,
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
from handvox.paths import DATASET_V2_DIR, LOG_FILE, ROOT
from handvox.processes import ScriptLauncher
from handvox.sentence import SentenceBuilder
from handvox.settings import AppSettings, SettingsStore
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


# ── เครื่องมือ UI ที่ใช้ร่วมกันทุกหน้า ──────────────────────
def clear_children(widget: tk.Misc) -> None:
    """ลบ widget ลูกทั้งหมดก่อนวาดรายการใหม่จากข้อมูลล่าสุด."""
    for child in widget.winfo_children():
        child.destroy()


def section_card(parent: tk.Misc, padding: int = 18) -> ttk.Frame:
    """สร้างกรอบ card มาตรฐานตามสีและระยะห่างของแอป."""
    return ttk.Frame(parent, style="OutlinedCard.TFrame", padding=padding)


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
            "ตรวจความพร้อมของโปรเจกต์โดยไม่เปิดกล้องและไม่เทรนโมเดล",
        )

        action_row = ttk.Frame(self, style="Page.TFrame")
        action_row.pack(fill="x", pady=(0, 18))
        ttk.Button(
            action_row,
            text="เริ่มตรวจจับภาษามือ",
            style="Accent.TButton",
            command=app.open_detector,
        ).pack(side="left")
        ttk.Button(
            action_row,
            text="สร้างประโยคโดยไม่ใช้กล้อง",
            command=lambda: app.show_page("sentence"),
        ).pack(side="left", padx=10)
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
        self._summary_card(summary, 2, "คลิป Dataset V2", self.dataset_var)

        card = section_card(self)
        card.pack(fill="both", expand=True)
        ttk.Label(card, text="สถานะระบบ", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            card,
            text="รายการนี้เป็นการอ่านไฟล์เท่านั้น ไม่เปิดกล้องและไม่แก้ไขโมเดล",
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(2, 12))
        self.tree = ttk.Treeview(
            card,
            columns=("status", "name", "detail"),
            show="headings",
            height=12,
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

    def open_reference(self) -> None:
        url = self.form_vars["reference_url"].get().strip()
        if not url:
            messagebox.showinfo("ยังไม่มีลิงก์", "เพิ่มลิงก์อ้างอิงก่อน")
            return
        if not url.startswith(("https://", "http://")):
            messagebox.showerror("ลิงก์ไม่ถูกต้อง", "ลิงก์ต้องเริ่มด้วย https:// หรือ http://")
            return
        webbrowser.open(url)


# ── หน้า 4: สถานะ Dataset V2 ───────────────────────────────
class DatasetPage(BasePage):
    """สรุป metadata, inventory และโครงสร้าง Dataset V2."""

    def __init__(self, parent: tk.Misc, app: "HandVoxApp") -> None:
        super().__init__(
            parent,
            app,
            "Dataset V2",
            "เตรียมมาตรฐานข้อมูลก่อนเก็บคลิปจริง โดยยังไม่ใช้กล้องและไม่เทรน",
        )
        summary = section_card(self)
        summary.pack(fill="x", pady=(0, 18))
        self.total_var = tk.StringVar(value="0")
        self.gesture_var = tk.StringVar(value="0")
        self.signer_var = tk.StringVar(value="0")
        ttk.Label(summary, text="สถานะ Dataset V2", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w"
        )
        for column, (label, variable) in enumerate(
            (
                ("คลิปทั้งหมด", self.total_var),
                ("จำนวนท่า", self.gesture_var),
                ("ผู้ทำท่า", self.signer_var),
            )
        ):
            summary.columnconfigure(column, weight=1)
            ttk.Label(summary, text=label, style="CardMuted.TLabel").grid(
                row=1, column=column, sticky="w", pady=(14, 0)
            )
            ttk.Label(summary, textvariable=variable, style="Metric.TLabel").grid(
                row=2, column=column, sticky="w"
            )
        ttk.Button(summary, text="สร้างโฟลเดอร์ Dataset V2", command=self.initialize).grid(
            row=1, column=3, rowspan=2, sticky="e"
        )

        details = section_card(self)
        details.pack(fill="both", expand=True)
        ttk.Label(details, text="ข้อมูลที่ต้องบันทึกต่อหนึ่งคลิป", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            details,
            text=f"ตำแหน่ง: {DATASET_V2_DIR}",
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(2, 12))
        fields = (
            ("clip_id", "รหัสคลิปที่ไม่ซ้ำ"),
            ("gesture_name", "ชื่อท่าหรือคำ"),
            ("signer_id", "รหัสผู้ทำท่าโดยไม่ใช้ชื่อจริง"),
            ("session_id", "รหัสรอบการเก็บข้อมูล"),
            ("recorded_at", "วันเวลาแบบ ISO 8601"),
            ("camera_index", "หมายเลขกล้อง"),
            ("lighting", "สภาพแสง"),
            ("clip_number", "ลำดับคลิปในรอบ"),
            ("quality", "สถานะ pending / accepted / rejected"),
            ("reference_url", "แหล่งอ้างอิงรูปแบบท่า"),
            ("sequence_file", "ตำแหน่งไฟล์ landmark"),
            ("preview_file", "วิดีโอตัวอย่างสำหรับตรวจคุณภาพ"),
            ("duration_frames", "จำนวนเฟรมที่บันทึกจริง"),
            ("feature_count", "จำนวนคุณลักษณะต่อเฟรม"),
            ("dataset_version", "เวอร์ชันรูปแบบข้อมูล"),
            ("notes", "หมายเหตุเพิ่มเติม"),
        )
        tree = ttk.Treeview(details, columns=("field", "meaning"), show="headings", height=12)
        tree.heading("field", text="ฟิลด์")
        tree.heading("meaning", text="ความหมาย")
        tree.column("field", width=180, stretch=False)
        tree.column("meaning", width=650)
        for field, meaning in fields:
            tree.insert("", "end", values=(field, meaning))
        tree.pack(fill="both", expand=True)

    def refresh(self) -> None:
        summary = self.app.dataset_store.summary()
        self.total_var.set(str(summary["clips"]))
        self.gesture_var.set(str(len(summary["gestures"])))
        self.signer_var.set(str(summary["signers"]))

    def initialize(self) -> None:
        try:
            self.app.dataset_store.initialize()
            self.refresh()
            self.app.set_status("เตรียมโฟลเดอร์ Dataset V2 แล้ว — ยังไม่มีการเปิดกล้อง")
            messagebox.showinfo(
                "เตรียม Dataset V2 แล้ว",
                "สร้างโครงโฟลเดอร์และไฟล์ metadata เปล่าแล้ว\nไม่มีการเก็บคลิปหรือเทรนโมเดล",
            )
        except Exception as exc:
            self.app.show_error("สร้าง Dataset V2 ไม่สำเร็จ", exc)


class TrainingPageLegacy(BasePage):
    """หน้าฝึกแบบแท็บรุ่นเก่าที่เก็บไว้เพื่ออ้างอิงและไม่ถูกสร้างในแอปปัจจุบัน."""

    def __init__(self, parent: tk.Misc, app: "HandVoxApp") -> None:
        super().__init__(
            parent,
            app,
            "เตรียมเทรนและวัดผล",
            "จัดการข้อมูลคำทั้งหมด + neutral ตรวจความพร้อม และเก็บผลทุกการทดลอง",
        )
        self.config = load_training_config()
        self.signer_var = tk.StringVar(value=self.config.collection.signers[0])
        self.session_var = tk.StringVar(value=self.config.collection.sessions[0])
        self.gesture_var = tk.StringVar(value=self.config.all_classes[0])
        self.lighting_var = tk.StringVar(value="unknown")
        self.readiness_var = tk.StringVar(value="ยังไม่พร้อม")
        self.accepted_var = tk.StringVar(value="0")
        self.target_var = tk.StringVar(value=str(self.config.expected_clip_count))

        summary = ttk.Frame(self, style="Page.TFrame")
        summary.pack(fill="x", pady=(0, 16))
        for column in range(4):
            summary.columnconfigure(column, weight=1, uniform="training-summary")
        for column, (title, value) in enumerate(
            (
                ("คำศัพท์ที่แสดง", tk.StringVar(value="16")),
                ("รวม neutral", tk.StringVar(value=str(len(self.config.all_classes)))),
                ("accepted / เป้าหมาย", self.accepted_var),
                ("สถานะ", self.readiness_var),
            )
        ):
            card = section_card(summary, 14)
            card.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 5, 0 if column == 3 else 5),
            )
            ttk.Label(card, text=title, style="CardMuted.TLabel").pack(anchor="w")
            ttk.Label(card, textvariable=value, style="Metric.TLabel").pack(anchor="w", pady=(5, 0))

        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True)
        readiness_tab = ttk.Frame(tabs, style="Card.TFrame", padding=14)
        collection_tab = ttk.Frame(tabs, style="Card.TFrame", padding=14)
        quality_tab = ttk.Frame(tabs, style="Card.TFrame", padding=14)
        experiments_tab = ttk.Frame(tabs, style="Card.TFrame", padding=14)
        tabs.add(readiness_tab, text="ความพร้อม")
        tabs.add(collection_tab, text="เก็บข้อมูล")
        tabs.add(quality_tab, text="ตรวจคุณภาพ")
        tabs.add(experiments_tab, text="ผลการทดลอง")

        readiness_actions = ttk.Frame(readiness_tab, style="Card.TFrame")
        readiness_actions.pack(fill="x", pady=(0, 10))
        ttk.Label(
            readiness_actions,
            text="ต้องไม่มีรายการ ‘ต้องแก้’ จึงจะเริ่มเทรนได้",
            style="CardMuted.TLabel",
        ).pack(side="left")
        ttk.Button(readiness_actions, text="ตรวจใหม่", command=self.refresh).pack(side="right")
        ttk.Button(
            readiness_actions,
            text="เทรนและสร้างรายงาน",
            style="Accent.TButton",
            command=self.start_training,
        ).pack(side="right", padx=8)
        self.readiness_tree = ttk.Treeview(
            readiness_tab,
            columns=("status", "message"),
            show="headings",
            height=14,
        )
        self.readiness_tree.heading("status", text="สถานะ")
        self.readiness_tree.heading("message", text="รายละเอียด")
        self.readiness_tree.column("status", width=90, anchor="center", stretch=False)
        self.readiness_tree.column("message", width=770)
        self.readiness_tree.tag_configure("ok", foreground=COLORS["success"])
        self.readiness_tree.tag_configure("warning", foreground=COLORS["warning"])
        self.readiness_tree.tag_configure("error", foreground=COLORS["danger"])
        self.readiness_tree.pack(fill="both", expand=True)

        collection_tab.columnconfigure(1, weight=1)
        fields = (
            ("ผู้ทำท่า", self.signer_var, self.config.collection.signers),
            ("รอบเก็บข้อมูล", self.session_var, self.config.collection.sessions),
            ("ท่า", self.gesture_var, self.config.all_classes),
            ("สภาพแสง", self.lighting_var, ("unknown", "bright", "normal", "dim", "backlit")),
        )
        for row, (label, variable, values) in enumerate(fields):
            ttk.Label(collection_tab, text=label, style="Card.TLabel").grid(
                row=row, column=0, sticky="w", pady=8
            )
            ttk.Combobox(
                collection_tab,
                textvariable=variable,
                values=values,
                state="readonly",
                width=30,
            ).grid(row=row, column=1, sticky="w", padx=(14, 0), pady=8)
        ttk.Label(
            collection_tab,
            text=(
                "แต่ละคนเก็บคลาสละ 10 คลิป แบ่ง session_01 และ session_02 อย่างละ 5 คลิป\n"
                "คลิปใหม่จะเป็น pending และจะยังไม่ถูกนำไปเทรนจนกว่าจะกด accepted"
            ),
            style="CardMuted.TLabel",
            justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(14, 10))
        ttk.Button(
            collection_tab,
            text="เปิดกล้องเก็บชุดที่เลือก",
            style="Accent.TButton",
            command=self.start_collection,
        ).grid(row=5, column=0, columnspan=2, sticky="w")

        quality_actions = ttk.Frame(quality_tab, style="Card.TFrame")
        quality_actions.pack(fill="x", pady=(0, 10))
        ttk.Button(quality_actions, text="เปิดวิดีโอตัวอย่าง", command=self.open_preview).pack(side="left")
        ttk.Button(quality_actions, text="ตั้งเป็น accepted", command=lambda: self.set_selected_quality("accepted")).pack(side="right")
        ttk.Button(quality_actions, text="ตั้งเป็น rejected", command=lambda: self.set_selected_quality("rejected")).pack(side="right", padx=8)
        ttk.Button(quality_actions, text="กลับเป็น pending", command=lambda: self.set_selected_quality("pending")).pack(side="right")
        self.quality_tree = ttk.Treeview(
            quality_tab,
            columns=("gesture", "signer", "session", "quality", "time", "preview"),
            show="headings",
            selectmode="extended",
            height=13,
        )
        for column, title, width in (
            ("gesture", "ท่า", 130),
            ("signer", "ผู้ทำท่า", 100),
            ("session", "รอบ", 100),
            ("quality", "คุณภาพ", 90),
            ("time", "เวลา", 150),
            ("preview", "วิดีโอ", 80),
        ):
            self.quality_tree.heading(column, text=title)
            self.quality_tree.column(column, width=width, stretch=column == "gesture")
        self.quality_tree.tag_configure("accepted", foreground=COLORS["success"])
        self.quality_tree.tag_configure("pending", foreground=COLORS["warning"])
        self.quality_tree.tag_configure("rejected", foreground=COLORS["danger"])
        self.quality_tree.pack(fill="both", expand=True)

        experiment_actions = ttk.Frame(experiments_tab, style="Card.TFrame")
        experiment_actions.pack(fill="x", pady=(0, 10))
        ttk.Label(
            experiment_actions,
            text="โมเดลจากการทดลองจะไม่แทนโมเดลหลักจนกว่าจะเลือกติดตั้ง",
            style="CardMuted.TLabel",
        ).pack(side="left")
        ttk.Button(experiment_actions, text="เปิดรายงาน", command=self.open_experiment_report).pack(side="right")
        ttk.Button(experiment_actions, text="ติดตั้งโมเดลที่ผ่าน", command=self.activate_selected).pack(side="right", padx=8)
        self.experiment_tree = ttk.Treeview(
            experiments_tab,
            columns=("id", "accuracy", "f1", "passed", "created"),
            show="headings",
            height=13,
        )
        for column, title, width in (
            ("id", "รหัสการทดลอง", 170),
            ("accuracy", "Accuracy", 100),
            ("f1", "Macro F1", 100),
            ("passed", "ผลเกณฑ์", 100),
            ("created", "เวลา", 190),
        ):
            self.experiment_tree.heading(column, text=title)
            self.experiment_tree.column(column, width=width, stretch=column == "created")
        self.experiment_tree.tag_configure("passed", foreground=COLORS["success"])
        self.experiment_tree.tag_configure("failed", foreground=COLORS["danger"])
        self.experiment_tree.pack(fill="both", expand=True)

    def refresh(self) -> None:
        self.config = load_training_config()
        report = preflight(self.config, self.app.dataset_store)
        self.accepted_var.set(f"{report.accepted_clips} / {report.expected_target_clips}")
        self.readiness_var.set("พร้อม" if report.ready else "ยังไม่พร้อม")
        for row in self.readiness_tree.get_children():
            self.readiness_tree.delete(row)
        labels = {"ok": "พร้อม", "warning": "ควรตรวจ", "error": "ต้องแก้"}
        for item in report.items:
            self.readiness_tree.insert(
                "",
                "end",
                values=(labels.get(item.status, item.status), item.message),
                tags=(item.status,),
            )
        self._refresh_quality()
        self._refresh_experiments()

    def _refresh_quality(self) -> None:
        for row in self.quality_tree.get_children():
            self.quality_tree.delete(row)
        for record in reversed(self.app.dataset_store.records()):
            self.quality_tree.insert(
                "",
                "end",
                iid=record.clip_id,
                values=(
                    record.gesture_name,
                    record.signer_id,
                    record.session_id,
                    record.quality,
                    record.recorded_at,
                    "มี" if record.preview_file else "ไม่มี",
                ),
                tags=(record.quality,),
            )

    def _refresh_experiments(self) -> None:
        for row in self.experiment_tree.get_children():
            self.experiment_tree.delete(row)
        for item in list_experiments():
            tag = "passed" if item["passed"] else "failed"
            self.experiment_tree.insert(
                "",
                "end",
                iid=item["id"],
                values=(
                    item["id"],
                    f"{item['accuracy']:.4f}",
                    f"{item['macro_f1']:.4f}",
                    "ผ่าน" if item["passed"] else "ยังไม่ผ่าน",
                    item["created_at"],
                ),
                tags=(tag,),
            )

    def start_collection(self) -> None:
        if not messagebox.askyesno(
            "เปิดกล้องเก็บข้อมูล",
            f"ผู้ทำท่า: {self.signer_var.get()}\n"
            f"รอบ: {self.session_var.get()}\n"
            f"ท่า: {self.gesture_var.get()}\n\nต้องการเปิดกล้องหรือไม่?",
        ):
            return
        arguments = (
            "--signer", self.signer_var.get(),
            "--session", self.session_var.get(),
            "--gesture", self.gesture_var.get(),
            "--lighting", self.lighting_var.get(),
        )
        try:
            self.app.launcher.launch("collect_v2", arguments)
            self.app.set_status("เปิดเครื่องมือเก็บ Dataset V2 แล้ว")
        except Exception as exc:
            self.app.show_error("เปิดเครื่องมือเก็บข้อมูลไม่สำเร็จ", exc)

    def start_training(self) -> None:
        report = preflight(self.config, self.app.dataset_store)
        if not report.ready:
            messagebox.showwarning(
                "ข้อมูลยังไม่พร้อม",
                "ยังมีรายการ ‘ต้องแก้’ ในแท็บความพร้อม จึงยังไม่เริ่มเทรน",
            )
            return
        if not messagebox.askyesno(
            "เริ่มเทรนและวัดผล",
            "ระบบจะประเมินแบบสลับสมาชิก 2 คนและสร้างไฟล์รายงาน\n"
            "โมเดลหลักจะยังไม่ถูกเขียนทับ ต้องการดำเนินการต่อหรือไม่?",
        ):
            return
        try:
            self.app.launcher.launch("train_v2", ("train",))
            self.app.set_status("เริ่ม workflow เทรนและวัดผลในหน้าต่างใหม่แล้ว")
        except Exception as exc:
            self.app.show_error("เริ่มเทรนไม่สำเร็จ", exc)

    def set_selected_quality(self, quality: str) -> None:
        selected = self.quality_tree.selection()
        if not selected:
            return
        try:
            updated = self.app.dataset_store.set_quality(selected, quality)
            self.app.set_status(f"ปรับคุณภาพ {updated} คลิปเป็น {quality}")
            self.refresh()
        except Exception as exc:
            self.app.show_error("ปรับสถานะคลิปไม่สำเร็จ", exc)

    def open_preview(self) -> None:
        selected = self.quality_tree.selection()
        if len(selected) != 1:
            messagebox.showinfo("เลือกหนึ่งคลิป", "กรุณาเลือกคลิปหนึ่งรายการ")
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
            messagebox.showerror("ไม่พบไฟล์", str(path))
            return
        os.startfile(path)

    def _selected_experiment(self):
        selected = self.experiment_tree.selection()
        if len(selected) != 1:
            return None
        return next((item for item in list_experiments() if item["id"] == selected[0]), None)

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
        if not item["passed"]:
            messagebox.showwarning("ยังไม่ผ่านเกณฑ์", "ติดตั้งได้เฉพาะโมเดลที่ผ่านเกณฑ์")
            return
        if not messagebox.askyesno(
            "ติดตั้งโมเดลใหม่",
            f"ติดตั้งผล {item['id']} หรือไม่?\n"
            "โมเดลและรายการคำเดิมจะถูกสำรองก่อนทุกครั้ง",
        ):
            return
        try:
            backup = activate_experiment(item["path"])
            self.app.catalog = GestureCatalog()
            messagebox.showinfo("ติดตั้งแล้ว", f"สำรองโมเดลเดิมไว้ที่\n{backup}")
            self.app.set_status(f"ติดตั้งโมเดลจากการทดลอง {item['id']} แล้ว")
        except Exception as exc:
            self.app.show_error("ติดตั้งโมเดลไม่สำเร็จ", exc)


# ── หน้า 5: Wizard เตรียมเทรน 5 ขั้น ───────────────────────
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
            "เตรียมเทรนทีละขั้น",
            "ทำตามขั้นที่ 1–5 ปุ่มเทรนจะเปิดเมื่อข้อมูลพร้อม และอ่านผลได้ทันทีเมื่อเสร็จ",
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
        self.scope_summary_var = tk.StringVar(value="กำลังตรวจรายการท่า...")
        self.readiness_summary_var = tk.StringVar(value="กำลังตรวจความพร้อม...")
        self.quality_stat_vars = {
            "accepted": tk.StringVar(value="0"),
            "pending": tk.StringVar(value="0"),
            "rejected": tk.StringVar(value="0"),
        }
        self._last_report = None
        self._last_experiments = []
        self._step_buttons: list[tk.Button] = []

        self._build_stepper()
        self._build_tabs()

    def _build_stepper(self) -> None:
        stepper = tk.Frame(self, background=COLORS["background"])
        stepper.pack(fill="x", pady=(0, 12))
        for column in range(5):
            stepper.columnconfigure(column, weight=1, uniform="training-step")
        for index, title in enumerate(self.STEP_TITLES):
            button = tk.Button(
                stepper,
                text=f"{title}\nรอดำเนินการ",
                font=("Leelawadee UI", 10, "bold"),
                foreground=COLORS["muted"],
                background=COLORS["neutral_soft"],
                activebackground=COLORS["info_soft"],
                activeforeground=COLORS["accent"],
                relief="flat",
                borderwidth=0,
                padx=8,
                pady=10,
                justify="left",
                anchor="w",
                cursor="hand2",
                command=lambda tab=index: self.show_step(tab),
            )
            button.grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(0 if index == 0 else 4, 0 if index == 4 else 4),
            )
            self._step_buttons.append(button)

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
            text=(
                "ช่องด้านล่างคือป้ายกำกับของคลิปที่จะถ่าย ไม่ใช่รายการคำที่ยังไม่ได้เทรน "
                "· เก็บข้อมูลเสริมของคำเดิมได้"
            ),
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
            # รายการเก็บข้อมูลแสดงคำในโมเดล + คำใหม่รอบนี้ + neutral
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
        ttk.Button(
            form,
            text="เปิดกล้องเก็บชุดนี้",
            style="Accent.TButton",
            command=self.start_collection,
        ).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        ttk.Label(
            form,
            text=(
                "รายการประกอบด้วยคำในโมเดลปัจจุบัน + คำใหม่ที่เลือก + neutral "
                "เพื่อป้องกันคำเดิมหายหลังเทรน"
            ),
            style="CardMuted.TLabel",
            wraplength=470,
            justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))

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
            text=(
                "Session 1: แสงและตำแหน่งปกติ\n"
                "Session 2: เปลี่ยนเสื้อ ระยะ หรือสภาพแสง\n\n"
                "คลิปใหม่จะเป็น pending จนกว่าจะตรวจวิดีโอ"
            ),
            style="CardMuted.TLabel",
            justify="left",
            wraplength=300,
        ).pack(anchor="w")

    def _build_quality_tab(self) -> None:
        stats = ttk.Frame(self.quality_tab, style="Card.TFrame")
        stats.pack(fill="x", pady=(0, 10))
        for column, (key, title, soft, strong) in enumerate(
            (
                ("pending", "รอตรวจ", COLORS["warning_soft"], COLORS["warning"]),
                ("accepted", "ผ่านแล้ว", COLORS["success_soft"], COLORS["success"]),
                ("rejected", "ไม่ผ่าน", COLORS["danger_soft"], COLORS["danger"]),
            )
        ):
            stats.columnconfigure(column, weight=1, uniform="quality-stat")
            box = tk.Frame(stats, background=soft)
            box.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 5, 0 if column == 2 else 5),
            )
            tk.Label(
                box,
                text=title,
                font=("Leelawadee UI", 9, "bold"),
                foreground=strong,
                background=soft,
            ).pack(anchor="w", padx=12, pady=(7, 0))
            tk.Label(
                box,
                textvariable=self.quality_stat_vars[key],
                font=("Leelawadee UI", 18, "bold"),
                foreground=strong,
                background=soft,
            ).pack(anchor="w", padx=12, pady=(0, 7))

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
            text="ไม่ผ่าน",
            style="Danger.TButton",
            command=lambda: self.set_selected_quality("rejected"),
        ).pack(side="right")
        ttk.Button(
            actions,
            text="ผ่าน ใช้เทรนได้",
            style="Success.TButton",
            command=lambda: self.set_selected_quality("accepted"),
        ).pack(side="right", padx=8)
        ttk.Button(
            actions,
            text="กลับไปรอตรวจ",
            style="Muted.TButton",
            command=lambda: self.set_selected_quality("pending"),
        ).pack(side="right")
        self.quality_tree = ttk.Treeview(
            self.quality_tab,
            columns=("gesture", "signer", "session", "quality", "time", "preview"),
            show="headings",
            selectmode="extended",
            height=9,
        )
        for column, title, width in (
            ("gesture", "คำ/คลาส", 145),
            ("signer", "ผู้ทำท่า", 100),
            ("session", "รอบ", 100),
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
        quick_box = tk.Frame(
            self.readiness_tab,
            background=COLORS["warning_soft"],
            highlightbackground="#f59e0b",
            highlightthickness=1,
        )
        quick_box.pack(fill="x", pady=(0, 10))
        tk.Label(
            quick_box,
            text="โหมดด่วน: เพิ่ม 1 ท่าแล้วทดลองกล้องได้เลย",
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
        header = ttk.Frame(self.experiments_tab, style="Card.TFrame")
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(
            header,
            text="ผลแต่ละรอบถูกเก็บแยกกัน โมเดลหลักจะไม่ถูกเปลี่ยนอัตโนมัติ",
            style="CardMuted.TLabel",
        ).pack(side="left")
        self.open_report_button = ttk.Button(
            header, text="เปิดรายงาน", command=self.open_experiment_report
        )
        self.open_report_button.pack(side="right")
        self.activate_button = ttk.Button(
            header,
            text="ติดตั้งผลที่ผ่าน",
            style="Success.TButton",
            command=self.activate_selected,
        )
        self.activate_button.pack(side="right", padx=8)
        self.test_camera_button = ttk.Button(
            header,
            text="ทดสอบด้วยกล้อง",
            style="Accent.TButton",
            command=self.test_selected_with_camera,
        )
        self.test_camera_button.pack(side="right")
        self.open_report_button.state(["disabled"])
        self.activate_button.state(["disabled"])
        self.test_camera_button.state(["disabled"])
        self.experiment_tree = ttk.Treeview(
            self.experiments_tab,
            columns=("id", "mode", "accuracy", "f1", "passed", "created"),
            show="headings",
            height=11,
        )
        for column, title, width in (
            ("id", "รหัสการทดลอง", 205),
            ("mode", "โหมด", 90),
            ("accuracy", "Accuracy", 100),
            ("f1", "Macro F1", 100),
            ("passed", "ผลเกณฑ์", 100),
            ("created", "วันเวลา", 220),
        ):
            self.experiment_tree.heading(column, text=title)
            self.experiment_tree.column(column, width=width, stretch=column == "created")
        self.experiment_tree.tag_configure("passed", foreground=COLORS["success"])
        self.experiment_tree.tag_configure("failed", foreground=COLORS["danger"])
        experiment_scroll = ttk.Scrollbar(
            self.experiments_tab, orient="vertical", command=self.experiment_tree.yview
        )
        self.experiment_tree.configure(yscrollcommand=experiment_scroll.set)
        experiment_scroll.pack(side="right", fill="y")
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
        sessions = self.config.collection.sessions
        target = self.config.collection.target_clips_per_signer_per_class
        base, remainder = divmod(target, len(sessions))
        return base + (1 if sessions.index(session_id) < remainder else 0)

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
        self.collection_summary_var.set(
            f"{self.gesture_var.get()} · {self.signer_var.get()} · {self.session_var.get()}\n"
            f"มี {usable}/{target} คลิป (ผ่าน {accepted}, รอตรวจ {pending})\n"
            + (f"เหลือเก็บอีก {remaining} คลิป" if remaining else "เก็บครบชุดนี้แล้ว")
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
                f"รอบนี้เพิ่ม “{target}” · เทรนรวม {len(self.config.visible_gestures)} คำ + neutral "
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
        experiments = list_experiments(target_gesture=self.target_var.get())
        self._last_report = report
        self._last_experiments = experiments
        scope_ready_count = self._refresh_scope()
        self._refresh_quality(records)
        self._refresh_readiness(report)
        self._refresh_quick_readiness(quick_report)
        self._refresh_experiments(experiments)
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
                    record.quality,
                    record.recorded_at,
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
                "ระบบจะรวมข้อมูลฐานคำเดิม แล้วสร้างโมเดลทดลองทันที"
            )
            self.quick_train_button.state(["!disabled"])
        else:
            self.quick_summary_var.set(
                f"ต้องมีคลิป accepted ของ “{self.target_var.get()}” อย่างน้อย 4 คลิป "
                f"(ตอนนี้ {target_clips}) — ไม่ต้องเก็บคำเดิมซ้ำ"
            )
            self.quick_train_button.state(["disabled"])

    def _refresh_experiments(self, experiments=None) -> None:
        experiments = experiments if experiments is not None else list_experiments()
        for row in self.experiment_tree.get_children():
            self.experiment_tree.delete(row)
        for item in experiments:
            tag = "passed" if item["passed"] else "failed"
            self.experiment_tree.insert(
                "",
                "end",
                iid=item["id"],
                values=(
                    item["id"],
                    "ด่วน" if item.get("mode") == "quick_trial" else "มาตรฐาน",
                    f"{item['accuracy']:.4f}",
                    f"{item['macro_f1']:.4f}",
                    "ผ่าน" if item["passed"] else "ยังไม่ผ่าน",
                    item["created_at"],
                ),
                tags=(tag,),
            )
        if experiments:
            self.experiment_tree.selection_set(experiments[0]["id"])
            self._update_experiment_actions()
        else:
            self.open_report_button.state(["disabled"])
            self.activate_button.state(["disabled"])
            self.test_camera_button.state(["disabled"])

    def _update_experiment_actions(self, _event=None) -> None:
        item = self._selected_experiment()
        if item is None:
            self.open_report_button.state(["disabled"])
            self.activate_button.state(["disabled"])
            self.test_camera_button.state(["disabled"])
            return
        self.open_report_button.state(["!disabled"])
        if item["passed"]:
            self.activate_button.state(["!disabled"])
            self.test_camera_button.state(["!disabled"])
        else:
            self.activate_button.state(["disabled"])
            self.test_camera_button.state(["disabled"])

    def _refresh_workflow_summary(self, scope_ready_count, records, report, experiments) -> None:
        target = self.config.expected_clip_count
        usable = sum(
            item.gesture_name in self.config.all_classes and item.quality != "rejected"
            for item in records
        )
        accepted = sum(
            item.gesture_name in self.config.all_classes and item.quality == "accepted"
            for item in records
        )
        pending = sum(
            item.gesture_name in self.config.all_classes and item.quality == "pending"
            for item in records
        )
        scope_complete = scope_ready_count == len(self.config.visible_gestures)
        collection_complete = usable >= target
        quality_complete = accepted >= target and pending == 0
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
            f"{usable}/{target} คลิป",
            f"accepted {accepted}",
            "มีผลแล้ว" if has_experiment else ("พร้อมเริ่ม" if report.ready else "รอข้อมูล"),
            "ผ่านเกณฑ์" if latest_passed else ("ต้องปรับ" if has_experiment else "ยังไม่มีผล"),
        )
        for index, (state, detail) in enumerate(zip(stage_states, details)):
            self._set_step_state(index, state, detail)

    def _set_step_state(self, index: int, state: str, detail: str) -> None:
        palette = {
            "complete": (COLORS["success_soft"], COLORS["success"]),
            "current": (COLORS["info_soft"], COLORS["accent"]),
            "review": (COLORS["warning_soft"], COLORS["warning"]),
            "upcoming": (COLORS["neutral_soft"], COLORS["muted"]),
        }
        background, foreground = palette[state]
        self._step_buttons[index].configure(
            text=f"{self.STEP_TITLES[index]}\n{detail}",
            background=background,
            foreground=foreground,
            activebackground=background,
            activeforeground=foreground,
        )

    def start_collection(self) -> None:
        if not messagebox.askyesno(
            "ยืนยันการเปิดกล้อง",
            f"ผู้ทำท่า: {self.signer_var.get()}\n"
            f"รอบ: {self.session_var.get()}\n"
            f"คำ/คลาส: {self.gesture_var.get()}\n\n"
            "ระบบจะเก็บเฉพาะจำนวนที่ยังขาดในชุดนี้ ต้องการเปิดกล้องหรือไม่?",
        ):
            return
        arguments = (
            "--signer", self.signer_var.get(),
            "--session", self.session_var.get(),
            "--gesture", self.gesture_var.get(),
            "--lighting", self.lighting_var.get(),
        )
        try:
            self.app.launcher.launch("collect_v2", arguments)
            self.app.set_status("เปิดเครื่องมือเก็บ Dataset V2 แล้ว — กลับมากดตรวจใหม่เมื่อเก็บเสร็จ")
        except Exception as exc:
            self.app.show_error("เปิดเครื่องมือเก็บข้อมูลไม่สำเร็จ", exc)

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
            "แล้วทดสอบแบบสลับสมาชิก 2 คน\n"
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
            messagebox.showwarning(
                "ข้อมูลโหมดด่วนยังไม่พร้อม",
                f"ต้องมีคลิป accepted ของ “{target}” อย่างน้อย 4 คลิปก่อน",
            )
            self.show_step(2)
            return
        if not messagebox.askyesno(
            "เริ่มเทรนทดลองด่วน",
            f"ระบบจะเพิ่ม “{target}” โดยใช้ข้อมูลฐานของคำเดิมและคลิปคำใหม่นี้\n"
            "ถ้าผลผ่าน ระบบจะสำรองโมเดลเดิม ติดตั้ง และแสดงคำใหม่ทันที "
            "แต่คะแนนยังไม่ถือเป็นผลทดสอบมาตรฐาน\n\n"
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
        if not item["passed"]:
            messagebox.showwarning("ยังไม่ผ่านเกณฑ์", "ติดตั้งได้เฉพาะผลที่ผ่านเกณฑ์")
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

    def test_selected_with_camera(self) -> None:
        """ติดตั้งผลที่เลือกอย่างปลอดภัย แล้วเปิดหน้ากล้องสำหรับทดสอบจริง."""
        item = self._selected_experiment()
        if item is None or not item["passed"]:
            messagebox.showinfo("ยังทดสอบไม่ได้", "เลือกผลที่ผ่านเกณฑ์ก่อน")
            return
        quick_mode = item.get("mode") == "quick_trial"
        if not messagebox.askyesno(
            "ติดตั้งและเปิดกล้องทดสอบ",
            f"ระบบจะสำรองโมเดลเดิม ติดตั้งผล {item['id']} แล้วเปิดกล้อง\n"
            + (
                "ผลนี้เป็นโมเดลทดลองด่วน ใช้ดูการทำงานจริงก่อนเก็บข้อมูลมาตรฐานให้ครบ\n"
                if quick_mode else ""
            )
            + "ต้องการดำเนินการต่อหรือไม่?",
        ):
            return
        try:
            activate_experiment(item["path"], allow_quick_trial=quick_mode)
            self.app.reload_model_state()
            self.app.launcher.launch("detect")
            self.app.set_status("ติดตั้งโมเดลแล้วและเปิดกล้องทดสอบจริง")
        except Exception as exc:
            self.app.show_error("เปิดการทดสอบจริงไม่สำเร็จ", exc)


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
        self.vars: dict[str, tk.Variable] = {
            "camera_index": tk.StringVar(),
            "min_confidence": tk.StringVar(),
            "confirm_frames": tk.StringVar(),
            "release_seconds": tk.StringVar(),
            "speak_hold_seconds": tk.StringVar(),
            "auto_add_words": tk.BooleanVar(),
            "auto_tts": tk.BooleanVar(),
            "tts_volume": tk.StringVar(),
            "font_scale": tk.StringVar(),
            "prevent_duplicate_words": tk.BooleanVar(),
            "save_spoken_sentences": tk.BooleanVar(),
            "history_limit": tk.StringVar(),
        }
        rows = (
            ("camera_index", "หมายเลขกล้อง", "0 คือกล้องหลัก"),
            ("min_confidence", "ความมั่นใจขั้นต่ำ", "0.00–1.00; ปัจจุบันแนะนำ 0.65"),
            ("confirm_frames", "จำนวนเฟรมยืนยัน", "ต้องเห็นท่าติดต่อกันกี่เฟรม"),
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
            )
        ):
            ttk.Checkbutton(form, text=label, variable=self.vars[key]).grid(
                row=bool_start + offset, column=0, columnspan=3, sticky="w", pady=6
            )
        actions = ttk.Frame(form, style="Card.TFrame")
        actions.grid(row=bool_start + 4, column=0, columnspan=3, sticky="ew", pady=(18, 0))
        ttk.Button(actions, text="คืนค่าเริ่มต้น", command=self.reset).pack(side="left")
        ttk.Button(actions, text="บันทึกการตั้งค่า", style="Accent.TButton", command=self.save).pack(side="right")

    def refresh(self) -> None:
        for key, value in asdict(self.app.settings).items():
            self.vars[key].set(value)

    def _settings_from_form(self) -> AppSettings:
        return AppSettings(
            camera_index=int(self.vars["camera_index"].get()),
            min_confidence=float(self.vars["min_confidence"].get()),
            confirm_frames=int(self.vars["confirm_frames"].get()),
            release_seconds=float(self.vars["release_seconds"].get()),
            speak_hold_seconds=float(self.vars["speak_hold_seconds"].get()),
            auto_add_words=bool(self.vars["auto_add_words"].get()),
            auto_tts=bool(self.vars["auto_tts"].get()),
            tts_volume=float(self.vars["tts_volume"].get()),
            font_scale=float(self.vars["font_scale"].get()),
            prevent_duplicate_words=bool(self.vars["prevent_duplicate_words"].get()),
            save_spoken_sentences=bool(self.vars["save_spoken_sentences"].get()),
            history_limit=int(self.vars["history_limit"].get()),
        )

    def save(self) -> None:
        try:
            settings = self._settings_from_form()
            self.app.settings_store.save(settings)
            self.app.apply_settings(settings)
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
                "3. เลือกคำใหม่ครั้งละ 1 คำ แล้วเก็บคำเดิม + คำใหม่ + neutral จากสมาชิก 2 คน\n"
                "4. ตรวจคุณภาพ เทรนรวมข้อมูลสะสม และวัดผลแบบสลับคน",
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
                "หรือเปลี่ยนท่าก่อนคำถัดไป ปุ่มบนหน้ากล้องใช้เพิ่ม ลบ อ่าน บันทึก และล้างได้",
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
        ("dataset", "Dataset V2"),
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
            "dataset": DatasetPage,
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
        for key in ("dashboard", "sentence", "gestures"):
            page = self.pages.get(key)
            if page is not None:
                page.refresh()

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
