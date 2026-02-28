"""
Participant registry UI
  – RegisterParticipantDialog  : modal form (name / age / gender)
  – ParticipantsWindow         : full list with stats, accessible from main window
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Callable

from PyQt5.QtCore import Qt, QPointF, QStringListModel, pyqtSignal
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
    """Lightweight painted line graph for the detail dialog."""

    def __init__(self, values: list[float], parent=None):
        super().__init__(parent)
        self._values = values
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if len(self._values) < 2:
            painter.setPen(QPen(QColor("#8aa0ba"), 1))
            painter.drawText(self.rect(), Qt.AlignCenter, "Not enough data for trend")
            return

        rect = self.rect().adjusted(12, 10, -12, -10)
        if rect.width() <= 0 or rect.height() <= 0:
            return

        mn = min(self._values)
        mx = max(self._values)
        spread = max(mx - mn, 1.0)

        # Grid lines
        painter.setPen(QPen(QColor("#d8e3f0"), 1))
        for i in range(1, 4):
            y = rect.top() + rect.height() * i / 4
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))

        # Data line
        n = len(self._values)
        step = rect.width() / max(n - 1, 1)
        points = []
        for idx, v in enumerate(self._values):
            x = rect.left() + idx * step
            y = rect.bottom() - ((v - mn) / spread) * rect.height()
            points.append(QPointF(x, y))

        path = QPainterPath(points[0])
        for p in points[1:]:
            path.lineTo(p)

        painter.setPen(QPen(QColor("#2a6ab0"), 2))
        painter.drawPath(path)

        # Dots
        painter.setBrush(QColor("#2a6ab0"))
        painter.setPen(Qt.NoPen)
        for p in points:
            painter.drawEllipse(p, 3, 3)

        # Y-axis labels
        painter.setPen(QPen(QColor("#7a9ab8"), 1))
        font = painter.font()
        font.setPointSize(7)
        painter.setFont(font)
        painter.drawText(rect.left(), rect.top() + 10, f"{mx:.0f}")
        painter.drawText(rect.left(), rect.bottom(), f"{mn:.0f}")


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


# ── Registration dialog ────────────────────────────────────────────────────────

class RegisterParticipantDialog(QDialog):
    """
    Modal dialog that collects name, age, and gender.
    If `prefill_name` is given the name field is pre-populated (and locked).
    Emits `registered(name, age, gender)` when confirmed.
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
        self.setWindowTitle("Register Participant")
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._build()
        if prefill_name:
            self.name_input.setText(prefill_name)
        # Always pre-fill existing data so editing is easy
        existing = self.storage.get_participant(prefill_name) if prefill_name else None
        if existing:
            self.age_spin.setValue(int(existing["age"] or 0))
            idx = self.gender_combo.findText(existing["gender"] or "")
            if idx >= 0:
                self.gender_combo.setCurrentIndex(idx)
            self.profession_input.setText(existing["profession"] or "")

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
            "Please enter the participant's details below.\n"
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

        # Required marker helper
        def _req_label(text: str) -> QLabel:
            lbl = QLabel(f"{text}  <span style='color:#c0392b;'>*</span>")
            lbl.setTextFormat(Qt.RichText)
            return lbl

        form_layout.addWidget(_req_label("Full Name"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Juan dela Cruz")
        # Completer from existing participants
        _existing_names = [p["name"] for p in self.storage.get_all_participants()]
        _dlg_completer = QCompleter(_existing_names, self.name_input)
        _dlg_completer.setCaseSensitivity(Qt.CaseInsensitive)
        _dlg_completer.setFilterMode(Qt.MatchContains)
        _dlg_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.name_input.setCompleter(_dlg_completer)
        form_layout.addWidget(self.name_input)

        age_row = QHBoxLayout()
        age_row.setSpacing(12)

        age_col = QVBoxLayout()
        age_col.setSpacing(4)
        age_col.addWidget(_req_label("Age"))
        self.age_spin = QSpinBox()
        self.age_spin.setRange(1, 120)
        self.age_spin.setValue(20)
        self.age_spin.setSuffix(" yrs")
        self.age_spin.setSpecialValueText("")  # no special text
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

        # Profession (optional)
        prof_label = QLabel("Profession  <span style='color:#7a9ab8; font-size:10px;'>(optional)</span>")
        prof_label.setTextFormat(Qt.RichText)
        form_layout.addWidget(prof_label)
        self.profession_input = QLineEdit()
        self.profession_input.setPlaceholderText("e.g. Student, Engineer, Teacher…")
        form_layout.addWidget(self.profession_input)

        layout.addWidget(form_widget)

        # Required note
        req_note = QLabel("<span style='color:#c0392b;'>*</span>  Required fields")
        req_note.setTextFormat(Qt.RichText)
        req_note.setObjectName("DialogSubtext")
        layout.addWidget(req_note)

        # ── Context note ──
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

    def _on_accept(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Required Field", "Please enter the participant's full name.")
            self.name_input.setFocus()
            return
        if self.gender_combo.currentIndex() == 0:
            QMessageBox.warning(self, "Required Field", "Please select a gender.")
            self.gender_combo.setFocus()
            return
        age = self.age_spin.value()
        gender = self.gender_combo.currentText()
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
