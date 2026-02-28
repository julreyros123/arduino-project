// =====================================================================
//  Reaction-Time Tester — Arduino Firmware
//  Integrates LCD display + buzzer feedback with the Python serial
//  protocol (S / X commands  ↔  ARMED / GO / RT:xxx / TIMEOUT /
//  CANCELLED / EARLY / BUSY responses).
// =====================================================================
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ===== PIN CONFIG =====
#define BUTTON_PIN    3     // Reaction button (INPUT_PULLUP — LOW = pressed)
#define LED_PIN       2     // GO indicator LED
#define BUZZER_PIN    4     // Auditory GO signal

// ===== LCD (I2C) =====
#define LCD_ADDR      0x27
#define LCD_COLS      16
#define LCD_ROWS      2

// ===== TEST CONFIG =====
const int           NUM_TESTS        = 5;
const unsigned long TIMEOUT_MS       = 5000;   // Max wait for reaction (ms)
const unsigned long MIN_DELAY_MS     = 1000;   // Min random pre-GO delay (ms)
const unsigned long MAX_DELAY_MS     = 3000;   // Max random pre-GO delay (ms)
// Buzzer stays ON throughout WAITING_FOR_PRESS; stopTest() turns it off.

// ===== SERIAL =====
#define SERIAL_BAUD_RATE 9600

// ── LCD ──────────────────────────────────────────────────────────────
LiquidCrystal_I2C lcd(LCD_ADDR, LCD_COLS, LCD_ROWS);

// ── State machine ────────────────────────────────────────────────────
enum TestState { IDLE, WAITING_RANDOM_DELAY, WAITING_FOR_PRESS };
TestState state       = IDLE;
unsigned long stateStartMs    = 0;
unsigned long reactionStartMs = 0;
unsigned long randomDelayMs   = 0;
int  trialNumber = 0;          // increments on each "S", resets on "X"

// ── Helpers ──────────────────────────────────────────────────────────

// Show a two-line message on the LCD.
void lcdShow(const char* line0, const char* line1 = "") {
  lcd.clear();
  lcd.setCursor(0, 0);  lcd.print(line0);
  lcd.setCursor(0, 1);  lcd.print(line1);
}

// Debounced button read — waits for release before returning true.
bool buttonPressed() {
  if (digitalRead(BUTTON_PIN) == LOW) {
    delay(20);                                          // debounce
    if (digitalRead(BUTTON_PIN) == LOW) {
      while (digitalRead(BUTTON_PIN) == LOW) delay(1); // wait release
      return true;
    }
  }
  return false;
}

// Map reaction time (ms) to a category string shown on the LCD.
const char* getCategory(unsigned long rt) {
  if (rt < 140)       return "Elite";
  else if (rt <= 190) return "Top Avg";
  else if (rt <= 250) return "Average";
  else                return "Below Avg";
}

// ── Core actions ─────────────────────────────────────────────────────

// Arm a new trial: pick random delay, update LCD, notify Python.
void armTrial() {
  randomDelayMs = random(MIN_DELAY_MS, MAX_DELAY_MS + 1);
  stateStartMs  = millis();
  reactionStartMs = 0;
  state = WAITING_RANDOM_DELAY;

  digitalWrite(LED_PIN,    LOW);
  digitalWrite(BUZZER_PIN, LOW);

  char buf[17];
  snprintf(buf, sizeof(buf), "Trial %d/%d", trialNumber, NUM_TESTS);
  lcdShow(buf, "Wait for GO...");

  Serial.println(F("ARMED"));
}

// Fire the GO signal: LED on, buzzer on (stays on until press/timeout), update LCD, notify Python.
void triggerGo() {
  state = WAITING_FOR_PRESS;

  // Activate stimulus – buzzer stays ON until stopTest() turns it off.
  digitalWrite(LED_PIN,    HIGH);
  digitalWrite(BUZZER_PIN, HIGH);

  lcdShow(">> GO! <<", "Press button now");

  // Start the reaction clock AFTER the stimulus is fully visible/audible
  // so the measured time reflects true user response latency.
  reactionStartMs = millis();
  Serial.println(F("GO"));
}

// Reset to IDLE.  Pass resetSession=true to zero the trial counter.
void stopTest(bool resetSession = false) {
  state = IDLE;
  stateStartMs    = 0;
  reactionStartMs = 0;
  randomDelayMs   = 0;
  if (resetSession) trialNumber = 0;

  digitalWrite(LED_PIN,    LOW);
  digitalWrite(BUZZER_PIN, LOW);
}

// ── Serial command handler ────────────────────────────────────────────
void handleCommand(const String& cmd) {
  if (cmd.length() == 0) return;

  // "PING" — Python requests a handshake confirmation (used after Bluetooth connect
  // where the Arduino does not reset and the boot-time HELLO was already missed).
  if (cmd == "PING") {
    Serial.println(F("HELLO"));
    lcdShow("PC Connected!", "  Ready to start");
    return;
  }

  // "BEGIN:name" — Python started a session; show participant name on LCD.
  // No response needed; Python sends "S" immediately after.
  if (cmd.startsWith("BEGIN:")) {
    String pName = cmd.substring(6);
    pName.trim();
    if (pName.length() > 16) pName = pName.substring(0, 16);
    char nameBuf[17];
    pName.toCharArray(nameBuf, sizeof(nameBuf));
    lcdShow(nameBuf, "   Session Start");
    trialNumber = 0;   // reset trial counter for new session
    return;
  }

  // "S" — start the next trial in the current session
  if (cmd == "S") {
    if (state != IDLE) {
      Serial.println(F("BUSY"));
      return;
    }
    trialNumber++;
    armTrial();
    return;
  }

  // "X" — abort / cancel the current session
  if (cmd == "X") {
    stopTest(true);   // reset trial counter too
    lcdShow("  RT Tester  ", " Waiting PC...");
    Serial.println(F("CANCELLED"));
    return;
  }

  // "RESULT:rt" — PC keyboard captured the reaction; show result on LCD
  // and return to IDLE (mirrors what the hardware button path does).
  if (cmd.startsWith("RESULT:")) {
    unsigned long rt = cmd.substring(7).toInt();
    digitalWrite(LED_PIN, LOW);
    char rtLine[17];
    snprintf(rtLine, sizeof(rtLine), "RT: %lu ms", rt);
    lcdShow(rtLine, getCategory(rt));
    stopTest();   // back to IDLE; trialNumber kept
    return;
  }

  // "DONE:avg" — Python signals session complete; show summary on LCD
  if (cmd.startsWith("DONE:")) {
    stopTest(true);
    unsigned long avg = cmd.substring(5).toInt();
    if (avg > 0) {
      char buf[17];
      snprintf(buf, sizeof(buf), "Avg: %lu ms", avg);
      lcdShow("Session Done!", buf);
    } else {
      lcdShow("Session Done!", "No valid result");
    }
  }
}

// =====================================================================
//  SETUP
// =====================================================================
void setup() {
  Serial.begin(SERIAL_BAUD_RATE);

  pinMode(BUTTON_PIN,  INPUT_PULLUP);
  pinMode(LED_PIN,     OUTPUT);
  pinMode(BUZZER_PIN,  OUTPUT);
  digitalWrite(LED_PIN,    LOW);
  digitalWrite(BUZZER_PIN, LOW);

  lcd.init();
  lcd.backlight();
  // Show waiting message — the test ONLY starts when Python sends "S".
  lcdShow("  RT Tester  ", " Waiting PC...");
  // Announce readiness to Python so it can confirm the handshake.
  Serial.println(F("HELLO"));

  randomSeed(analogRead(A0) ^ micros());
}

// =====================================================================
//  LOOP
// =====================================================================
void loop() {

  // Always drain the serial buffer first so Python commands are
  // processed promptly even while we are in a state.
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    handleCommand(command);
  }

  // ── IDLE ── nothing to do
  if (state == IDLE) return;

  // ── WAITING FOR RANDOM DELAY ─────────────────────────────────────
  if (state == WAITING_RANDOM_DELAY) {

    // False-start: button pressed before GO
    if (buttonPressed()) {
      char buf[17];
      snprintf(buf, sizeof(buf), "Trial %d/%d", trialNumber, NUM_TESTS);
      lcdShow("FALSE START!", "Wait for GO...");
      Serial.println(F("EARLY"));

      // Brief penalty pause, then re-arm the SAME trial number.
      delay(1200);
      armTrial();   // sends ARMED again; trialNumber unchanged
      return;
    }

    // Time elapsed — fire GO signal
    if (millis() - stateStartMs >= randomDelayMs) {
      triggerGo();
    }
    return;
  }

  // ── WAITING FOR PRESS ────────────────────────────────────────────
  if (state == WAITING_FOR_PRESS) {

    // Valid reaction press
    if (buttonPressed()) {
      unsigned long rt = millis() - reactionStartMs;
      digitalWrite(LED_PIN, LOW);

      // LCD: show result
      char rtLine[17];
      snprintf(rtLine, sizeof(rtLine), "RT: %lu ms", rt);
      lcdShow(rtLine, getCategory(rt));

      // Serial: notify Python
      Serial.print(F("RT:"));
      Serial.println(rt);

      stopTest();   // back to IDLE; trialNumber kept for session tracking
      return;
    }

    // Timeout — no press received in time
    if (millis() - reactionStartMs >= TIMEOUT_MS) {
      digitalWrite(LED_PIN, LOW);
      lcdShow("TIMEOUT", "No response");
      Serial.println(F("TIMEOUT"));
      stopTest();
    }
  }
}
