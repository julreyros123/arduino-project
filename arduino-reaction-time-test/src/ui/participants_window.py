"""
Participant registry UI
  – RegisterParticipantDialog  : modal form (name / age / gender)
  – ParticipantsWindow         : full list with stats, accessible from main window
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Callable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QCheckBox,
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


# ── Registration dialog ────────────────────────────────────────────────────────

class RegisterParticipantDialog(QDialog):
    """
    Modal dialog that collects name, age, and gender.
    If `prefill_name` is given the name field is pre-populated (and locked).
    Emits `registered(name, age, gender)` when confirmed.
    """

    registered = pyqtSignal(str, int, str)

    def __init__(
        self,
        storage: ReactionTimeStorage,
        prefill_name: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.storage = storage
        self.setWindowTitle("Register Participant")
        self.setMinimumWidth(380)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._build()
        if prefill_name:
            self.name_input.setText(prefill_name)
            # pre-fill existing data if participant already registered
            existing = self.storage.get_participant(prefill_name)
            if existing:
                self.age_spin.setValue(int(existing["age"] or 0))
                idx = self.gender_combo.findText(existing["gender"] or "")
                if idx >= 0:
                    self.gender_combo.setCurrentIndex(idx)

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

        form_layout.addWidget(QLabel("Full Name"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Juan dela Cruz")
        form_layout.addWidget(self.name_input)

        age_row = QHBoxLayout()
        age_row.setSpacing(12)

        age_col = QVBoxLayout()
        age_col.setSpacing(4)
        age_col.addWidget(QLabel("Age"))
        self.age_spin = QSpinBox()
        self.age_spin.setRange(5, 120)
        self.age_spin.setValue(20)
        self.age_spin.setSuffix(" yrs")
        age_col.addWidget(self.age_spin)
        age_row.addLayout(age_col)

        gender_col = QVBoxLayout()
        gender_col.setSpacing(4)
        gender_col.addWidget(QLabel("Gender"))
        self.gender_combo = QComboBox()
        self.gender_combo.addItems(["Male", "Female", "Non-binary", "Prefer not to say"])
        gender_col.addWidget(self.gender_combo)
        age_row.addLayout(gender_col)

        form_layout.addLayout(age_row)
        layout.addWidget(form_widget)

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
            QMessageBox.warning(self, "Validation", "Please enter a participant name.")
            return
        age = self.age_spin.value()
        gender = self.gender_combo.currentText()
        self.storage.save_participant(name, age, gender)
        self.registered.emit(name, age, gender)
        self.accept()

    def get_values(self):
        """Convenience accessor after accept()."""
        return (
            self.name_input.text().strip(),
            self.age_spin.value(),
            self.gender_combo.currentText(),
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

    def _on_search(self, text: str) -> None:
        text = text.strip().lower()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            name = item.text().lower() if item else ""
            self.table.setRowHidden(row, bool(text and text not in name))

    def _open_add_dialog(self) -> None:
        dlg = RegisterParticipantDialog(self.storage, parent=self)
        dlg.registered.connect(lambda *_: self.refresh())
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
