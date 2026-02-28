# Arduino Reaction Time Test

This project is an Arduino-based reaction time test designed for medical purposes. It measures how quickly a user can press a button and stores the data for historical tracking.

## Project Structure

```
arduino-reaction-time-test
├── src
│   ├── main.py               # Entry point of the application
│   ├── arduino
│   │   ├── reaction_time.ino  # Arduino sketch for button input
│   │   └── config.h           # Configuration settings for Arduino
│   ├── ui
│   │   ├── main_window.py      # Main window of the user interface
│   │   ├── widgets.py          # Custom widget definitions
│   │   └── styles.css          # Styling for the user interface
│   ├── data
│   │   ├── storage.py          # Data storage operations
│   │   └── models.py           # Data models for reaction time records
│   └── utils
│       ├── serial_handler.py    # Serial communication management
│       └── calculations.py       # Functions for calculating reaction times
├── tests
│   ├── test_calculations.py     # Unit tests for calculation functions
│   └── test_storage.py           # Unit tests for data storage functionality
├── data
│   └── results.db                # SQLite database for historical data
├── requirements.txt              # Project dependencies
├── README.md                     # Project documentation
└── .gitignore                    # Files to ignore in version control
```

## Setup Instructions

1. **Clone the repository**:
   ```
   git clone <repository-url>
   cd arduino-reaction-time-test
   ```

2. **Install dependencies**:
   Use the following command to install the required libraries:
   ```
   pip install -r requirements.txt
   ```

3. **Wire and upload the Arduino sketch**:
   - Connect a push button between `D2` and `GND` (the sketch uses `INPUT_PULLUP`).
   - Optional cue LED: use the built-in LED on pin `13` (already configured).
   - Open `src/arduino/reaction_time.ino` in Arduino IDE and upload to your board.

4. **Run the application**:
   Execute the main application with:
   ```
   python src/main.py
   ```

## Usage Guidelines

1. Enter a participant name, then click **Register participant**.
2. Connect to your Arduino serial port from the app.
3. Click **Start 5-Trial Test**.
4. The app runs 5 trials automatically. Each trial has a random GO cue (`GO` in app / LED on Arduino).
5. Press the hardware button as fast as possible after each GO cue.
6. Each valid trial is saved automatically in the history table, and the app shows a session summary.

## Contributing

Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.
