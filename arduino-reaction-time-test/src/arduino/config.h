#define BUTTON_PIN 2
#define LED_PIN 13

const int NUM_TESTS = 5;
const int TIMEOUT_MS = 5000; // Maximum time to wait for a reaction in milliseconds

// Reaction time thresholds (in milliseconds)
const int MIN_REACTION_TIME = 100; // Minimum reaction time to consider valid
const int MAX_REACTION_TIME = 2000; // Maximum reaction time to consider valid

// Serial communication settings
#define SERIAL_BAUD_RATE 9600

// Function prototypes
void setup();
void loop();
void handleButtonPress();
void sendReactionTime(unsigned long reactionTime);
