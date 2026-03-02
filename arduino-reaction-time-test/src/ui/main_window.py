import sys
import time
import uuid
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QPointF, QRectF, QSize, QStringListModel, Qt, QTimer
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
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
    from src.utils.serial_handler import SerialHandler
    from src.ui.participants_window import ParticipantsWindow, RegisterParticipantDialog
else:
    from ..data.storage import ReactionTimeStorage
    from ..utils.serial_handler import SerialHandler
    from .participants_window import ParticipantsWindow, RegisterParticipantDialog

try:
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    list_ports = None

ARDUINO_BAUD_RATE = 9600
SESSION_TRIALS = 5


def _connect_signal(signal, slot):
    connector = getattr(signal, "connect", None)
    if callable(connector):
        connector(slot)


class ReactionTrendWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._values = []
        self.setObjectName("TrendGraph")
        self.setMinimumHeight(140)

    def set_values(self, values):
        self._values = list(values[-30:])
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if len(self._values) < 2:
            painter.setPen(QPen(QColor("#8aa0ba"), 1))
            painter.drawText(self.rect(), Qt.AlignCenter, "Need more data for trend")
            return

        rect = self.rect().adjusted(14, 14, -14, -14)
        if rect.width() <= 0 or rect.height() <= 0:
            return

        minimum = min(self._values)
        maximum = max(self._values)
        spread = max(maximum - minimum, 1.0)

        painter.setPen(QPen(QColor("#d8e3f0"), 1))
        for line in range(1, 4):
            y = rect.top() + (rect.height() * line / 4)
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))

        count = len(self._values)
        step_x = rect.width() / max(count - 1, 1)
        points = []
        for idx, value in enumerate(self._values):
            norm = (value - minimum) / spread
            x = rect.left() + (idx * step_x)
            y = rect.bottom() - (norm * rect.height())
            points.append(QPointF(x, y))

        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.setPen(QPen(QColor("#2f80ed"), 2))
        painter.drawPath(path)

        fill_path = QPainterPath(path)
        fill_path.lineTo(points[-1].x(), rect.bottom())
        fill_path.lineTo(points[0].x(), rect.bottom())
        fill_path.closeSubpath()
        painter.fillPath(fill_path, QColor(47, 128, 237, 36))

        painter.setPen(QPen(QColor("#1f67ce"), 1.6))
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(points[-1], 4, 4)


class SignalWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "idle"
        self._title = "READY"
        self._subtitle = "-- ms"
        self._colors = {
            "idle": QColor("#1E88E5"),
            "ready": QColor("#2196F3"),
            "go": QColor("#2E7D32"),
            "warning": QColor("#F9A825"),
            "danger": QColor("#D32F2F"),
            "success": QColor("#90A4AE"),
        }
        self.setObjectName("SignalWidget")
        self.setMinimumSize(180, 180)
        self.setMaximumSize(220, 220)

    def sizeHint(self):
        return QSize(200, 200)

    def set_state(self, state, title=None):
        self._state = state if state in self._colors else "idle"
        if title is not None:
            self._title = title
        self.update()

    def set_subtitle(self, text):
        self._subtitle = text if text is not None else "-- ms"
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        canvas = self.rect().adjusted(10, 10, -10, -10)
        diameter = min(canvas.width(), canvas.height())
        circle = QRectF(
            canvas.center().x() - diameter / 2,
            canvas.center().y() - diameter / 2,
            diameter,
            diameter,
        )

        fill = self._colors.get(self._state, self._colors["idle"])
        border = fill.darker(135)
        painter.setBrush(fill)
        painter.setPen(QPen(border, 4))
        painter.drawEllipse(circle)

        # State title in upper-centre of circle
        title_rect = QRectF(circle.left(), circle.top(), circle.width(), circle.height() * 0.56)
        painter.setPen(QPen(QColor("#0f3559"), 1))
        title_font = painter.font()
        title_font.setBold(True)
        title_font.setPointSize(18)
        painter.setFont(title_font)
        painter.drawText(title_rect, Qt.AlignCenter | Qt.AlignBottom, self._title)

        # Divider line inside circle
        cx = int(circle.center().x())
        cy = int(circle.center().y()) + 4
        half_w = int(circle.width() * 0.28)
        painter.setPen(QPen(QColor("#0f3559"), 1, Qt.SolidLine))
        painter.setOpacity(0.25)
        painter.drawLine(cx - half_w, cy, cx + half_w, cy)
        painter.setOpacity(1.0)

        # Subtitle in lower-centre of circle
        sub_rect = QRectF(circle.left(), circle.top() + circle.height() * 0.54, circle.width(), circle.height() * 0.44)
        sub_font = painter.font()
        sub_font.setBold(True)
        sub_font.setPointSize(13)
        painter.setFont(sub_font)
        painter.drawText(sub_rect, Qt.AlignCenter | Qt.AlignTop, self._subtitle)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.storage = ReactionTimeStorage()
        self.serial_handler: Optional[SerialHandler] = None
        self.current_participant: Optional[str] = None
        self.session_active = False
        self.test_in_progress = False
        self.current_trial = 0
        self.session_results = []
        self.latest_reaction_ms: Optional[float] = None
        self._current_session_id: Optional[str] = None
        self._go_received_at: Optional[float] = None   # time.monotonic() when GO arrived

        self.serial_poll_timer = QTimer(self)
        self.serial_poll_timer.setInterval(50)
        _connect_signal(self.serial_poll_timer.timeout, self.poll_serial_data)

        # Retry PING every 2 s until HELLO is received (handles Bluetooth latency
        # where the one-shot PING sent at connect is sometimes missed).
        self._ping_retry_timer = QTimer(self)
        self._ping_retry_timer.setInterval(2000)
        _connect_signal(self._ping_retry_timer.timeout, self._retry_ping)
        self._ping_retry_count = 0

        self._arduino_ready = False   # True only after HELLO handshake received
        self._participants_window = None   # lazy-created

        self._build_ui()
        self.populate_serial_ports()
        self.refresh_history()
        self._refresh_name_completer()

    def _build_ui(self):
        self.setWindowTitle("Arduino Reaction-Time Tester")
        self.setMinimumSize(900, 600)
        self.showMaximized()

        central_widget = QWidget(self)
        central_widget.setObjectName("MainContainer")
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout()
        root_layout.setSpacing(8)
        root_layout.setContentsMargins(10, 8, 10, 8)
        central_widget.setLayout(root_layout)

        # ── Header ────────────────────────────────────────────────────────────
        status_strip = QFrame()
        status_strip.setObjectName("StatusStrip")
        status_strip.setFixedHeight(46)
        status_strip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(14, 4, 14, 4)
        status_layout.setSpacing(10)
        status_strip.setLayout(status_layout)
        root_layout.addWidget(status_strip)

        status_icon = QLabel("⚡")
        status_icon.setObjectName("StatusIcon")
        status_layout.addWidget(status_icon)

        status_title = QLabel("Reaction-Time Assessment")
        status_title.setObjectName("StatusTitle")
        status_layout.addWidget(status_title)
        status_layout.addStretch(1)

        self.participant_chip = QLabel()
        self.participant_chip.setObjectName("StatusChip")
        status_layout.addWidget(self.participant_chip)

        self.connection_chip = QLabel()
        self.connection_chip.setObjectName("StatusChip")
        status_layout.addWidget(self.connection_chip)

        self.session_chip = QLabel()
        self.session_chip.setObjectName("StatusChip")
        status_layout.addWidget(self.session_chip)

        # ── Body: left (setup) + right (reaction test) ────────────────────────
        body_layout = QHBoxLayout()
        body_layout.setSpacing(10)
        body_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addLayout(body_layout)

        # ── Left: Session Setup ───────────────────────────────────────────────
        setup_group = QGroupBox("Session Setup")
        setup_group.setObjectName("SectionCard")
        setup_group.setFixedWidth(310)
        setup_group.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        setup_layout = QVBoxLayout()
        setup_layout.setContentsMargins(12, 12, 12, 12)
        setup_layout.setSpacing(10)
        setup_group.setLayout(setup_layout)
        body_layout.addWidget(setup_group)

        setup_layout.addWidget(QLabel("Participant Name"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter participant name")
        _connect_signal(self.name_input.textChanged, self._on_name_changed)
        _connect_signal(self.name_input.returnPressed, self.register_participant)
        self._name_completer_model = QStringListModel()
        self._name_completer = QCompleter(self._name_completer_model, self.name_input)
        self._name_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._name_completer.setFilterMode(Qt.MatchContains)
        self._name_completer.setCompletionMode(QCompleter.PopupCompletion)
        # Selecting a suggestion loads the participant directly — no re-registration needed.
        self._name_completer.activated.connect(self._load_participant_from_registry)
        self.name_input.setCompleter(self._name_completer)
        setup_layout.addWidget(self.name_input)

        self.register_button = QPushButton("Register Participant")
        self.register_button.setObjectName("SecondaryButton")
        _connect_signal(self.register_button.clicked, self.register_participant)
        setup_layout.addWidget(self.register_button)

        self.view_participants_btn = QPushButton("👥  View Participants")
        self.view_participants_btn.setObjectName("SecondaryButton")
        _connect_signal(self.view_participants_btn.clicked, self._open_participants_window)
        setup_layout.addWidget(self.view_participants_btn)

        self.participant_status = QLabel()
        self.participant_status.setObjectName("InlineStatus")
        self.participant_status.setMinimumHeight(26)
        setup_layout.addWidget(self.participant_status)

        setup_divider = QFrame()
        setup_divider.setFrameShape(QFrame.HLine)
        setup_divider.setObjectName("SetupDivider")
        setup_layout.addWidget(setup_divider)

        setup_layout.addWidget(QLabel("Serial Port"))
        self.port_select = QComboBox()
        setup_layout.addWidget(self.port_select)

        serial_btn_row = QHBoxLayout()
        serial_btn_row.setSpacing(8)
        setup_layout.addLayout(serial_btn_row)

        self.refresh_ports_btn = QPushButton("Refresh")
        self.refresh_ports_btn.setObjectName("SecondaryButton")
        _connect_signal(self.refresh_ports_btn.clicked, self.populate_serial_ports)
        serial_btn_row.addWidget(self.refresh_ports_btn)

        self.connect_button = QPushButton("Connect")
        self.connect_button.setObjectName("PrimaryButton")
        _connect_signal(self.connect_button.clicked, self.toggle_serial_connection)
        serial_btn_row.addWidget(self.connect_button)

        self.connection_status = QLabel()
        self.connection_status.setObjectName("InlineStatus")
        self.connection_status.setMinimumHeight(26)
        setup_layout.addWidget(self.connection_status)
        setup_layout.addStretch(1)

        # ── Right: Reaction Test ──────────────────────────────────────────────
        reaction_group = QGroupBox("Reaction Test")
        reaction_group.setObjectName("MainTestCard")
        reaction_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        reaction_layout = QVBoxLayout()
        reaction_layout.setContentsMargins(12, 12, 12, 12)
        reaction_layout.setSpacing(10)
        reaction_group.setLayout(reaction_layout)
        body_layout.addWidget(reaction_group, stretch=1)

        # Circle + reading panel side by side
        signal_container = QWidget()
        signal_container_layout = QHBoxLayout()
        signal_container_layout.setContentsMargins(0, 0, 0, 0)
        signal_container_layout.setSpacing(24)
        signal_container.setLayout(signal_container_layout)
        reaction_layout.addWidget(signal_container)

        signal_container_layout.addStretch(1)

        self.signal_widget = SignalWidget()
        self.signal_widget.setFixedSize(200, 200)
        signal_container_layout.addWidget(self.signal_widget, alignment=Qt.AlignCenter)

        reading_panel = QWidget()
        reading_panel.setObjectName("ReadingPanel")
        reading_panel_layout = QVBoxLayout()
        reading_panel_layout.setContentsMargins(12, 0, 0, 0)
        reading_panel_layout.setSpacing(8)
        reading_panel.setLayout(reading_panel_layout)
        signal_container_layout.addWidget(reading_panel, stretch=2)

        reading_panel_layout.addStretch(1)

        self.live_result_value = QLabel("-- ms")
        self.live_result_value.setObjectName("LiveResultValue")
        self.live_result_value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        reading_panel_layout.addWidget(self.live_result_value)

        self.live_result_hint = QLabel("Waiting...")
        self.live_result_hint.setObjectName("LiveResultHint")
        self.live_result_hint.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        reading_panel_layout.addWidget(self.live_result_hint)

        reading_panel_layout.addStretch(1)
        signal_container_layout.addStretch(1)

        # Buttons
        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        reaction_layout.addLayout(button_row)

        self.start_button = QPushButton("START TEST")
        self.start_button.setObjectName("PrimaryActionButton")
        _connect_signal(self.start_button.clicked, self.start_test)
        self.start_button.setFixedHeight(36)
        button_row.addWidget(self.start_button, stretch=1)

        self.stop_button = QPushButton("END SESSION")
        self.stop_button.setObjectName("DangerButton")
        _connect_signal(self.stop_button.clicked, self.stop_test)
        self.stop_button.setFixedHeight(36)
        button_row.addWidget(self.stop_button, stretch=1)

        # Dynamic hint shown when START TEST is disabled
        self.start_hint_label = QLabel()
        self.start_hint_label.setObjectName("InlineStatus")
        self.start_hint_label.setAlignment(Qt.AlignCenter)
        self.start_hint_label.setFixedHeight(26)
        reaction_layout.addWidget(self.start_hint_label)

        self.trial_progress = QProgressBar()
        self.trial_progress.setObjectName("TrialProgress")
        self.trial_progress.setRange(0, SESSION_TRIALS)
        self.trial_progress.setValue(0)
        self.trial_progress.setTextVisible(True)
        self.trial_progress.setFixedHeight(22)
        reaction_layout.addWidget(self.trial_progress)

        self.feedback_label = QLabel()
        self.feedback_label.setObjectName("FeedbackPanel")
        self.feedback_label.setWordWrap(True)
        self.feedback_label.setAlignment(Qt.AlignCenter)
        self.feedback_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        reaction_layout.addWidget(self.feedback_label)

        # ── Scrollable lower section (Summary + Tabs) ─────────────────────────
        scroll_area = QScrollArea()
        scroll_area.setObjectName("LowerScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root_layout.addWidget(scroll_area, stretch=1)

        scroll_content = QWidget()
        scroll_content.setObjectName("LowerContent")
        scroll_layout = QVBoxLayout()
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(8)
        scroll_content.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_content)

        # Session Summary
        summary_group = QGroupBox("Session Summary")
        summary_group.setObjectName("SectionCard")
        summary_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        summary_layout = QVBoxLayout()
        summary_layout.setContentsMargins(12, 12, 12, 12)
        summary_layout.setSpacing(8)
        summary_group.setLayout(summary_layout)
        scroll_layout.addWidget(summary_group)

        metric_row = QHBoxLayout()
        metric_row.setSpacing(10)
        summary_layout.addLayout(metric_row)

        total_card, self.total_trials_value = self._create_metric_card("Total", "0")
        avg_card, self.average_value = self._create_metric_card("Average", "--")
        best_card, self.best_value = self._create_metric_card("Best", "--")
        worst_card, self.worst_value = self._create_metric_card("Worst", "--")
        metric_row.addWidget(total_card, stretch=1)
        metric_row.addWidget(avg_card, stretch=1)
        metric_row.addWidget(best_card, stretch=1)
        metric_row.addWidget(worst_card, stretch=1)

        self.overall_category_badge = QLabel("Overall Category: Awaiting Data")
        self.overall_category_badge.setObjectName("CategoryBadge")
        self.overall_category_badge.setAlignment(Qt.AlignCenter)
        summary_layout.addWidget(self.overall_category_badge)

        self.interpretation_label = QLabel("Assessment: Complete at least one trial to generate interpretation.")
        self.interpretation_label.setObjectName("InterpretationText")
        self.interpretation_label.setWordWrap(True)
        summary_layout.addWidget(self.interpretation_label)

        # Trend / History Tabs
        tabs = QTabWidget()
        tabs.setObjectName("DataTabs")
        tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        tabs.setMinimumHeight(200)
        scroll_layout.addWidget(tabs)

        trend_tab = QWidget()
        trend_layout = QVBoxLayout()
        trend_layout.setContentsMargins(10, 10, 10, 10)
        trend_layout.setSpacing(8)
        trend_tab.setLayout(trend_layout)

        self.trend_graph = ReactionTrendWidget()
        trend_layout.addWidget(self.trend_graph)

        self.trend_status_label = QLabel("Trend: collect more data to evaluate direction.")
        self.trend_status_label.setObjectName("TrendStatus")
        self.trend_status_label.setAlignment(Qt.AlignCenter)
        trend_layout.addWidget(self.trend_status_label)
        tabs.addTab(trend_tab, "Trend")

        history_tab = QWidget()
        history_layout = QVBoxLayout()
        history_layout.setContentsMargins(10, 10, 10, 10)
        history_layout.setSpacing(8)
        history_tab.setLayout(history_layout)

        self.history_table = QTableWidget(0, 5)
        self.history_table.setObjectName("HistoryTable")
        self.history_table.setHorizontalHeaderLabels(["Timestamp", "Participant", "Avg (ms)", "Trials", "Category"])
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setShowGrid(False)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        history_layout.addWidget(self.history_table)
        tabs.addTab(history_tab, "History")

        self._set_participant_status("No participant registered", "neutral")
        self._set_connection_status("Status: Not connected", "warning")
        self._set_feedback("Register participant and connect Arduino to begin.", "neutral")
        self._set_signal_state("idle", "READY", "Press START TEST to begin session.")
        self._set_live_result(None, "neutral", "Waiting...")
        self._update_participant_chip()
        self._update_connection_chip()
        self._update_session_chip()
        self._update_trial_status()
        self._sync_start_button_state()

    @staticmethod
    def _create_metric_card(label_text, value_text):
        card = QFrame()
        card.setObjectName("MetricCard")
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)
        card.setLayout(layout)

        label = QLabel(label_text)
        label.setObjectName("MetricLabel")
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        label.setMinimumHeight(18)
        layout.addWidget(label)

        value = QLabel(value_text)
        value.setObjectName("MetricValue")
        value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        value.setMinimumHeight(30)
        layout.addWidget(value)

        return card, value

    @staticmethod
    def _set_widget_state(widget, state):
        widget.setProperty("state", state)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _set_participant_status(self, message, state):
        self.participant_status.setText(message)
        self._set_widget_state(self.participant_status, state)

    def _set_connection_status(self, message, state):
        self.connection_status.setText(message)
        self._set_widget_state(self.connection_status, state)

    def _set_feedback(self, message, state):
        self.feedback_label.setText(message)
        self._set_widget_state(self.feedback_label, state)

    def _set_signal_state(self, state, title, subtitle):
        self.signal_widget.set_state(state, title=title)
        self.live_result_hint.setText(subtitle)

    def _set_live_result(self, reaction_ms, state, subtitle):
        if reaction_ms is None:
            self.live_result_value.setText("-- ms")
            self.signal_widget.set_subtitle("-- ms")
        else:
            ms_text = f"{reaction_ms:.1f} ms"
            self.live_result_value.setText(ms_text)
            self.signal_widget.set_subtitle(ms_text)
        self.live_result_hint.setText(subtitle)
        self._set_widget_state(self.live_result_value, state)

    @staticmethod
    def _classify_reaction(reaction_ms):
        if reaction_ms < 200:
            return "Excellent", "success", "Excellent response speed for most adults."
        if reaction_ms <= 300:
            return "Normal", "success", "Reaction time is within normal adult range."
        if reaction_ms <= 380:
            return "Slightly Slow", "warning", "Reaction is slightly slower than typical adult range."
        return "Delayed", "danger", "Reaction is slower than typical adult range."

    def _update_assessment(self, reactions):
        if not reactions:
            self.overall_category_badge.setText("Overall Category: Awaiting Data")
            self.interpretation_label.setText("Assessment: Complete at least one trial to generate interpretation.")
            self._set_widget_state(self.overall_category_badge, "neutral")
            self._set_widget_state(self.interpretation_label, "neutral")
            self._set_live_result(None, "neutral", "Reaction time")
            self.trend_status_label.setText("Trend: collect more data to evaluate direction.")
            self._set_widget_state(self.trend_status_label, "neutral")
            self.trend_graph.set_values([])
            return

        latest_ms = reactions[0]
        average_ms = sum(reactions) / len(reactions)
        category, state, interpretation = self._classify_reaction(average_ms)
        self.overall_category_badge.setText(f"Overall Category: {category.upper()}")
        self.interpretation_label.setText(
            f"Assessment: {interpretation} Based on {len(reactions)} recorded trials."
        )
        self._set_widget_state(self.overall_category_badge, state)
        self._set_widget_state(self.interpretation_label, state)

        latest_category, latest_state, _ = self._classify_reaction(latest_ms)
        self._set_live_result(latest_ms, latest_state, f"Latest reaction: {latest_category}")
        self._update_trend_status(list(reversed(reactions)))

    def _update_trend_status(self, ordered_values):
        self.trend_graph.set_values(ordered_values)
        if len(ordered_values) < 4:
            self.trend_status_label.setText("Trend: collect more trials for reliable direction.")
            self._set_widget_state(self.trend_status_label, "neutral")
            return

        window = min(5, max(2, len(ordered_values) // 3))
        recent_avg = sum(ordered_values[-window:]) / window
        previous_slice = ordered_values[:-window]
        if len(previous_slice) >= window:
            previous_avg = sum(previous_slice[-window:]) / window
        else:
            previous_avg = sum(previous_slice) / len(previous_slice)

        delta = recent_avg - previous_avg
        if delta <= -10:
            self.trend_status_label.setText(f"Trend: improving, about {abs(delta):.1f} ms faster.")
            self._set_widget_state(self.trend_status_label, "success")
        elif delta >= 18:
            self.trend_status_label.setText(f"Trend: slowing, about {delta:.1f} ms slower.")
            self._set_widget_state(self.trend_status_label, "danger")
        elif delta >= 10:
            self.trend_status_label.setText(f"Trend: slightly slower by {delta:.1f} ms.")
            self._set_widget_state(self.trend_status_label, "warning")
        else:
            self.trend_status_label.setText("Trend: stable across recent trials.")
            self._set_widget_state(self.trend_status_label, "active")

    def _update_participant_chip(self):
        typed_name = self.name_input.text().strip()
        if self.current_participant and typed_name == self.current_participant:
            self.participant_chip.setText(f"Participant: {self.current_participant}")
            self._set_widget_state(self.participant_chip, "success")
        elif typed_name:
            self.participant_chip.setText("Participant: Pending registration")
            self._set_widget_state(self.participant_chip, "warning")
        else:
            self.participant_chip.setText("Participant: Not registered")
            self._set_widget_state(self.participant_chip, "neutral")

    def _update_connection_chip(self):
        if self.serial_handler and self.serial_handler.is_connected():
            self.connection_chip.setText("Arduino: Connected")
            self._set_widget_state(self.connection_chip, "success")
            return
        if list_ports is None:
            self.connection_chip.setText("Arduino: Serial unavailable")
            self._set_widget_state(self.connection_chip, "danger")
            return
        has_port = any(self.port_select.itemData(idx) for idx in range(self.port_select.count()))
        if has_port:
            self.connection_chip.setText("Arduino: Disconnected")
            self._set_widget_state(self.connection_chip, "warning")
        else:
            self.connection_chip.setText("Arduino: No ports detected")
            self._set_widget_state(self.connection_chip, "danger")

    def _update_session_chip(self):
        if self.session_active and self.test_in_progress:
            self.session_chip.setText(f"Session: Trial {self.current_trial}/{SESSION_TRIALS}")
            self._set_widget_state(self.session_chip, "active")
        elif self.session_active:
            self.session_chip.setText("Session: Running")
            self._set_widget_state(self.session_chip, "active")
        else:
            self.session_chip.setText("Session: Ready")
            self._set_widget_state(self.session_chip, "neutral")

    def _refresh_name_completer(self) -> None:
        """Re-populate the name field completer from all registered participants."""
        names = [p["name"] for p in self.storage.get_all_participants()]
        self._name_completer_model.setStringList(names)

    def _on_name_changed(self):
        typed_name = self.name_input.text().strip()
        if self.current_participant and typed_name != self.current_participant:
            self._set_participant_status("Name changed. Click Register to confirm.", "warning")
        elif typed_name and typed_name == self.current_participant:
            self._set_participant_status(f"Registered: {typed_name}", "success")
        elif typed_name:
            self._set_participant_status("Name entered. Click Register to continue.", "neutral")
        else:
            self._set_participant_status("No participant registered", "neutral")
        self._update_participant_chip()
        self._sync_start_button_state()

    def register_participant(self):
        # Always open the dialog — pre-fills existing data if the participant
        # is already registered so the user can review or update their details.
        prefill = self.name_input.text().strip()
        dlg = RegisterParticipantDialog(self.storage, prefill_name=prefill, parent=self)
        dlg.registered.connect(self._on_participant_registered)
        dlg.exec_()

    def _on_participant_registered(self, name: str, age: int, gender: str,
                                    profession: str) -> None:
        self.name_input.setText(name)
        self.current_participant = name
        detail = f"Age {age}, {gender}"
        if profession:
            detail += f", {profession}"
        self._set_participant_status(f"Registered: {name} ({detail})", "success")
        self._set_feedback(
            f"{name} is ready. Connect Arduino and start the test.",
            "success",
        )
        self._update_participant_chip()
        self._sync_start_button_state()
        self._refresh_name_completer()

    def _open_participants_window(self) -> None:
        if self._participants_window is None:
            self._participants_window = ParticipantsWindow(self.storage, parent=None)
            self._participants_window.participant_selected.connect(self._load_participant_from_registry)
        self._participants_window.refresh()
        self._participants_window.show()
        self._participants_window.raise_()
        self._participants_window.activateWindow()

    def _load_participant_from_registry(self, name: str) -> None:
        """Called when the user double-clicks or presses Load in the participants window."""
        participant = self.storage.get_participant(name)
        age        = int(participant["age"])    if participant and participant["age"]    else 0
        gender     = participant["gender"]      if participant and participant["gender"] else "—"
        profession = participant["profession"]  if participant and participant["profession"] else ""
        self.name_input.setText(name)
        self.current_participant = name
        detail = f"Age {age}, {gender}"
        if profession:
            detail += f", {profession}"
        self._set_participant_status(f"Loaded: {name} ({detail})", "success")
        self._set_feedback(
            f"{name} loaded from registry. Connect Arduino and start the test.",
            "success",
        )
        self._update_participant_chip()
        self._sync_start_button_state()
        self._refresh_name_completer()
        self.raise_()
        self.activateWindow()

    def populate_serial_ports(self):
        current_selected = self.port_select.currentData()
        self.port_select.clear()
        if list_ports is None:
            self.port_select.addItem("pyserial not installed", userData=None)
            self.port_select.setEnabled(False)
            self.connect_button.setEnabled(False)
            self._set_connection_status("Status: Serial support unavailable", "danger")
            self._update_connection_chip()
            self._sync_start_button_state()
            return

        ports = list(list_ports.comports())
        if not ports:
            self.port_select.addItem("No ports detected", userData=None)
            if not (self.serial_handler and self.serial_handler.is_connected()):
                self._set_connection_status("Status: No ports detected", "danger")
        else:
            for port in ports:
                label = f"{port.device} ({port.description})"
                self.port_select.addItem(label, userData=port.device)
            if current_selected:
                for idx in range(self.port_select.count()):
                    if self.port_select.itemData(idx) == current_selected:
                        self.port_select.setCurrentIndex(idx)
                        break
            if not (self.serial_handler and self.serial_handler.is_connected()):
                self._set_connection_status("Status: Not connected", "warning")
        self.port_select.setEnabled(True)
        self.connect_button.setEnabled(True)
        self._update_connection_chip()
        self._sync_start_button_state()

    def toggle_serial_connection(self):
        if self.serial_handler and self.serial_handler.is_connected():
            if self.session_active or self.test_in_progress:
                self.serial_handler.send_data("X\n")
            self.serial_handler.disconnect()
            self.serial_handler = None
            self.serial_poll_timer.stop()
            self._ping_retry_timer.stop()
            self._arduino_ready = False
            self.session_active = False
            self.test_in_progress = False
            self.current_trial = 0
            self.session_results = []
            self.latest_reaction_ms = None
            self._go_received_at = None
            self.connect_button.setText("Connect")
            self._set_connection_status("Status: Not connected", "warning")
            self._set_feedback("Arduino disconnected.", "warning")
            self._set_signal_state("idle", "WAITING", "Reconnect Arduino to continue.")
            self._update_trial_status()
            self._update_connection_chip()
            self._update_session_chip()
            self._sync_start_button_state()
            return

        selected_port = self.port_select.currentData()
        if not selected_port:
            QMessageBox.warning(self, "Serial", "Please pick a serial port before connecting.")
            return

        handler = SerialHandler(selected_port, baudrate=ARDUINO_BAUD_RATE)
        handler.connect()
        if handler.is_connected():
            self.serial_handler = handler
            self.connect_button.setText("Disconnect")
            self.serial_poll_timer.start()
            self._set_connection_status(f"Status: Connected to {selected_port}", "success")
            self._set_feedback(
                "Arduino connected — waiting for handshake…", "active"
            )
            # Wait 2 s for Bluetooth/USB to stabilise, then send the first PING.
            # The retry timer will keep sending every 2 s until HELLO arrives.
            self._ping_retry_count = 0
            self._ping_retry_timer.start()
            QTimer.singleShot(2000, self._send_initial_ping)
            self._set_signal_state("idle", "READY", "Waiting for Arduino handshake…")
            self._update_connection_chip()
            self._sync_start_button_state()
        else:
            err = handler.last_error.lower()
            if "access is denied" in err or "permiss" in err or "in use" in err:
                detail = (
                    f"{selected_port} is already in use by another program.\n\n"
                    "Most likely cause: Arduino IDE Serial Monitor is open.\n"
                    "Fix: Close the Serial Monitor (or Arduino IDE), then click Connect again."
                )
            else:
                detail = (
                    f"Unable to open {selected_port}.\n\n"
                    "Tip: Make sure Arduino IDE Serial Monitor is closed, "
                    "the USB cable is plugged in, and the correct port is selected."
                )
            QMessageBox.critical(self, "Serial — Port Unavailable", detail)

    def _send_initial_ping(self):
        """Send the first PING after the stabilisation delay."""
        if self.serial_handler and self.serial_handler.is_connected() and not self._arduino_ready:
            self.serial_handler.send_data("PING\n")

    def start_test(self):
        participant_name = self.name_input.text().strip()
        if not participant_name or participant_name != self.current_participant:
            QMessageBox.warning(
                self,
                "Participant",
                "Please register the participant before starting a test.",
            )
            return

        if not (self.serial_handler and self.serial_handler.is_connected()):
            QMessageBox.warning(self, "Serial", "Please connect to Arduino before starting.")
            return

        if not self._arduino_ready:
            QMessageBox.warning(
                self,
                "Arduino Not Ready",
                "Arduino has not finished initialising yet.\n"
                "Wait for the \"Arduino is ready\" message before starting.",
            )
            return

        if self.session_active or self.test_in_progress:
            return

        self.session_active = True
        self.test_in_progress = False
        self.current_trial = 0
        self.session_results = []
        self.latest_reaction_ms = None
        self._go_received_at = None
        self._current_session_id = str(uuid.uuid4())
        self._set_live_result(None, "active", "Session started")
        self._set_signal_state("ready", "READY", "Waiting for random stimulus...")
        self._set_feedback(f"Session started for {participant_name}. Get ready for trial 1.", "active")
        self._update_trial_status()
        self._update_session_chip()
        self._sync_start_button_state()
        # Tell Arduino who the participant is and that the session has begun.
        # Arduino will show the name on LCD; delay 800 ms before first S so
        # the participant name / Session Start screen is visible briefly.
        safe_name = participant_name[:16].replace("\n", "").replace("\r", "")
        self.serial_handler.send_data(f"BEGIN:{safe_name}\n")
        QTimer.singleShot(800, self._start_next_trial)

    def stop_test(self):
        if not (self.serial_handler and self.serial_handler.is_connected()):
            return
        if not (self.session_active or self.test_in_progress):
            return
        self.serial_handler.send_data("X\n")
        self._set_signal_state("warning", "STOPPING", "Ending current session...")
        self._set_feedback("Stopping current session...", "warning")
        self._sync_start_button_state()

    def _start_next_trial(self):
        if not self.session_active:
            return
        if not (self.serial_handler and self.serial_handler.is_connected()):
            self._set_feedback("Arduino disconnected. Session stopped.", "danger")
            self._finish_session(aborted=True)
            return
        if self.current_trial >= SESSION_TRIALS:
            self._finish_session()
            return

        self.current_trial += 1
        self.test_in_progress = True
        self._update_trial_status()
        self._update_session_chip()
        self._set_signal_state("ready", "READY", "Wait for GO signal.")
        self._set_feedback(
            f"Trial {self.current_trial}/{SESSION_TRIALS}: wait for random GO signal.",
            "active",
        )
        self.serial_handler.send_data("S\n")
        self._sync_start_button_state()

    def _queue_next_trial_or_finish(self):
        if not self.session_active:
            return
        if len(self.session_results) >= SESSION_TRIALS:
            self._finish_session()
            return
        QTimer.singleShot(900, self._start_next_trial)

    def _finish_session(self, aborted=False):
        participant_name = self.current_participant or self.name_input.text().strip() or "Unknown"
        self.session_active = False
        self.test_in_progress = False
        self.current_trial = 0
        completed_results = list(self.session_results)
        self.session_results = []
        self._current_session_id = None
        self._update_trial_status()
        self._update_session_chip()
        self._sync_start_button_state()

        if aborted:
            self._set_signal_state("danger", "STOPPED", "Session aborted.")
            self._set_feedback("Session aborted. Reconnect Arduino and start again.", "danger")
            return

        valid_results = [result for result in completed_results if result is not None]
        missed_trials = SESSION_TRIALS - len(valid_results)
        if valid_results:
            average_ms = sum(valid_results) / len(valid_results)
            best_ms = min(valid_results)
            self._set_signal_state("success", "COMPLETE", f"Avg {average_ms:.1f} ms")
            self._set_feedback(
                f"{participant_name} done: {len(valid_results)}/{SESSION_TRIALS} valid, "
                f"avg {average_ms:.1f} ms, best {best_ms:.1f} ms, missed {missed_trials}.",
                "success",
            )
            # Notify Arduino LCD that session is complete.
            if self.serial_handler and self.serial_handler.is_connected():
                avg_int = int(round(average_ms))
                self.serial_handler.send_data(f"DONE:{avg_int}\n")
        else:
            self._set_signal_state("warning", "COMPLETE", "No valid response captured.")
            self._set_feedback(
                f"{participant_name} done: no valid reaction captured in {SESSION_TRIALS} trials.",
                "warning",
            )
            if self.serial_handler and self.serial_handler.is_connected():
                self.serial_handler.send_data("DONE:0\n")

    def poll_serial_data(self):
        if not (self.serial_handler and self.serial_handler.is_connected()):
            return
        try:
            for _ in range(20):
                payload = self.serial_handler.receive_data()
                if not payload:
                    break
                self._handle_serial_message(payload)
        except Exception:
            # Silently ignore transient serial errors during polling;
            # the next tick will retry or the disconnect handler will fire.
            pass

    def _retry_ping(self):
        """Resend PING every 2 s until Arduino replies with HELLO.
        After 5 retries (~10 s) with no response, force-enable the start
        button so a Bluetooth latency or missed-HELLO issue can't lock the
        user out permanently."""
        if self._arduino_ready:
            self._ping_retry_timer.stop()
            return
        if not (self.serial_handler and self.serial_handler.is_connected()):
            self._ping_retry_timer.stop()
            return
        self._ping_retry_count += 1
        self.serial_handler.send_data("PING\n")
        if self._ping_retry_count >= 5:
            # No HELLO after ~10 s - Arduino firmware is likely running but the
            # Bluetooth layer dropped the response.  Treat as ready so the user
            # isn't permanently blocked.
            self._ping_retry_timer.stop()
            self._arduino_ready = True
            self._set_connection_status("Status: Arduino ready (fallback)", "success")
            self._set_feedback(
                "Arduino ready (handshake timed out — proceeding). Press START TEST.",
                "success",
            )
            self._set_signal_state("idle", "READY", "Waiting for START TEST button.")
            self._sync_start_button_state()

    def _handle_serial_message(self, message):
        value = message.strip()
        if not value:
            return

        if value == "HELLO":
            self._arduino_ready = True
            self._ping_retry_timer.stop()   # handshake complete — stop retrying
            self._set_connection_status(
                f"Status: Arduino ready", "success"
            )
            self._set_feedback(
                "Arduino is ready and waiting. Press START TEST to begin.", "success"
            )
            self._set_signal_state("idle", "READY", "Waiting for START TEST button.")
            self._sync_start_button_state()
            return
        if value == "ARMED":
            self._set_signal_state("ready", "READY", "Wait for GO signal.")
            self._set_feedback(
                f"Trial {self.current_trial}/{SESSION_TRIALS}: ready... wait for LED signal.",
                "active",
            )
            return
        if value == "GO":
            self._go_received_at = time.monotonic()   # start PC-side reaction clock
            self._set_signal_state("go", "GO", "Press the hardware button — or Enter / Space key.")
            self._set_feedback(
                f"Trial {self.current_trial}/{SESSION_TRIALS}: GO! "
                "Press the Arduino button  OR  hit Enter / Space on the keyboard.",
                "warning",
            )
            return
        if value == "PRESSED":
            # Hardware button detected — clear PC clock so keyboard can't double-record
            self._go_received_at = None
            self._set_signal_state("active", "PRESSED!", "Button detected…")
            self._set_feedback(
                f"Trial {self.current_trial}/{SESSION_TRIALS}: button press detected! Recording…",
                "active",
            )
            return
        if value == "TIMEOUT":
            self.test_in_progress = False
            self._go_received_at = None
            self.session_results.append(None)
            self._set_signal_state("warning", "MISSED", "No response captured in time.")
            self._set_feedback(
                f"Trial {self.current_trial}/{SESSION_TRIALS}: timeout. Preparing next trial.",
                "warning",
            )
            self._set_live_result(None, "warning", "Latest reaction: timeout")
            self._update_trial_status()
            self._update_session_chip()
            self._queue_next_trial_or_finish()
            self._sync_start_button_state()
            return
        if value in {"EARLY", "TOO_SOON"}:
            self._set_signal_state("danger", "EARLY", "False start — wait for GO.")
            self._set_feedback(
                f"Trial {self.current_trial}/{SESSION_TRIALS}: false start! "
                "Arduino is re-arming — wait for GO signal.",
                "danger",
            )
            # test_in_progress stays True; Arduino will send ARMED again to re-arm.
            return
        if value == "CANCELLED":
            self.test_in_progress = False
            self._go_received_at = None
            self._set_signal_state("danger", "STOPPED", "Session cancelled.")
            self._set_feedback("Test cancelled.", "danger")
            self._finish_session(aborted=True)
            self._sync_start_button_state()
            return
        if value == "BUSY":
            self._set_feedback("Arduino is still running a previous test.", "warning")
            return

        reaction_time_ms = self._parse_reaction_time(value)
        if reaction_time_ms is None:
            return
        if not self.test_in_progress:
            if self.session_active:
                self._set_signal_state("danger", "EARLY", "Detected input outside GO phase.")
                self._set_feedback("Input received outside active GO phase.", "danger")
            return

        # Clear the PC-side GO timestamp now that a result is being recorded.
        # Leaving it set would allow a simultaneous keyboard press to re-enter
        # this path with a near-zero time (the serial transit latency ~17 ms).
        self._go_received_at = None
        participant_name = self.current_participant or self.name_input.text().strip() or "Unknown"
        self.storage.save_reaction_time(participant_name, reaction_time_ms, self._current_session_id)
        self.latest_reaction_ms = reaction_time_ms
        category, _category_state, _ = self._classify_reaction(reaction_time_ms)
        self._set_signal_state("success", "RECORDED", f"{reaction_time_ms:.1f} ms ({category})")
        self._set_feedback(
            f"{participant_name}'s reaction time: {reaction_time_ms:.1f} ms ({category}).",
            "success",
        )
        self.session_results.append(reaction_time_ms)
        self.test_in_progress = False
        self._update_trial_status()
        self._update_session_chip()
        self.refresh_history()
        self._queue_next_trial_or_finish()
        self._sync_start_button_state()

    @staticmethod
    def _parse_reaction_time(payload):
        candidate = payload
        if payload.startswith("RT:"):
            candidate = payload[3:].strip()

        try:
            parsed = float(candidate)
        except ValueError:
            return None

        if parsed < 0:
            return None
        return parsed

    def refresh_history(self):
        # History table: one row per session (grouped average)
        sessions = self.storage.get_session_averages()
        self.history_table.setRowCount(len(sessions))
        for row_idx, record in enumerate(sessions):
            if hasattr(record, "keys"):
                timestamp  = record["timestamp"]
                participant = record["participant_name"]
                avg_rt      = float(record["avg_rt"])
                trial_count = int(record["trial_count"])
            else:
                timestamp   = record[0]
                participant = record[1]
                avg_rt      = float(record[2])
                trial_count = int(record[3])

            category, _, _ = self._classify_reaction(avg_rt)

            # Format timestamp: strip microseconds for readability
            ts_display = timestamp.replace("T", "  ").split(".")[0]

            timestamp_item  = QTableWidgetItem(ts_display)
            participant_item = QTableWidgetItem(participant or "-")
            avg_item        = QTableWidgetItem(f"{avg_rt:.1f}")
            trials_item     = QTableWidgetItem(str(trial_count))
            category_item   = QTableWidgetItem(category)
            avg_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            trials_item.setTextAlignment(Qt.AlignCenter)

            self.history_table.setItem(row_idx, 0, timestamp_item)
            self.history_table.setItem(row_idx, 1, participant_item)
            self.history_table.setItem(row_idx, 2, avg_item)
            self.history_table.setItem(row_idx, 3, trials_item)
            self.history_table.setItem(row_idx, 4, category_item)

        # Stats panel / trend graph: filter to current participant when one is loaded
        if self.current_participant:
            participant_records = self.storage.get_participant_reaction_times(
                self.current_participant
            )
            summary_reactions = [float(r[1]) for r in reversed(participant_records)]
        else:
            all_rows = self.storage.get_all_reaction_times()
            summary_reactions = [
                float(r["reaction_time"] if hasattr(r, "keys") else r[3])
                for r in all_rows
            ]

        self._update_history_summary(summary_reactions)

    def _update_history_summary(self, reactions):
        self.total_trials_value.setText(str(len(reactions)))
        if reactions:
            average_ms = sum(reactions) / len(reactions)
            self.average_value.setText(f"{average_ms:.1f}")
            self.best_value.setText(f"{min(reactions):.1f}")
            self.worst_value.setText(f"{max(reactions):.1f}")
        else:
            self.average_value.setText("--")
            self.best_value.setText("--")
            self.worst_value.setText("--")
        self._update_assessment(reactions)

    def _update_trial_status(self):
        if self.session_active:
            completed = len(self.session_results)
            self.trial_progress.setFormat(
                f"Trial {self.current_trial}/{SESSION_TRIALS} - {completed}/{SESSION_TRIALS} completed"
            )
        else:
            completed = 0
            self.trial_progress.setFormat(
                f"Trial 0/{SESSION_TRIALS} - {completed}/{SESSION_TRIALS} completed"
            )
        self.trial_progress.setValue(min(completed, SESSION_TRIALS))

    def _sync_start_button_state(self):
        has_registered_name = bool(
            self.current_participant
            and self.current_participant == self.name_input.text().strip()
        )
        has_serial_connection = bool(self.serial_handler and self.serial_handler.is_connected())
        can_start = (
            has_registered_name
            and has_serial_connection
            and self._arduino_ready
            and not self.test_in_progress
            and not self.session_active
        )
        self.start_button.setEnabled(can_start)
        self.stop_button.setEnabled(
            has_serial_connection and (self.session_active or self.test_in_progress)
        )

        # Show a clear reason why START TEST is blocked
        if can_start:
            self.start_hint_label.setText("✅  Ready — press START TEST to begin")
            self.start_hint_label.setStyleSheet("color: #1a7a3a; font-weight: 600;")
        elif self.session_active or self.test_in_progress:
            self.start_hint_label.setText("⏳  Session in progress")
            self.start_hint_label.setStyleSheet("color: #b07000; font-weight: 600;")
        elif not has_serial_connection:
            self.start_hint_label.setText("⚠️  Connect to Arduino first (choose a port and click Connect)")
            self.start_hint_label.setStyleSheet("color: #b05000; font-weight: 600;")
        elif not self._arduino_ready:
            self.start_hint_label.setText("⏳  Waiting for Arduino handshake (PING sent — please wait…)")
            self.start_hint_label.setStyleSheet("color: #b07000; font-weight: 600;")
        elif not has_registered_name:
            self.start_hint_label.setText("⚠️  Register or load a participant first (use Register Participant or View Participants)")
            self.start_hint_label.setStyleSheet("color: #b05000; font-weight: 600;")
        else:
            self.start_hint_label.setText("")

    def keyPressEvent(self, event):
        """Enter / Space / Return acts as the reaction button when GO is active."""
        reaction_keys = {Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space}
        if (
            event.key() in reaction_keys
            and self.test_in_progress
            and self._go_received_at is not None
            and not event.isAutoRepeat()
        ):
            rt_ms = (time.monotonic() - self._go_received_at) * 1000.0
            self._go_received_at = None
            # Tell Arduino the result so it can show RT on LCD and return to IDLE
            if self.serial_handler and self.serial_handler.is_connected():
                self.serial_handler.send_data(f"RESULT:{int(rt_ms)}\n")
            # Process as a normal RT result in Python
            self._handle_serial_message(f"RT:{rt_ms:.1f}")
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.serial_poll_timer.stop()
        self.storage.close()
        if self.serial_handler and self.serial_handler.is_connected():
            self.serial_handler.disconnect()
        super().closeEvent(event)


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    style_path = Path(__file__).resolve().parent / "styles.css"
    if style_path.exists():
        app.setStyleSheet(style_path.read_text(encoding="utf-8"))

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
