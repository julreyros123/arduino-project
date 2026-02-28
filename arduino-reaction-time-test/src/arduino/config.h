// ===== PIN CONFIG =====
#define BUTTON_PIN    3     // Reaction button (INPUT_PULLUP — LOW = pressed)
#define LED_PIN       2     // GO indicator LED
#define BUZZER_PIN    4     // Auditory GO signal

// ===== LCD (I2C) =====
// Address 0x27, 16 columns, 2 rows
#define LCD_ADDR      0x27
#define LCD_COLS      16
#define LCD_ROWS      2

// ===== TEST CONFIG =====
const int   NUM_TESTS         = 5;
const unsigned long TIMEOUT_MS        = 5000;   // Max wait for reaction (ms)
const unsigned long MIN_DELAY_MS      = 1000;   // Min random pre-GO delay (ms)
const unsigned long MAX_DELAY_MS      = 3000;   // Max random pre-GO delay (ms)
const unsigned long BUZZ_DURATION_MS  = 120;    // Buzzer ON duration on GO (ms)

// ===== SERIAL =====
#define SERIAL_BAUD_RATE 9600
