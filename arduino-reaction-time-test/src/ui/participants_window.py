"""
Participant registry UI
  – RegisterParticipantDialog  : modal form (name / age / gender)
  – ParticipantsWindow         : full list with stats, accessible from main window
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Callable

from PyQt5.QtCore import Qt, QPointF, QRectF, QStringListModel, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QAction,
    QCheckBox,
    QCompleter,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from src.data.storage import ReactionTimeStorage
else:
    from ..data.storage import ReactionTimeStorage


# ── small helpers ──────────────────────────────────────────────────────────────

def _classify_reaction(ms: float) -> str:
    if ms < 200:
        return "Excellent"
    if ms <= 300:
        return "Normal"
    if ms <= 380:
        return "Slightly Slow"
    return "Delayed"


def _category_color(category: str) -> str:
    return {
        "Excellent":     "#15803a",
        "Normal":        "#1a5699",
        "Slightly Slow": "#b45309",
        "Delayed":       "#b91c1c",
    }.get(category, "#3a607d")


# ── Mini trend chart ───────────────────────────────────────────────────────────

class _MiniTrendWidget(QWidget):
    """
    Painted line graph for the participant detail dialog.
    Hovering within 20 px of any data point shows an inline tooltip with:
      • Trial number  •  Reaction time  •  Category (colour-coded)
    """

    _SNAP_PX = 20

    def __init__(self, values: list[float], parent=None):
        super().__init__(parent)
        self._values = values
        self._points: list = []
        self._hovered_idx: Optional[int] = None
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)

    # ── Mouse events ───────────────────────────────────────────────────────────

    def mouseMoveEvent(self, event):
        if not self._points:
            if self._hovered_idx is not None:
                self._hovered_idx = None
                self.update()
            super().mouseMoveEvent(event)
            return

        mx, my = event.x(), event.y()
        best_idx, best_dist = None, float("inf")
        for i, pt in enumerate(self._points):
            d = ((mx - pt.x()) ** 2 + (my - pt.y()) ** 2) ** 0.5
            if d < best_dist:
                best_dist, best_idx = d, i

        new_idx = best_idx if best_dist <= self._SNAP_PX else None
        if new_idx != self._hovered_idx:
            self._hovered_idx = new_idx
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hovered_idx is not None:
            self._hovered_idx = None
            self.update()
        super().leaveEvent(event)

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _classify(ms: float):
        if ms < 200:
            return "Excellent", QColor("#15803a")
        if ms <= 300:
            return "Normal", QColor("#1a5699")
        if ms <= 380:
            return "Slightly Slow", QColor("#b45309")
        return "Delayed", QColor("#b91c1c")

    def _build_points(self, rect):
        mn     = min(self._values)
        spread = max(max(self._values) - mn, 1.0)
        n      = len(self._values)
        step   = rect.width() / max(n - 1, 1)
        return [
            QPointF(
                rect.left() + idx * step,
                rect.bottom() - ((v - mn) / spread) * rect.height(),
            )
            for idx, v in enumerate(self._values)
        ]

    # ── Paint ──────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if len(self._values) < 2:
            painter.setPen(QPen(QColor("#8aa0ba"), 1))
            painter.drawText(self.rect(), Qt.AlignCenter, "Not enough data for trend")
            self._points = []
            return

        rect = self.rect().adjusted(12, 10, -12, -10)
        if rect.width() <= 0 or rect.height() <= 0:
            return

        mn = min(self._values)
        mx = max(self._values)

        # Cache points for hit-testing.
        self._points = self._build_points(rect)
        points = self._points

        # Grid lines
        painter.setPen(QPen(QColor("#d8e3f0"), 1))
        for i in range(1, 4):
            y = rect.top() + rect.height() * i / 4
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))

        # Data line
        path = QPainterPath(points[0])
        for p in points[1:]:
            path.lineTo(p)
        painter.setPen(QPen(QColor("#2a6ab0"), 2))
        painter.drawPath(path)

        # Dots — highlight the hovered one differently
        for i, p in enumerate(points):
            if i == self._hovered_idx:
                painter.setPen(QPen(QColor("#1050a0"), 2))
                painter.setBrush(QColor("#2a6ab0"))
                painter.drawEllipse(p, 6, 6)
            else:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#2a6ab0"))
                painter.drawEllipse(p, 3, 3)

        # Y-axis labels
        painter.setPen(QPen(QColor("#7a9ab8"), 1))
        font = painter.font()
        font.setPointSize(7)
        painter.setFont(font)
        painter.drawText(rect.left(), rect.top() + 10, f"{mx:.0f}")
        painter.drawText(rect.left(), rect.bottom(), f"{mn:.0f}")

        # ── Hover tooltip ─────────────────────────────────────────────────────
        if self._hovered_idx is None:
            return

        idx      = self._hovered_idx
        pt       = points[idx]
        value    = self._values[idx]
        category, cat_color = self._classify(value)

        TW, TH, PAD = 124, 66, 8

        tx = pt.x() + 14
        if tx + TW > rect.right() + 12:
            tx = pt.x() - TW - 14
        ty = pt.y() - TH / 2
        ty = max(float(rect.top()), min(ty, float(rect.bottom()) - TH))
        box = QRectF(tx, ty, TW, TH)

        # Drop shadow
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 28))
        painter.drawRoundedRect(box.adjusted(2, 2, 2, 2), 7, 7)

        # Background + border
        painter.setPen(QPen(QColor("#bcd0e8"), 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(box, 7, 7)

        base_font = painter.font()

        # Trial label
        f = painter.font()
        f.setPointSize(8)
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(QPen(QColor("#5a7a9a")))
        painter.drawText(
            QRectF(box.left() + PAD, box.top() + 7, TW - PAD * 2, 15),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"Trial #{idx + 1}",
        )

        # RT value
        f.setPointSize(13)
        painter.setFont(f)
        painter.setPen(QPen(QColor("#1a3a5a")))
        painter.drawText(
            QRectF(box.left() + PAD, box.top() + 22, TW - PAD * 2, 22),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"{value:.1f} ms",
        )

        # Category
        f.setPointSize(8)
        f.setBold(False)
        painter.setFont(f)
        painter.setPen(QPen(cat_color))
        painter.drawText(
            QRectF(box.left() + PAD, box.top() + 45, TW - PAD * 2, 14),
            Qt.AlignLeft | Qt.AlignVCenter,
            category,
        )

        painter.setFont(base_font)


# ── Participant Detail Dialog ──────────────────────────────────────────────────

class ParticipantDetailDialog(QDialog):
    """Shows full profile + reaction-time history for one participant."""

    def __init__(self, storage: "ReactionTimeStorage", name: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.storage = storage
        self.participant_name = name
        self.setWindowTitle(f"Details — {name}")
        self.setMinimumSize(640, 560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._build()

    # ── layout ─────────────────────────────────────────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout()
        root.setSpacing(10)
        root.setContentsMargins(0, 0, 0, 0)
        self.setLayout(root)

        p    = self.storage.get_participant(self.participant_name)
        stats = self.storage.get_participant_stats(self.participant_name)
        rows  = self.storage.get_participant_reaction_times(self.participant_name)

        name    = p["name"]   if p else self.participant_name
        age     = str(p["age"]) if (p and p["age"]) else "—"
        gender  = (p["gender"] or "—") if p else "—"
        profession = (p["profession"] or "—") if p else "—"
        reg     = ((p["registered_at"] or "")[:10]) if p else "—"
        trials  = int(stats["trials"]) if stats else 0
        avg_rt  = stats["avg_rt"]  if (stats and stats["avg_rt"])  else None
        best_rt = stats["best_rt"] if (stats and stats["best_rt"]) else None
        category = _classify_reaction(avg_rt) if avg_rt else "—"

        # ── Header ──
        header_frame = QFrame()
        header_frame.setObjectName("StatusStrip")
        header_frame.setFixedHeight(52)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(16, 6, 16, 6)
        header_layout.setSpacing(10)
        header_frame.setLayout(header_layout)

        icon = QLabel("👤")
        icon.setObjectName("StatusIcon")
        header_layout.addWidget(icon)

        title = QLabel(name)
        title.setObjectName("StatusTitle")
        header_layout.addWidget(title)
        header_layout.addStretch(1)

        if avg_rt is not None:
            badge = QLabel(category)
            badge.setObjectName("StatusChip")
            color = _category_color(category)
            badge.setStyleSheet(
                f"color: {color}; border: 1px solid {color};"
                "border-radius: 10px; padding: 2px 10px; font-weight: bold;"
            )
            header_layout.addWidget(badge)
        root.addWidget(header_frame)

        # ── Body (padded) ──
        body = QVBoxLayout()
        body.setSpacing(10)
        body.setContentsMargins(14, 6, 14, 14)
        root.addLayout(body)

        # ── Info cards ──
        info_row = QHBoxLayout()
        info_row.setSpacing(8)
        for label, value in [
            ("Age",        age),
            ("Gender",     gender),
            ("Profession", profession),
            ("Registered", reg),
            ("Trials",     str(trials)),
            ("Avg RT",     f"{avg_rt:.1f} ms" if avg_rt else "—"),
            ("Best RT",    f"{best_rt:.1f} ms" if best_rt else "—"),
        ]:
            card = QFrame()
            card.setObjectName("MetricCard")
            card_lay = QVBoxLayout()
            card_lay.setContentsMargins(10, 8, 10, 8)
            card_lay.setSpacing(2)
            card.setLayout(card_lay)
            lbl = QLabel(label)
            lbl.setObjectName("MetricLabel")
            val = QLabel(value)
            val.setObjectName("MetricValue")
            card_lay.addWidget(lbl)
            card_lay.addWidget(val)
            info_row.addWidget(card, stretch=1)
        body.addLayout(info_row)

        # ── Participant UUID ──────────────────────────────────────────────────
        if p and p["participant_uuid"]:
            uid_label = QLabel(f"Participant ID:  {p['participant_uuid']}")
            uid_label.setObjectName("MetricLabel")
            uid_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            uid_label.setStyleSheet(
                "color: #7a9ab8; font-size: 10px; font-family: monospace; padding: 2px 0;"
            )
            body.addWidget(uid_label)

        # ── Trend chart ──
        rt_values = [float(r["reaction_time"]) for r in rows]
        if rt_values:
            trend_label = QLabel("Reaction Time Trend")
            trend_label.setObjectName("MetricLabel")
            body.addWidget(trend_label)
            chart = _MiniTrendWidget(rt_values)
            body.addWidget(chart)

        # ── History table ──
        hist_label = QLabel("Trial History")
        hist_label.setObjectName("MetricLabel")
        body.addWidget(hist_label)

        hist_table = QTableWidget(len(rows), 3)
        hist_table.setObjectName("HistoryTable")
        hist_table.setHorizontalHeaderLabels(["Timestamp", "Reaction Time (ms)", "Category"])
        hist_table.setEditTriggers(QTableWidget.NoEditTriggers)
        hist_table.setSelectionBehavior(QTableWidget.SelectRows)
        hist_table.setAlternatingRowColors(True)
        hist_table.setShowGrid(False)
        hist_table.verticalHeader().setVisible(False)
        hist_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        hist_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hist_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

        for i, r in enumerate(reversed(rows)):   # newest first
            ts  = str(r["timestamp"])[:19].replace("T", "  ")
            rt  = float(r["reaction_time"])
            cat = _classify_reaction(rt)
            ts_item  = QTableWidgetItem(ts)
            rt_item  = QTableWidgetItem(f"{rt:.1f}")
            cat_item = QTableWidgetItem(cat)
            rt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            cat_item.setTextAlignment(Qt.AlignCenter)
            cat_item.setForeground(QColor(_category_color(cat)))
            hist_table.setItem(i, 0, ts_item)
            hist_table.setItem(i, 1, rt_item)
            hist_table.setItem(i, 2, cat_item)

        body.addWidget(hist_table, stretch=1)

        # ── Close button ──
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("SecondaryButton")
        close_btn.setFixedHeight(32)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        body.addLayout(btn_row)


import uuid as _uuid

# ── Registration dialog ────────────────────────────────────────────────────────

class RegisterParticipantDialog(QDialog):
    """
    Modal dialog that collects name, age, gender, and profession.
    If `prefill_name` is given the name field is pre-populated.
    Emits `registered(name, age, gender, profession)` when confirmed.

    HCI design principles applied
    ──────────────────────────────
    • Live duplicate detection  — inline error appears as the user types,
      before they ever press Register.
    • Register button disabled  — while a validation error exists the button
      is greyed out and cannot be clicked.
    • Unique Participant ID      — shown as a read-only preview inside the form.
    • Hard block in _on_accept  — catches any paste-then-submit bypass.
    • Contextual button label   — shows "Edit" when editing self.
    """

    registered = pyqtSignal(str, int, str, str)  # name, age, gender, profession

    def __init__(
        self,
        storage: ReactionTimeStorage,
        prefill_name: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.storage = storage
        self._prefill_name = prefill_name   # original name when editing

        # Determine UUID upfront:
        #   • editing an existing participant → reuse their stored UUID
        #   • new registration               → generate a fresh one now
        _existing_on_open = self.storage.get_participant(prefill_name) if prefill_name else None
        self._assigned_uuid: str = (
            _existing_on_open["participant_uuid"]
            if (_existing_on_open and _existing_on_open["participant_uuid"])
            else str(_uuid.uuid4())
        )

        self.setWindowTitle("Register Participant")
        self.setMinimumWidth(460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._build()

        # Pre-fill fields when editing an existing participant.
        if prefill_name:
            self.name_input.setText(prefill_name)
        if _existing_on_open:
            self.age_spin.setValue(int(_existing_on_open["age"] or 0))
            idx = self.gender_combo.findText(_existing_on_open["gender"] or "")
            if idx >= 0:
                self.gender_combo.setCurrentIndex(idx)
            self.profession_input.setText(_existing_on_open["profession"] or "")

        # Wire live validation AFTER fields are set to avoid spurious errors.
        self.name_input.textChanged.connect(self._validate_name_live)
        self._validate_name_live(self.name_input.text())

    # ── UI construction ────────────────────────────────────────────────────────

    def _build(self) -> None:
        layout = QVBoxLayout()
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)
        self.setLayout(layout)

        # ── Header ──
        header = QLabel("Participant Registration")
        header.setObjectName("DialogHeader")
        layout.addWidget(header)

        sub = QLabel(
            "Please enter the participant\u2019s details below.\n"
            "This information supports health monitoring and reaction-time analysis."
        )
        sub.setObjectName("DialogSubtext")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("SetupDivider")
        layout.addWidget(sep)

        # ── Form fields ──
        form_widget = QWidget()
        form_layout = QVBoxLayout()
        form_layout.setSpacing(10)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_widget.setLayout(form_layout)

        def _req_label(text: str) -> QLabel:
            lbl = QLabel(f"{text}  <span style='color:#c0392b;'>*</span>")
            lbl.setTextFormat(Qt.RichText)
            return lbl

        # ── Name field ──
        form_layout.addWidget(_req_label("Full Name"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Juan dela Cruz")
        _existing_names = [p["name"] for p in self.storage.get_all_participants()]
        _dlg_completer = QCompleter(_existing_names, self.name_input)
        _dlg_completer.setCaseSensitivity(Qt.CaseInsensitive)
        _dlg_completer.setFilterMode(Qt.MatchContains)
        _dlg_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.name_input.setCompleter(_dlg_completer)
        form_layout.addWidget(self.name_input)

        # Inline duplicate / required error — hidden until a problem is detected.
        self._name_error_label = QLabel()
        self._name_error_label.setWordWrap(True)
        self._name_error_label.setTextFormat(Qt.RichText)
        self._name_error_label.setStyleSheet(
            "color: #b91c1c; font-size: 11px; padding: 4px 8px;"
            "background: #fef2f2; border: 1px solid #fca5a5; border-radius: 4px;"
        )
        self._name_error_label.hide()
        form_layout.addWidget(self._name_error_label)

        # ── Participant ID (read-only preview) ──
        id_row = QHBoxLayout()
        id_row.setSpacing(8)
        id_lbl = QLabel("Participant ID")
        id_lbl.setObjectName("MetricLabel")
        id_lbl.setFixedWidth(100)
        self._id_display = QLineEdit(self._assigned_uuid)
        self._id_display.setReadOnly(True)
        self._id_display.setStyleSheet(
            "color: #4a6a8a; background: #f1f5f9;"
            "border: 1px solid #cbd5e1; border-radius: 4px;"
            "font-family: monospace; font-size: 10px; padding: 2px 6px;"
        )
        self._id_display.setToolTip(
            "Auto-generated unique identifier for this participant.\n"
            "This ID is permanent and never changes, even if the name is updated."
        )
        id_row.addWidget(id_lbl)
        id_row.addWidget(self._id_display)
        form_layout.addLayout(id_row)

        # ── Age / Gender row ──
        age_row = QHBoxLayout()
        age_row.setSpacing(12)

        age_col = QVBoxLayout()
        age_col.setSpacing(4)
        age_col.addWidget(_req_label("Age"))
        self.age_spin = QSpinBox()
        self.age_spin.setRange(1, 120)
        self.age_spin.setValue(20)
        self.age_spin.setSuffix(" yrs")
        age_col.addWidget(self.age_spin)
        age_row.addLayout(age_col)

        gender_col = QVBoxLayout()
        gender_col.setSpacing(4)
        gender_col.addWidget(_req_label("Gender"))
        self.gender_combo = QComboBox()
        self.gender_combo.addItems(["— Select gender —", "Male", "Female",
                                    "Non-binary", "Prefer not to say"])
        gender_col.addWidget(self.gender_combo)
        age_row.addLayout(gender_col)

        form_layout.addLayout(age_row)

        # ── Profession (optional) ──
        prof_label = QLabel("Profession  <span style='color:#7a9ab8; font-size:10px;'>(optional)</span>")
        prof_label.setTextFormat(Qt.RichText)
        form_layout.addWidget(prof_label)
        self.profession_input = QLineEdit()
        self.profession_input.setPlaceholderText("e.g. Student, Engineer, Teacher\u2026")
        form_layout.addWidget(self.profession_input)

        layout.addWidget(form_widget)

        req_note = QLabel("<span style='color:#c0392b;'>*</span>  Required fields")
        req_note.setTextFormat(Qt.RichText)
        req_note.setObjectName("DialogSubtext")
        layout.addWidget(req_note)

        note = QLabel(
            "\u24d8  Reaction time is a simple, accessible indicator of brain and motor health.\n"
            "      Early tracking helps detect cognitive changes before they become serious."
        )
        note.setObjectName("DialogNote")
        note.setWordWrap(True)
        layout.addWidget(note)

        # ── Buttons ──
        btn_box = QDialogButtonBox()
        self.ok_btn = QPushButton("Register")
        self.ok_btn.setObjectName("PrimaryButton")
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("SecondaryButton")
        btn_box.addButton(self.ok_btn, QDialogButtonBox.AcceptRole)
        btn_box.addButton(self.cancel_btn, QDialogButtonBox.RejectRole)
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    # ── Live validation ────────────────────────────────────────────────────────

    def _validate_name_live(self, text: str) -> None:
        """
        Called on every keystroke.  Shows/hides the inline error label and
        enables/disables the Register button in real time.

        Rules
        ─────
        • Blank input     → neutral (empty-check fires at submit time only).
        • Editing self    → always allowed; show their existing UUID; label "Edit".
        • New duplicate   → show inline error with conflicting ID; disable button.
        • New unique name → clear error; show preview UUID; enable button.
        """
        name = text.strip()

        if not name:
            self._clear_name_error()
            self._id_display.setText(self._assigned_uuid)
            self.ok_btn.setText("Register")
            self.ok_btn.setEnabled(True)
            return

        is_editing_self = bool(
            self._prefill_name
            and self._prefill_name.lower() == name.lower()
        )
        if is_editing_self:
            self._clear_name_error()
            self._id_display.setText(self._assigned_uuid)
            self.ok_btn.setText("Edit")
            self.ok_btn.setEnabled(True)
            return

        conflict = self.storage.get_participant_ci(name)
        if conflict:
            uid = conflict["participant_uuid"] or "\u2014"
            canonical = conflict["name"]
            self._show_name_error(
                f"<b>\u26a0\ufe0f &nbsp;Duplicate name:</b> &nbsp;"
                f"\u201c{canonical}\u201d is already registered.<br>"
                f"<span style='font-family:monospace; font-size:10px;'>"
                f"Participant ID: {uid}</span><br>"
                "Choose a different name, or open <i>View Participants</i> "
                "to load and edit the existing record."
            )
            self._id_display.setText(uid)   # show the conflicting participant's ID
            self.ok_btn.setEnabled(False)
            self.ok_btn.setText("Register")
        else:
            self._clear_name_error()
            self._id_display.setText(self._assigned_uuid)
            self.ok_btn.setText("Register")
            self.ok_btn.setEnabled(True)

    def _show_name_error(self, html: str) -> None:
        self._name_error_label.setText(html)
        self._name_error_label.show()
        self.name_input.setStyleSheet("border: 1.5px solid #ef4444;")
        self.adjustSize()

    def _clear_name_error(self) -> None:
        self._name_error_label.hide()
        self._name_error_label.clear()
        self.name_input.setStyleSheet("")

    # ── Submit ─────────────────────────────────────────────────────────────────

    def _on_accept(self) -> None:
        name = self.name_input.text().strip()

        # Required-field: name
        if not name:
            self._show_name_error(
                "<b>\u26a0\ufe0f &nbsp;Name is required.</b>"
                " Please enter the participant\u2019s full name."
            )
            self.name_input.setFocus()
            return

        # Required-field: gender
        if self.gender_combo.currentIndex() == 0:
            QMessageBox.warning(self, "Required Field", "Please select a gender.")
            self.gender_combo.setFocus()
            return

        # Hard duplicate guard — catches paste-then-submit bypasses.
        is_editing_self = bool(
            self._prefill_name
            and self._prefill_name.lower() == name.lower()
        )
        if not is_editing_self and self.storage.get_participant_ci(name):
            self._validate_name_live(name)   # re-show the inline error
            self.name_input.setFocus()
            return

        age        = self.age_spin.value()
        gender     = self.gender_combo.currentText()
        profession = self.profession_input.text().strip()
        self.storage.save_participant(name, age, gender, profession)
        self.registered.emit(name, age, gender, profession)
        self.accept()

    def get_values(self):
        """Convenience accessor after accept()."""
        return (
            self.name_input.text().strip(),
            self.age_spin.value(),
            self.gender_combo.currentText(),
            self.profession_input.text().strip(),
        )


# ── Participants list window ───────────────────────────────────────────────────

class ParticipantsWindow(QMainWindow):
    """
    Stand-alone window showing all registered participants with their
    demographics and session statistics.
    """

    participant_selected = pyqtSignal(str)  # emitted when user clicks "Load"

    COLS = ["Name", "Age", "Gender", "Registered", "Trials", "Avg RT (ms)", "Best RT (ms)", "Category"]

    def __init__(
        self,
        storage: ReactionTimeStorage,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.storage = storage
        self.setWindowTitle("Registered Participants")
        self.setMinimumSize(820, 520)
        self.resize(960, 580)
        self._build()
        self.refresh()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build(self) -> None:
        central = QWidget()
        central.setObjectName("MainContainer")
        self.setCentralWidget(central)

        root = QVBoxLayout()
        root.setSpacing(10)
        root.setContentsMargins(14, 14, 14, 14)
        central.setLayout(root)

        # Header
        hdr = QFrame()
        hdr.setObjectName("StatusStrip")
        hdr.setFixedHeight(46)
        hdr_layout = QHBoxLayout()
        hdr_layout.setContentsMargins(14, 4, 14, 4)
        hdr_layout.setSpacing(10)
        hdr.setLayout(hdr_layout)

        icon = QLabel("👥")
        icon.setObjectName("StatusIcon")
        hdr_layout.addWidget(icon)

        title = QLabel("Participant Registry")
        title.setObjectName("StatusTitle")
        hdr_layout.addWidget(title)
        hdr_layout.addStretch(1)

        self.count_chip = QLabel()
        self.count_chip.setObjectName("StatusChip")
        hdr_layout.addWidget(self.count_chip)

        root.addWidget(hdr)

        # Context card
        ctx_card = QGroupBox("About This Registry")
        ctx_card.setObjectName("SectionCard")
        ctx_layout = QVBoxLayout()
        ctx_layout.setContentsMargins(12, 10, 12, 10)
        ctx_layout.setSpacing(4)
        ctx_card.setLayout(ctx_layout)

        ctx_text = QLabel(
            "This registry stores participants for the Arduino Reaction-Time Tester — a tool designed "
            "to make monitoring of brain and motor health accessible in daily life. "
            "Reaction time (RT) is a simple but powerful indicator of cognitive function: "
            "slower or inconsistent RT can signal cognitive decline, neurological issues, or increased health risks. "
            "Tracking participants over time supports preventive care and community wellness."
        )
        ctx_text.setObjectName("DialogSubtext")
        ctx_text.setWordWrap(True)
        ctx_layout.addWidget(ctx_text)
        root.addWidget(ctx_card)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search participant…")
        self.search_input.textChanged.connect(self._on_search)
        self._search_completer_model = QStringListModel()
        self._search_completer = QCompleter(self._search_completer_model, self.search_input)
        self._search_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._search_completer.setFilterMode(Qt.MatchContains)
        self._search_completer.setCompletionMode(QCompleter.PopupCompletion)
        # Selecting a suggestion immediately loads that participant.
        self._search_completer.activated.connect(self._select_and_load_by_name)
        self.search_input.setCompleter(self._search_completer)
        toolbar.addWidget(self.search_input, stretch=1)

        self.add_btn = QPushButton("➕  Add Participant")
        self.add_btn.setObjectName("PrimaryButton")
        self.add_btn.clicked.connect(self._open_add_dialog)
        toolbar.addWidget(self.add_btn)

        self.refresh_btn = QPushButton("⟳  Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self.refresh_btn)

        root.addLayout(toolbar)

        # Table
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setObjectName("HistoryTable")
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, len(self.COLS)):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.doubleClicked.connect(self._on_row_double_clicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        root.addWidget(self.table, stretch=1)

        # Bottom bar
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        tip = QLabel("Double-click a row to load that participant into the main session.")
        tip.setObjectName("DialogSubtext")
        bottom.addWidget(tip, stretch=1)

        self.edit_btn = QPushButton("✏️  Edit Selected")
        self.edit_btn.setObjectName("SecondaryButton")
        self.edit_btn.setFixedHeight(34)
        self.edit_btn.setToolTip("Open the registration form to edit the selected participant's details.")
        self.edit_btn.clicked.connect(self._edit_selected)
        bottom.addWidget(self.edit_btn)

        self.load_btn = QPushButton("Load Selected →")
        self.load_btn.setObjectName("PrimaryActionButton")
        self.load_btn.setFixedHeight(34)
        self.load_btn.clicked.connect(self._load_selected)
        bottom.addWidget(self.load_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("SecondaryButton")
        self.close_btn.setFixedHeight(34)
        self.close_btn.clicked.connect(self.close)
        bottom.addWidget(self.close_btn)

        root.addLayout(bottom)

    # ── Data ───────────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        participants = self.storage.get_all_participants()
        self._populate(participants)

    def _populate(self, participants) -> None:
        self.table.setRowCount(0)
        for row_idx, p in enumerate(participants):
            name    = p["name"]
            age     = str(p["age"]) if p["age"] else "—"
            gender  = p["gender"] or "—"
            reg     = (p["registered_at"] or "")[:10]

            stats   = self.storage.get_participant_stats(name)
            trials  = str(stats["trials"]) if stats else "0"
            avg_rt  = f"{stats['avg_rt']:.1f}" if (stats and stats["avg_rt"]) else "—"
            best_rt = f"{stats['best_rt']:.1f}" if (stats and stats["best_rt"]) else "—"
            category = _classify_reaction(stats["avg_rt"]) if (stats and stats["avg_rt"]) else "—"

            values = [name, age, gender, reg, trials, avg_rt, best_rt, category]
            self.table.insertRow(row_idx)
            for col_idx, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter if col_idx > 0 else Qt.AlignLeft | Qt.AlignVCenter)
                if col_idx == 0:
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                if col_idx == len(values) - 1:
                    color_map = {
                        "Excellent": QColor("#15693a"),
                        "Normal":    QColor("#1a5699"),
                        "Slightly Slow": QColor("#8a4800"),
                        "Delayed":   QColor("#a81510"),
                    }
                    item.setForeground(color_map.get(category, QColor("#3a607d")))
                self.table.setItem(row_idx, col_idx, item)

        count = self.table.rowCount()
        self.count_chip.setText(f"{count} participant{'s' if count != 1 else ''}")
        # Keep the search bar completer in sync with current participant names.
        names = [self.table.item(r, 0).text()
                 for r in range(self.table.rowCount())
                 if self.table.item(r, 0)]
        self._search_completer_model.setStringList(names)

    def _on_search(self, text: str) -> None:
        text = text.strip().lower()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            name = item.text().lower() if item else ""
            self.table.setRowHidden(row, bool(text and text not in name))

    def _select_and_load_by_name(self, name: str) -> None:
        """Select the row matching `name` and immediately load the participant."""
        # Un-hide all rows first so the target row is reachable.
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, False)
        # Find and select the row.
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.text() == name:
                self.table.selectRow(row)
                break
        self._load_selected()

    def _open_add_dialog(self) -> None:
        dlg = RegisterParticipantDialog(self.storage, parent=self)
        dlg.registered.connect(lambda *_: self.refresh())
        dlg.exec_()

    def _edit_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(
                self, "Edit Participant",
                "Please select a participant from the list first."
            )
            return
        name_item = self.table.item(rows[0].row(), 0)
        if name_item:
            self._open_edit_dialog(name_item.text())

    def _open_edit_dialog(self, name: str) -> None:
        dlg = RegisterParticipantDialog(self.storage, prefill_name=name, parent=self)
        dlg.registered.connect(lambda *_: self.refresh())
        dlg.exec_()

    def _show_context_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        name_item = self.table.item(index.row(), 0)
        if not name_item:
            return
        name = name_item.text()

        menu = QMenu(self)
        view_action = QAction(f"📋  View Details — {name}", self)
        view_action.triggered.connect(lambda: self._open_detail_dialog(name))
        menu.addAction(view_action)
        edit_action = QAction("✏️  Edit Details", self)
        edit_action.triggered.connect(lambda: self._open_edit_dialog(name))
        menu.addAction(edit_action)
        menu.addSeparator()
        load_action = QAction("▶  Load into Session", self)
        load_action.triggered.connect(lambda: self._select_and_load_by_name(name))
        menu.addAction(load_action)
        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def _open_detail_dialog(self, name: str) -> None:
        dlg = ParticipantDetailDialog(self.storage, name, parent=self)
        dlg.exec_()

    def _on_row_double_clicked(self, index) -> None:
        self._load_selected()

    def _load_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Load Participant", "Please select a participant from the list.")
            return
        name_item = self.table.item(rows[0].row(), 0)
        if name_item:
            self.participant_selected.emit(name_item.text())
            self.close()
