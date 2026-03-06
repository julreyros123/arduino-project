#include <Wire.h>
#include <LiquidCrystal_I2C.h>

#define BUTTON_PIN      4
#define BUZZER_PIN     13
#define RGB_RED_PIN     7
#define RGB_GREEN_PIN   6
#define RGB_BLUE_PIN    5

#define LCD_ADDR      0x27
#define LCD_COLS      16
#define LCD_ROWS      2

enum TestMode { MODE_BOTH, MODE_VISUAL, MODE_AUDIO };
TestMode testMode = MODE_BOTH;

const int           NUM_TESTS        = 5;
const unsigned long TIMEOUT_MS       = 5000;
const unsigned long MIN_DELAY_MS     = 1000;
const unsigned long MAX_DELAY_MS     = 3000;
const unsigned long BUZZ_DURATION_MS = 120;

#define SERIAL_BAUD_RATE 9600

LiquidCrystal_I2C lcd(LCD_ADDR, LCD_COLS, LCD_ROWS);

enum TestState { IDLE, WAITING_RANDOM_DELAY, WAITING_FOR_PRESS, SHOWING_RESULT, BUTTON_TEST };
TestState state          = IDLE;
unsigned long stateStartMs       = 0;
unsigned long reactionStartMs    = 0;
unsigned long randomDelayMs      = 0;
unsigned long buzzerOffAt        = 0;
unsigned long resultDisplayUntil = 0;
bool prevButtonState    = HIGH;
unsigned long debounceStartMs    = 0;
bool debouncePending    = false;
int  trialNumber  = 0;
int  btnTestCount = 0;
bool retryAfterResult = false;

void lcdShow(const char* line0, const char* line1 = "") {
  lcd.setCursor(0, 0);
  lcd.print(line0);
  for (int i = (int)strlen(line0); i < LCD_COLS; i++) lcd.print(' ');
  lcd.setCursor(0, 1);
  lcd.print(line1);
  for (int i = (int)strlen(line1); i < LCD_COLS; i++) lcd.print(' ');
}

#define DEBOUNCE_MS 20
bool buttonPressed() {
  bool isLow = (digitalRead(BUTTON_PIN) == LOW);

  if (!isLow) {
    prevButtonState = HIGH;
    debouncePending = false;
    return false;
  }

  if (prevButtonState == LOW) return false;

  if (!debouncePending) {
    debouncePending = true;
    debounceStartMs = millis();
    return false;
  }

  if (millis() - debounceStartMs < DEBOUNCE_MS) return false;

  prevButtonState = LOW;
  debouncePending = false;
  return true;
}

const char* getCategory(unsigned long rt) {
  if (rt < 140)       return "Elite";
  else if (rt <= 190) return "Top Avg";
  else if (rt <= 250) return "Average";
  else                return "Below Avg";
}

void setRGB(bool r, bool g, bool b) {
  digitalWrite(RGB_RED_PIN,   r ? HIGH : LOW);
  digitalWrite(RGB_GREEN_PIN, g ? HIGH : LOW);
  digitalWrite(RGB_BLUE_PIN,  b ? HIGH : LOW);
}

void beepBuzzer(unsigned int durationMs) {
  digitalWrite(BUZZER_PIN, HIGH);
  delay(durationMs);
  digitalWrite(BUZZER_PIN, LOW);
}

void armTrial() {
  randomDelayMs   = random(MIN_DELAY_MS, MAX_DELAY_MS + 1);
  stateStartMs    = millis();
  reactionStartMs = 0;
  prevButtonState = digitalRead(BUTTON_PIN);
  debouncePending = false;
  state = WAITING_RANDOM_DELAY;

  if (testMode != MODE_AUDIO) setRGB(true, false, false);
  else                         setRGB(false, false, false);
  digitalWrite(BUZZER_PIN, LOW);

  char buf[17];
  snprintf(buf, sizeof(buf), "Trial %d/%d", trialNumber, NUM_TESTS);
  const char* waitMsg;
  if      (testMode == MODE_VISUAL) waitMsg = "Wait for LED...";
  else if (testMode == MODE_AUDIO)  waitMsg = "Wait for beep...";
  else                               waitMsg = "Wait for GO...";
  lcdShow(buf, waitMsg);

  Serial.println(F("ARMED"));
}

void triggerGo() {
  state = WAITING_FOR_PRESS;

  reactionStartMs = millis();
  prevButtonState = digitalRead(BUTTON_PIN);
  debouncePending = false;
  Serial.println(F("GO"));

  if (testMode == MODE_VISUAL || testMode == MODE_BOTH) {
    setRGB(false, true, false);
  } else {
    setRGB(false, false, false);
  }

  if (testMode == MODE_AUDIO || testMode == MODE_BOTH) {
    digitalWrite(BUZZER_PIN, HIGH);
    buzzerOffAt = millis() + BUZZ_DURATION_MS;
  }

  if (testMode == MODE_AUDIO) {
    lcdShow(">> BEEP! <<", "Press button now");
  } else {
    lcdShow(">> GO! <<", "Press button now");
  }
}

void stopTest(bool resetSession = false) {
  state            = IDLE;
  stateStartMs     = 0;
  reactionStartMs  = 0;
  randomDelayMs    = 0;
  buzzerOffAt      = 0;
  retryAfterResult = false;
  prevButtonState  = digitalRead(BUTTON_PIN);
  debouncePending  = false;
  if (resetSession) trialNumber = 0;

  setRGB(false, false, false);
  digitalWrite(BUZZER_PIN, LOW);
  lcdShow("  RT Tester  ", " Ready to start");
}

void handleCommand(const String& cmd) {
  if (cmd.length() == 0) return;

  if (cmd == "PING") {
    Serial.println(F("HELLO"));
    lcdShow("PC Connected!", "  Ready to start");
    return;
  }

  if (cmd.startsWith("NAME:")) {
    if (state == IDLE) {
      String pName = cmd.substring(5);
      pName.trim();
      if (pName.length() > 16) pName = pName.substring(0, 16);
      char nameBuf[17];
      pName.toCharArray(nameBuf, sizeof(nameBuf));
      lcdShow(nameBuf, "     Ready");
    }
    return;
  }

  if (cmd.startsWith("MODE:")) {
    String modeStr = cmd.substring(5);
    if      (modeStr == "VISUAL") testMode = MODE_VISUAL;
    else if (modeStr == "AUDIO")  testMode = MODE_AUDIO;
    else                           testMode = MODE_BOTH;
    return;
  }

  if (cmd.startsWith("BEGIN:")) {
    String pName = cmd.substring(6);
    pName.trim();
    if (pName.length() > 16) pName = pName.substring(0, 16);
    char nameBuf[17];
    pName.toCharArray(nameBuf, sizeof(nameBuf));
    lcdShow(nameBuf, "   Session Start");
    trialNumber = 0;
    return;
  }

  if (cmd == "S") {
    if (state != IDLE) {
      Serial.println(F("BUSY"));
      return;
    }
    trialNumber++;
    armTrial();
    return;
  }

  if (cmd == "BTNTEST") {
    state = BUTTON_TEST;
    btnTestCount = 0;
    lcdShow("Button Test", "Press button...");
    Serial.println(F("BTNTEST:START"));
    return;
  }

  if (cmd == "X") {
    if (state == BUTTON_TEST) {
      state = IDLE;
      btnTestCount = 0;
      setRGB(false, false, false);
      lcdShow("  RT Tester  ", " Waiting PC...");
      Serial.println(F("BTNTEST:STOP"));
      return;
    }
    stopTest(true);
    lcdShow("  RT Tester  ", " Waiting PC...");
    Serial.println(F("CANCELLED"));
    return;
  }

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
    for (uint8_t i = 0; i < 3; i++) {
      beepBuzzer(120);
      delay(100);
    }
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);

  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  digitalWrite(RGB_RED_PIN,   LOW);
  digitalWrite(RGB_GREEN_PIN, LOW);
  digitalWrite(RGB_BLUE_PIN,  LOW);
  pinMode(RGB_RED_PIN,   OUTPUT);
  pinMode(RGB_GREEN_PIN, OUTPUT);
  pinMode(RGB_BLUE_PIN,  OUTPUT);

  lcd.init();
  lcd.backlight();
  lcdShow("  RT Tester  ", " Waiting PC...");

  beepBuzzer(100);
  delay(100);
  beepBuzzer(100);

  Serial.println(F("HELLO"));
  randomSeed(analogRead(A0) ^ micros());
}

void loop() {

  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    handleCommand(command);
  }

  if (state == IDLE) return;

  if (state == BUTTON_TEST) {
    if (buttonPressed()) {
      btnTestCount++;
      char buf[17];
      snprintf(buf, sizeof(buf), "Press #%d OK!", btnTestCount);
      lcdShow(buf, "Send X to exit");
      Serial.print(F("BTN:PRESS "));
      Serial.println(btnTestCount);
      beepBuzzer(40);
    }
    return;
  }

  if (state == WAITING_RANDOM_DELAY) {
    if (buttonPressed()) {
      lcdShow("Too Early!", "Wait for signal");
      Serial.println(F("EARLY"));
      state              = SHOWING_RESULT;
      resultDisplayUntil = millis() + 1500;
      retryAfterResult   = true;
      return;
    }

    if (millis() - stateStartMs >= randomDelayMs) triggerGo();
    return;
  }

  if (state == WAITING_FOR_PRESS) {
    if (buzzerOffAt > 0 && millis() >= buzzerOffAt) {
      digitalWrite(BUZZER_PIN, LOW);
      buzzerOffAt = 0;
    }

    if (buttonPressed()) {
      unsigned long rt = millis() - reactionStartMs;
      setRGB(false, false, false);

      char rtLine[17];
      snprintf(rtLine, sizeof(rtLine), "RT: %lu ms", rt);
      lcdShow(rtLine, getCategory(rt));
      Serial.print(F("RT:"));
      Serial.println(rt);

      state              = SHOWING_RESULT;
      resultDisplayUntil = millis() + 2000;
      return;
    }

    if (millis() - reactionStartMs >= TIMEOUT_MS) {
      setRGB(false, false, false);
      lcdShow("TIMEOUT", "Retrying...");
      Serial.println(F("TIMEOUT"));

      state              = SHOWING_RESULT;
      resultDisplayUntil = millis() + 2000;
      retryAfterResult   = true;
    }
  }

  if (state == SHOWING_RESULT) {
    if (millis() >= resultDisplayUntil) {
      if (retryAfterResult) {
        retryAfterResult = false;
        armTrial();
      } else {
        stopTest();
      }
    }
  }
}
