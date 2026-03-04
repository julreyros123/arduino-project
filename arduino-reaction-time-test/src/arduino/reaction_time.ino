// =====================================================================
//  Reaction-Time Tester — Arduino Firmware
//  Integrates LCD display + buzzer feedback with the Python serial
//  protocol (S / X commands  ↔  ARMED / GO / RT:xxx / TIMEOUT /
//  CANCELLED / EARLY / BUSY responses).
// =====================================================================
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ===== PIN CONFIG =====
#define BUTTON_PIN    2     // Reaction button (NC, INPUT_PULLUP — LOW = rest, HIGH = pressed)
#define LED_PIN       4     // GO indicator LED
#define BUZZER_PIN    3     // Auditory GO signal

// ===== LCD (I2C) =====
#define LCD_ADDR      0x27
#define LCD_COLS      16
#define LCD_ROWS      2

// ===== TEST CONFIG =====
const int           NUM_TESTS        = 5;
const unsigned long TIMEOUT_MS       = 5000;   // Max wait for reaction (ms)
const unsigned long MIN_DELAY_MS     = 1000;   // Min random pre-GO delay (ms)
const unsigned long MAX_DELAY_MS     = 3000;   // Max random pre-GO delay (ms)
const unsigned long BUZZ_DURATION_MS = 120;    // Buzzer ON duration on GO (ms)
const unsigned long ARM_GRACE_MS     = 300;    // Ignore button presses for this long after arming

// ===== SERIAL =====
#define SERIAL_BAUD_RATE 9600

// ── LCD ──────────────────────────────────────────────────────────────
LiquidCrystal_I2C lcd(LCD_ADDR, LCD_COLS, LCD_ROWS);

// ── State machine ────────────────────────────────────────────────────
enum TestState { IDLE, WAITING_RANDOM_DELAY, WAITING_FOR_PRESS, BUTTON_TEST };
TestState state       = IDLE;
unsigned long stateStartMs    = 0;
unsigned long reactionStartMs = 0;
unsigned long randomDelayMs   = 0;
unsigned long buzzerOffAt     = 0;   // non-blocking buzzer cutoff (0 = off)
unsigned long armTimeMs       = 0;   // when the current trial was armed (grace-period ref)
bool prevButtonState = LOW;          // LOW = resting state for NC button; used for edge detection
int  trialNumber  = 0;         // increments on each "S", resets on "X"
int  btnTestCount = 0;         // press counter used in BUTTON_TEST mode

// ── Helpers ──────────────────────────────────────────────────────────

// Show a two-line message on the LCD.
void lcdShow(const char* line0, const char* line1 = "") {
  lcd.clear();
  lcd.setCursor(0, 0);  lcd.print(line0);
  lcd.setCursor(0, 1);  lcd.print(line1);
}

// Edge-detecting button read — returns true ONLY on a LOW→HIGH transition.
// NC button: pin sits LOW at rest (closed to GND). Pressing opens the circuit;
// INPUT_PULLUP pulls pin HIGH. So a press = rising edge.
bool buttonPressed() {
  bool isHigh = (digitalRead(BUTTON_PIN) == HIGH);
  if (!isHigh) {
    prevButtonState = LOW;                              // pin at rest — arm for next press
    return false;
  }
  if (prevButtonState == HIGH) return false;            // still held from last press — ignore

  // Rising edge detected — apply debounce
  delay(15);
  if (digitalRead(BUTTON_PIN) == HIGH) {
    delay(5);
    if (digitalRead(BUTTON_PIN) == HIGH) {
      prevButtonState = HIGH;                           // latch until pin returns LOW
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

// Active-buzzer beep helper: drives pin HIGH for `durationMs`, then LOW.
// Call multiple times for repeated beeps.
void beepBuzzer(unsigned int durationMs) {
  digitalWrite(BUZZER_PIN, HIGH);
  delay(durationMs);
  digitalWrite(BUZZER_PIN, LOW);
}

// Arm a new trial: pick random delay, update LCD, notify Python.
void armTrial() {
  randomDelayMs = random(MIN_DELAY_MS, MAX_DELAY_MS + 1);
  stateStartMs  = millis();
  armTimeMs     = millis();
  reactionStartMs = 0;
  prevButtonState = digitalRead(BUTTON_PIN); // sync — if pin is already LOW, require a release first
  state = WAITING_RANDOM_DELAY;

  digitalWrite(LED_PIN,    LOW);
  digitalWrite(BUZZER_PIN, LOW);

  char buf[17];
  snprintf(buf, sizeof(buf), "Trial %d/%d", trialNumber, NUM_TESTS);
  lcdShow(buf, "Wait for GO...");

  Serial.println(F("ARMED"));
}

// Fire the GO signal: LED on, start non-blocking buzzer, record start time, notify Python.
void triggerGo() {
  state = WAITING_FOR_PRESS;

  digitalWrite(LED_PIN, HIGH);

  // ── CRITICAL ORDERING ──────────────────────────────────────────────
  // Set the reaction clock and send GO to the PC BEFORE anything else.
  // Any code below this point (LCD, buzzer) must NOT use blocking delay(),
  // otherwise both the Arduino timer and the PC-side timer (_go_received_at)
  // would start late, causing artificially short reaction times.
  reactionStartMs = millis();
  prevButtonState = digitalRead(BUTTON_PIN); // sync before reaction window — wire already low won't count
  Serial.println(F("GO"));

  // Non-blocking audible cue: buzzerOffAt tells loop() when to silence it.
  digitalWrite(BUZZER_PIN, HIGH);
  buzzerOffAt = millis() + BUZZ_DURATION_MS;

  lcdShow(">> GO! <<", "Press button now");
}

// Reset to IDLE.  Pass resetSession=true to zero the trial counter.
void stopTest(bool resetSession = false) {
  state = IDLE;
  stateStartMs    = 0;
  reactionStartMs = 0;
  randomDelayMs   = 0;
  buzzerOffAt     = 0;   // cancel any pending non-blocking beep
  prevButtonState = digitalRead(BUTTON_PIN); // sync to actual pin level — avoids phantom edge if wire is still low
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

  // "BTNTEST" — enter button-test mode: every press is reported over serial
  // and shown on the LCD.  Send "X" to exit.
  if (cmd == "BTNTEST") {
    state = BUTTON_TEST;
    btnTestCount = 0;
    lcdShow("Button Test", "Press button...");
    Serial.println(F("BTNTEST:START"));
    return;
  }

  // "X" — abort / cancel the current session
  if (cmd == "X") {
    if (state == BUTTON_TEST) {
      state = IDLE;
      btnTestCount = 0;
      lcdShow("  RT Tester  ", " Waiting PC...");
      Serial.println(F("BTNTEST:STOP"));
      return;
    }
    stopTest(true);   // reset trial counter too
    lcdShow("  RT Tester  ", " Waiting PC...");
    Serial.println(F("CANCELLED"));
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
    // Three short beeps to audibly signal session completion.
    for (uint8_t i = 0; i < 3; i++) {
      beepBuzzer(120);
      delay(100);
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

  // ── Active-buzzer initialisation: two short beeps confirm the buzzer
  // is wired and driven correctly before any test begins.
  beepBuzzer(100);
  delay(100);
  beepBuzzer(100);

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

  // ── BUTTON TEST ──────────────────────────────────────────────────
  if (state == BUTTON_TEST) {
    if (buttonPressed()) {
      btnTestCount++;
      char buf[17];
      snprintf(buf, sizeof(buf), "Press #%d OK!", btnTestCount);
      lcdShow(buf, "Send X to exit");
      Serial.print(F("BTN:PRESS "));
      Serial.println(btnTestCount);
      beepBuzzer(40);   // short click feedback
    }
    return;
  }

  // ── WAITING FOR RANDOM DELAY ─────────────────────────────────────
  if (state == WAITING_RANDOM_DELAY) {

    // False-start: button pressed before GO.
    // ARM_GRACE_MS guard ignores residual contact / noise right after arming.
    if (millis() - armTimeMs >= ARM_GRACE_MS && buttonPressed()) {
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

    // Non-blocking buzzer cutoff.
    if (buzzerOffAt > 0 && millis() >= buzzerOffAt) {
      digitalWrite(BUZZER_PIN, LOW);
      buzzerOffAt = 0;
    }

    // Detect press using the same edge-detecting buttonPressed() that works in BTNTEST.
    if (buttonPressed()) {
      unsigned long rt = millis() - reactionStartMs;
      digitalWrite(LED_PIN, LOW);

      char rtLine[17];
      snprintf(rtLine, sizeof(rtLine), "RT: %lu ms", rt);
      lcdShow(rtLine, getCategory(rt));
      Serial.print(F("RT:"));
      Serial.println(rt);
      stopTest();
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
