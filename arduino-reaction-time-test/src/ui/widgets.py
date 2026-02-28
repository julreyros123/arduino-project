from PyQt5.QtWidgets import QPushButton, QLabel, QVBoxLayout, QWidget
from PyQt5.QtCore import QTimer
import time

class ReactionTimeWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.reaction_time = None
        self.start_time = None

    def initUI(self):
        self.layout = QVBoxLayout()

        self.instruction_label = QLabel("Press the button as quickly as you can when it turns green!")
        self.layout.addWidget(self.instruction_label)

        self.reaction_button = QPushButton("Press Me!")
        self.reaction_button.setEnabled(False)
        self.reaction_button.clicked.connect(self.record_reaction_time)
        self.layout.addWidget(self.reaction_button)

        self.result_label = QLabel("")
        self.layout.addWidget(self.result_label)

        self.setLayout(self.layout)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.change_button_color)

    def start_test(self):
        self.result_label.setText("")
        self.reaction_button.setEnabled(False)
        self.timer.start(2000)  # Wait for 2 seconds before enabling the button

    def change_button_color(self):
        self.reaction_button.setEnabled(True)
        self.reaction_button.setStyleSheet("background-color: green;")
        self.start_time = time.time()

    def record_reaction_time(self):
        if self.start_time is not None:
            self.reaction_time = time.time() - self.start_time
            self.result_label.setText(f"Your reaction time: {self.reaction_time:.3f} seconds")
            self.reaction_button.setEnabled(False)
            self.reaction_button.setStyleSheet("")  # Reset button color
            self.start_time = None
            self.timer.stop()