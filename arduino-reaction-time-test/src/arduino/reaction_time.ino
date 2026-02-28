#include "config.h"

enum TestState {
  IDLE,
  WAITING_RANDOM_DELAY,
  WAITING_FOR_PRESS
};

TestState state = IDLE;
unsigned long stateStartMs = 0;
unsigned long reactionStartMs = 0;
unsigned long randomDelayMs = 0;

void startTest() {
  randomDelayMs = random(2000, 5001);
  stateStartMs = millis();
  reactionStartMs = 0;
  state = WAITING_RANDOM_DELAY;
  digitalWrite(LED_PIN, LOW);
  Serial.println("ARMED");
}

void stopTest() {
  state = IDLE;
  stateStartMs = 0;
  reactionStartMs = 0;
  randomDelayMs = 0;
  digitalWrite(LED_PIN, LOW);
}

void handleCommand(const String& command) {
  if (command.length() == 0) {
    return;
  }

  if (command == "S") {
    if (state != IDLE) {
      Serial.println("BUSY");
      return;
    }
    startTest();
    return;
  }

  if (command == "X") {
    stopTest();
    Serial.println("CANCELLED");
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  randomSeed(analogRead(A0) ^ micros());
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    handleCommand(command);
  }

  if (state == WAITING_RANDOM_DELAY) {
    if (millis() - stateStartMs >= randomDelayMs) {
      reactionStartMs = millis();
      state = WAITING_FOR_PRESS;
      digitalWrite(LED_PIN, HIGH);
      Serial.println("GO");
    }
    return;
  }

  if (state == WAITING_FOR_PRESS) {
    if (digitalRead(BUTTON_PIN) == LOW) {
      unsigned long reactionTime = millis() - reactionStartMs;
      Serial.print("RT:");
      Serial.println(reactionTime);
      stopTest();
      delay(200); // Basic debounce after a successful press.
      return;
    }

    if (millis() - reactionStartMs >= TIMEOUT_MS) {
      Serial.println("TIMEOUT");
      stopTest();
    }
  }
}
