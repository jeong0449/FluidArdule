#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <EEPROM.h>

// Fluid Ardule UNO-1 input firmware
// 20260616 encoder ISR version - interrupt-driven quadrature capture + tolerant release detection
//
// Uno -> Pi protocol:
//   UNO_READY
//   BTN:LEFT / UP / DOWN / RIGHT / SEL / ENC_PUSH
//   BTN:LEFT_LP / UP_LP / DOWN_LP / RIGHT_LP / SEL_LP
//   ENC:+N / ENC:-N
//   POT:<0-1023>
//   ACCEL:<1-3>
//
// Pi -> Uno protocol:
//   HELLO
//   HB
//   UI:READY / UI:BUSY
//   ACK:BTN / ACK:ENC
//   ACT:MIDI
//   PLAY:OFF / PLAY:ON / PLAY:BLINK
//   PWR:SHUTDOWN / PWR:REBOOT
//
// Behavior:
//   D13 : blink until Pi link established, then steady ON
//   D12 : PLAY status LED
//   D11 : activity LED for MIDI pulse and local button/encoder/pot input
//   1602 LCD : local input monitor only
//   Line 1 rightmost 6 chars : last button event (e.g. L-SP / L-LP)
//   Line 2 rightmost 2 chars : current encoder acceleration profile (P1/P2/P3)
//   Encoder long press : acceleration profile cycle
//   SELECT long press : Pi-side power menu, unchanged
//   Encoder + SELECT simultaneous long press : keypad calibration entry
//   Keypad calibration saves automatically after LEFT/UP/DOWN/RIGHT/SELECT capture

LiquidCrystal_I2C lcd(0x27, 16, 2);

// ---- Pins ----
const uint8_t PIN_KEYPAD = A0;   // LCD keypad resistor ladder
const uint8_t PIN_ENC_A  = 2;
const uint8_t PIN_ENC_B  = 3;
const uint8_t PIN_ENC_SW = A1;   // active low, INPUT_PULLUP
const uint8_t PIN_POT    = A2;

const uint8_t PIN_LED_LINK = 13;
const uint8_t PIN_LED_PLAY = 12;
const uint8_t PIN_LED_MIDI = 11;

// ---- Timing ----
const unsigned long DEBOUNCE_MS = 20;
const unsigned long LONGPRESS_MS = 700;
const unsigned long CAL_COMBO_HOLD_MS = 900;  // Encoder switch + SELECT hold to enter keypad calibration
const unsigned long READY_REPEAT_MS = 3000;
const unsigned long READY_REPEAT_UNLINKED_MS = 500;
const unsigned long READY_REPEAT_CAL_MS = 1000;  // Keep Pi-side serial watchdog calm during local calibration
const unsigned long LCD_REFRESH_MS = 120;
const unsigned long POT_SEND_MS = 60;
const unsigned long LINK_TIMEOUT_MS = 3000;
const unsigned long POWER_SAFE_DELAY_MS = 10000;  // Wait after Pi heartbeat/link is lost following PWR:SHUTDOWN
// 60 seconds is intentionally conservative because USB serial can disappear
// before Raspberry Pi has fully completed filesystem sync and poweroff.
const unsigned long LINK_BLINK_MS = 300;
const unsigned long MIDI_LED_PULSE_MS = 70;
const unsigned long INPUT_LED_HOLD_MS = 180;
const unsigned long BUTTON_LED_BLINK_ON_MS = 70;
const unsigned long BUTTON_LED_BLINK_OFF_MS = 70;
const unsigned long PLAY_LED_BLINK_MS = 500;
const unsigned long DEBUG_TAG_HOLD_MS = 1200;
const unsigned long ACK_DEBUG_DELAY_MS = 300;
const int           POT_DELTA_SEND = 31;   // Serial POT reporting threshold (anout 3% of 1023)
const int           POT_DELTA_LED  = 31;   // Larger threshold to avoid LED stuck-on from A2 noise (same threshold)

// ---- A0 keypad calibration ----
// The old fixed-threshold method was vulnerable to module/temperature/Vcc drift.
// Runtime decoding now uses button center values loaded from EEPROM, with
// nearest-match selection and automatic midpoint boundaries.
const uint16_t KEYPAD_DEFAULT_CENTER[5] = {60, 195, 355, 560, 805};  // LEFT, UP, DOWN, RIGHT, SELECT
uint16_t keypadCenter[5] = {60, 195, 355, 560, 805};

// Keypad filtering.
// Odd sample count allows a true median, which rejects single-sample spikes better
// than a simple average on a resistor-ladder keypad.
const uint8_t KEYPAD_ADC_SAMPLES = 5;

// EEPROM layout for keypad calibration.
const uint16_t CAL_MAGIC = 0xFA10;
const uint8_t  CAL_VERSION = 1;
const int      CAL_EEPROM_ADDR = 0;

struct KeypadCalData {
  uint16_t magic;
  uint8_t version;
  uint8_t reserved;
  uint16_t center[5];
  uint16_t checksum;
};

// Calibration capture rules.
const int CAL_PRESS_MAX_ADC = 970;       // Below this, treat A0 as "some key is held"
const int CAL_RELEASE_MIN_ADC = 960;     // Above this, treat A0 as released/no-key. 960 is safer than 990 for real resistor-ladder modules
const uint8_t CAL_CAPTURE_SAMPLES = 25;  // Median-like trimmed average sample count
const unsigned long CAL_HOLD_STABILIZE_MS = 360;  // Keep key held this long before capture
const unsigned long CAL_RELEASE_STABLE_MS = 220;  // Require all keys released this long before accepting next press
const unsigned long CAL_LCD_BLINK_MS = 120;       // LCD blink interval while measuring/holding
const int CAL_MIN_GAP_ADC = 60;          // Reject calibration if neighboring centers are too close

enum KeyCode {
  KEY_NONE = 0,
  KEY_LEFT,
  KEY_UP,
  KEY_DOWN,
  KEY_RIGHT,
  KEY_SELECT
};

struct AccelProfile {
  unsigned int tFast;    // <= tFast => x3
  unsigned int tMedium;  // <= tMedium => x2, else x1
};

const AccelProfile ACCEL_TABLE[3] = {
  {60, 120},
  {70, 160},
  {100, 220}
};

// ---- Link / LCD state ----
bool piLinked = false;
bool everLinked = false;
unsigned long lastPiSeenMs = 0;

enum UiLinkState { UI_UNKNOWN = 0, UI_READY = 1, UI_BUSY = 2 };
UiLinkState piUiState = UI_UNKNOWN;
unsigned long lastUiSeenMs = 0;
unsigned long lastReadySentMs = 0;
unsigned long lastLcdRefreshMs = 0;
unsigned long lastBlinkMs = 0;
bool linkLedState = false;

enum PowerState { POWER_NORMAL = 0, POWER_SHUTDOWN_ARMED = 1, POWER_REBOOT_ARMED = 2, POWER_OFF_OK = 3 };
PowerState powerState = POWER_NORMAL;
unsigned long powerCommandMs = 0;
unsigned long powerLinkLostMs = 0;

unsigned long midiLedUntilMs = 0;
bool buttonLedBlinkActive = false;
uint8_t buttonLedBlinkRemainingToggles = 0;
bool buttonLedBlinkState = false;
unsigned long buttonLedBlinkNextMs = 0;
enum PlayLedMode { PLAY_LED_OFF = 0, PLAY_LED_ON = 1, PLAY_LED_BLINK = 2 };
PlayLedMode playLedMode = PLAY_LED_OFF;
bool playLedState = false;
unsigned long playLedLastToggleMs = 0;

String l1Text = "FluidArdule UNO";
String l2Text = "Booting...";

// Right-side 6-char debug tag on LCD line 1
String debugTag = "";
unsigned long debugTagUntilMs = 0;
unsigned long debugTagSetMs = 0;
String pendingAckDebugTag = "";
unsigned long pendingAckDebugDueMs = 0;

// ---- Keypad state ----
KeyCode stableKey = KEY_NONE;
KeyCode lastSampledKey = KEY_NONE;
unsigned long keyChangedMs = 0;
unsigned long keyPressedMs = 0;
bool keyLongSent = false;

// ---- Encoder state ----
// Rotation is captured in ISRs on D2/D3 so loop-time work such as LCD refresh,
// A0 keypad median filtering, Serial RX, or calibration UI cannot miss short
// quadrature transitions. The main loop consumes whole detents and keeps the
// existing ENC:+/-N protocol and acceleration behavior.
volatile uint8_t encIsrLastEncoded = 0;
volatile int8_t encIsrTransitionAccum = 0;
volatile int8_t encIsrStepAccum = 0;
volatile bool encIsrReady = false;
const int8_t ENC_TRANSITIONS_PER_STEP = 4;  // Keep previous UI feel. Use 4 if encoder becomes too sensitive.

int lastEncSw = HIGH;
bool encSwStable = HIGH;
unsigned long encSwChangedMs = 0;
unsigned long encSwPressedMs = 0;
bool encSwLongSent = false;
unsigned long lastEncStepMs = 0;

// ---- Pot state ----
int lastPotSent = -1000;
int lastPotLedRaw = -1;
unsigned long lastPotSentMs = 0;

// ---- Accel config ----
uint8_t accelProfile = 2;
bool accelSettingMode = false;
uint8_t accelDraft = 2;

// ---- Keypad calibration mode ----
bool keypadCalMode = false;
uint8_t keypadCalStep = 0;
unsigned long calComboStartMs = 0;
bool calComboConsumed = false;
bool selectEncOverlap = false;
uint16_t keypadCalDraft[5] = {0, 0, 0, 0, 0};
bool keypadCalWaitingRelease = false;
bool keypadCalNeedInitialRelease = false;
unsigned long keypadCalReleaseStableSinceMs = 0;
unsigned long calDenyUntilMs = 0;  // Temporary LCD notice when calibration is refused during playback

// ---- Serial RX ----
String rxLine;

int readKeypadAdcFiltered() {
  int v[KEYPAD_ADC_SAMPLES];

  for (uint8_t i = 0; i < KEYPAD_ADC_SAMPLES; i++) {
    v[i] = analogRead(PIN_KEYPAD);
    delayMicroseconds(250);
  }

  for (uint8_t i = 0; i < KEYPAD_ADC_SAMPLES - 1; i++) {
    for (uint8_t j = i + 1; j < KEYPAD_ADC_SAMPLES; j++) {
      if (v[j] < v[i]) {
        int t = v[i];
        v[i] = v[j];
        v[j] = t;
      }
    }
  }

  return v[KEYPAD_ADC_SAMPLES / 2];
}

uint16_t keypadCalChecksum(const KeypadCalData &d) {
  uint16_t s = d.magic + d.version + d.reserved;
  for (uint8_t i = 0; i < 5; i++) s += d.center[i];
  return s ^ 0x5A5A;
}

bool keypadCentersValid(const uint16_t c[5]) {
  for (uint8_t i = 0; i < 5; i++) {
    if (c[i] > 1023) return false;
  }

  for (uint8_t i = 1; i < 5; i++) {
    if (c[i] <= c[i - 1]) return false;
    if ((int)c[i] - (int)c[i - 1] < CAL_MIN_GAP_ADC) return false;
  }

  if (c[4] >= CAL_RELEASE_MIN_ADC) return false;
  return true;
}

void useDefaultKeypadCalibration() {
  for (uint8_t i = 0; i < 5; i++) keypadCenter[i] = KEYPAD_DEFAULT_CENTER[i];
}

void loadKeypadCalibration() {
  KeypadCalData d;
  EEPROM.get(CAL_EEPROM_ADDR, d);

  if (d.magic == CAL_MAGIC &&
      d.version == CAL_VERSION &&
      d.checksum == keypadCalChecksum(d) &&
      keypadCentersValid(d.center)) {
    for (uint8_t i = 0; i < 5; i++) keypadCenter[i] = d.center[i];
  } else {
    useDefaultKeypadCalibration();
  }
}

void saveKeypadCalibration(const uint16_t c[5]) {
  KeypadCalData d;
  d.magic = CAL_MAGIC;
  d.version = CAL_VERSION;
  d.reserved = 0;
  for (uint8_t i = 0; i < 5; i++) d.center[i] = c[i];
  d.checksum = keypadCalChecksum(d);
  EEPROM.put(CAL_EEPROM_ADDR, d);
}



bool keypadAnalogReleased(int raw) {
  // Some 5-key resistor-ladder boards do not return a perfect 1023 when idle,
  // especially after wiring, enclosure assembly, USB ground changes, or Vcc drift.
  // Treat the high ADC region as released instead of requiring near-perfect 1023.
  return raw >= CAL_RELEASE_MIN_ADC;
}

bool calibrationEntryControlsReleased(int raw) {
  // Initial release after ENC+SELECT entry should mean both sides of the
  // entry gesture are physically released: keypad SELECT on A0 and encoder SW.
  // encSwStable is debounced by updateEncoder(); one extra loop after release is OK.
  return keypadAnalogReleased(raw) && encSwStable == HIGH;
}

KeyCode keyFromIndex(uint8_t i) {
  switch (i) {
    case 0: return KEY_LEFT;
    case 1: return KEY_UP;
    case 2: return KEY_DOWN;
    case 3: return KEY_RIGHT;
    case 4: return KEY_SELECT;
    default: return KEY_NONE;
  }
}

KeyCode decodeKeyFromA0(int v) {
  // Above the release/no-key threshold, always regard it as no key.
  if (keypadAnalogReleased(v)) return KEY_NONE;

  int bestIdx = -1;
  int bestDiff = 32767;

  for (uint8_t i = 0; i < 5; i++) {
    int d = abs(v - (int)keypadCenter[i]);
    if (d < bestDiff) {
      bestDiff = d;
      bestIdx = i;
    }
  }

  if (bestIdx < 0) return KEY_NONE;

  // Auto-tolerance: half the gap to the closest neighboring center, with a
  // small margin removed so boundary noise is not accepted too eagerly.
  int leftGap = 1024;
  int rightGap = 1024;
  if (bestIdx > 0) leftGap = (int)keypadCenter[bestIdx] - (int)keypadCenter[bestIdx - 1];
  if (bestIdx < 4) rightGap = (int)keypadCenter[bestIdx + 1] - (int)keypadCenter[bestIdx];

  int tol = min(leftGap, rightGap) / 2 - 8;
  if (tol < 25) tol = 25;
  if (tol > 120) tol = 120;

  if (bestDiff <= tol) return keyFromIndex((uint8_t)bestIdx);
  return KEY_NONE;
}

void sendLine(const char* s) {
  Serial.println(s);
}

void sendReady() {
  sendLine("UNO_READY");
  lastReadySentMs = millis();
}

bool canSendRuntimeEvents() {
  // After an UNO reset, the Pi may still be reopening the serial port.
  // Keep the line quiet except for UNO_READY until HELLO/HB/UI confirms link.
  return piLinked && powerState == POWER_NORMAL;
}

void sendAccelProfile() {
  Serial.print(F("ACCEL:"));
  Serial.println(accelProfile);
}

void sendPotValue(int v) {
  if (!canSendRuntimeEvents()) return;
  Serial.print(F("POT:"));
  Serial.println(v);
}

void sendEncStep(int step) {
  if (!canSendRuntimeEvents()) return;
  Serial.print(F("ENC:"));
  if (step > 0) Serial.print('+');
  Serial.println(step);
}

String linkUiText();

void setLocalDisplay(const String &line1, const String &line2) {
  l1Text = line1;
  l2Text = line2;
}

void setEventLine1(const String &line1) {
  // Normal-operation LCD policy:
  //   Line 1 = transient local/event message
  //   Line 2 = current Pi/link/UI status, with P1/P2/P3 kept at right
  l1Text = line1;
}

void setCurrentStatusLine2() {
  l2Text = linkUiText();
}

void printPadded16(const String &s) {
  String t = s;
  if (t.length() > 16) t = t.substring(0, 16);
  while (t.length() < 16) t += ' ';
  lcd.print(t);
}

String makeLine2WithAccel(const String &s) {
  // Keep the current encoder acceleration profile visible at all times.
  // The bottom line uses columns 14-15 for P1/P2/P3, so the left status
  // area is limited to 13 characters plus one separator space.
  String left = s;
  if (left.length() > 13) left = left.substring(0, 13);
  while (left.length() < 13) left += ' ';
  return left + " P" + String(accelProfile);
}

String padRight(const String &s, uint8_t width) {
  String t = s;
  if (t.length() > width) t = t.substring(0, width);
  while (t.length() < width) t += ' ';
  return t;
}

const __FlashStringHelper* accelName(uint8_t p) {
  switch (p) {
    case 1: return F("FINE");
    case 2: return F("NORM");
    case 3: return F("FAST");
    default: return F("NORM");
  }
}

const __FlashStringHelper* keyName(KeyCode k) {
  switch (k) {
    case KEY_LEFT:   return F("LEFT");
    case KEY_UP:     return F("UP");
    case KEY_DOWN:   return F("DOWN");
    case KEY_RIGHT:  return F("RIGHT");
    case KEY_SELECT: return F("SEL");
    default:         return F("NONE");
  }
}

String makeButtonDebugTag(KeyCode k, bool isLongPress) {
  String head;
  switch (k) {
    case KEY_LEFT:   head = "L"; break;
    case KEY_UP:     head = "U"; break;
    case KEY_DOWN:   head = "D"; break;
    case KEY_RIGHT:  head = "R"; break;
    case KEY_SELECT: head = "S"; break;
    default:         head = "?"; break;
  }
  String tail = isLongPress ? "-LP" : "-SP";
  return padRight(head + tail, 6);
}

void setDebugTag(const String &tag) {
  debugTag = padRight(tag, 6);
  debugTagSetMs = millis();
  debugTagUntilMs = debugTagSetMs + DEBUG_TAG_HOLD_MS;
  pendingAckDebugTag = "";
  pendingAckDebugDueMs = 0;
}

void scheduleAckDebugTag(const String &tag) {
  unsigned long now = millis();
  if (debugTag.length() > 0 && (now - debugTagSetMs) < ACK_DEBUG_DELAY_MS) {
    pendingAckDebugTag = padRight(tag, 6);
    pendingAckDebugDueMs = debugTagSetMs + ACK_DEBUG_DELAY_MS;
  } else {
    setDebugTag(tag);
  }
}

void updatePendingAckDebugTag() {
  if (pendingAckDebugTag.length() == 0) return;
  if (millis() >= pendingAckDebugDueMs) {
    String tag = pendingAckDebugTag;
    pendingAckDebugTag = "";
    pendingAckDebugDueMs = 0;
    setDebugTag(tag);
  }
}

void updateDebugTagTimeout() {
  if (debugTag.length() == 0) return;
  if (millis() >= debugTagUntilMs) {
    debugTag = "";
    debugTagUntilMs = 0;
  }
}

void showButtonEvent(const String &name, bool isLongPress, KeyCode k) {
  if (powerState != POWER_NORMAL) return;
  String line1 = "BTN:" + name;
  setEventLine1(line1);
  setCurrentStatusLine2();
  setDebugTag(makeButtonDebugTag(k, isLongPress));
}

void showEncoderEvent(int step) {
  if (powerState != POWER_NORMAL) return;
  String line1 = "ENC:";
  if (step > 0) line1 += "+";
  line1 += String(step);
  setEventLine1(line1);
  setCurrentStatusLine2();
}

String linkUiText() {
  if (!piLinked) return "WAIT PI";
  if (piUiState == UI_READY) return "LNK OK UI OK";
  if (piUiState == UI_BUSY)  return "LNK OK BUSY";
  return "LINK OK UI ?";
}

void showPotEvent(int v) {
  if (powerState != POWER_NORMAL) return;
  String line1 = "POT:" + String(v);
  setEventLine1(line1);
  setCurrentStatusLine2();
}

void showAccelSetupScreen() {
  String line1 = "ACCEL SETUP";
  String line2 = "P" + String(accelDraft) + " ";
  line2 += String(accelName(accelDraft));
  if (accelDraft == accelProfile) line2 += " *";
  setLocalDisplay(line1, line2);
}


void showKeypadCalPrompt() {
  String line1 = "CAL ";
  line1 += String(keyName(keyFromIndex(keypadCalStep)));
  String line2 = "Hold key ";
  line2 += String(keypadCalStep + 1);
  line2 += "/5";
  setLocalDisplay(line1, line2);
}

void showKeypadCalReleaseAll() {
  setLocalDisplay("RELEASE ALL", "SEL+ENC off");
}

void showKeypadCalMeasuring() {
  String line1 = "MEAS ";
  line1 += String(keyName(keyFromIndex(keypadCalStep)));
  setLocalDisplay(line1, "Keep holding");
  drawStatus();
}

void showKeypadCalRelease(uint8_t capturedStep, uint16_t raw) {
  String line2 = String(keyName(keyFromIndex(capturedStep)));
  line2 += "=";
  line2 += String(raw);

  if (keypadCalStep < 5) {
    String line1 = "CAL ";
    line1 += String(keyName(keyFromIndex(keypadCalStep)));
    setLocalDisplay(line1, line2);
  } else {
    setLocalDisplay("CAL DONE", line2);
  }
}

bool canEnterKeypadCalibrationNow() {
  // Calibration is intentionally a local maintenance mode, but entering it
  // while a MIDI file is playing can confuse the Pi-side runtime/watchdog
  // state machine. PLAY:ON or PLAY:BLINK means the Pi has told UNO-1 that
  // playback is active, so refuse calibration until playback is stopped.
  return powerState == POWER_NORMAL && playLedMode == PLAY_LED_OFF;
}

void denyKeypadCalibrationDuringPlayback() {
  calDenyUntilMs = millis() + 800;
  setLocalDisplay("STOP PLAYBACK", "No CAL playing");
  setDebugTag("CAL-N ");
  startButtonLedBlink(2);
}

void enterKeypadCalibrationMode() {
  if (!canEnterKeypadCalibrationNow()) {
    denyKeypadCalibrationDuringPlayback();
    return;
  }

  keypadCalMode = true;
  keypadCalStep = 0;
  keypadCalWaitingRelease = false;
  keypadCalNeedInitialRelease = true;
  keypadCalReleaseStableSinceMs = 0;
  accelSettingMode = false;

  stableKey = KEY_NONE;
  lastSampledKey = KEY_NONE;
  keyLongSent = false;
  encSwLongSent = true;  // Consume the long press that entered calibration.

  for (uint8_t i = 0; i < 5; i++) keypadCalDraft[i] = 0;

  setDebugTag("CAL   ");
  showKeypadCalReleaseAll();
}

bool waitHeldForCalibrationCapture() {
  showKeypadCalMeasuring();
  unsigned long startMs = millis();
  unsigned long lastBlinkMsLocal = 0;
  bool backlightOn = true;

  while (millis() - startMs < CAL_HOLD_STABILIZE_MS) {
    int raw = readKeypadAdcFiltered();
    // During calibration, do not decode the held key using the existing
    // EEPROM centers. EEPROM may contain stale/wrong-but-valid values, which
    // would reject the very key we are trying to recalibrate. At this point
    // the LCD prompt defines the target key; we only require that some key is
    // held steadily in the pressed ADC region.
    if (raw > CAL_PRESS_MAX_ADC) {
      lcd.backlight();
      setLocalDisplay("CAL RETRY", "Hold key steady");
      drawStatus();
      delay(450);
      showKeypadCalPrompt();
      return false;
    }

    unsigned long now = millis();
    if (now - lastBlinkMsLocal >= CAL_LCD_BLINK_MS) {
      lastBlinkMsLocal = now;
      backlightOn = !backlightOn;
      if (backlightOn) lcd.backlight();
      else lcd.noBacklight();
    }
    delay(10);
  }

  lcd.backlight();
  drawStatus();
  return true;
}

uint16_t captureKeypadRawValue() {
  int v[CAL_CAPTURE_SAMPLES];
  unsigned long lastBlinkMsLocal = millis();
  bool backlightOn = true;

  for (uint8_t i = 0; i < CAL_CAPTURE_SAMPLES; i++) {
    v[i] = analogRead(PIN_KEYPAD);
    unsigned long now = millis();
    if (now - lastBlinkMsLocal >= CAL_LCD_BLINK_MS) {
      lastBlinkMsLocal = now;
      backlightOn = !backlightOn;
      if (backlightOn) lcd.backlight();
      else lcd.noBacklight();
    }
    delay(3);
  }

  lcd.backlight();

  for (uint8_t i = 0; i < CAL_CAPTURE_SAMPLES - 1; i++) {
    for (uint8_t j = i + 1; j < CAL_CAPTURE_SAMPLES; j++) {
      if (v[j] < v[i]) {
        int t = v[i];
        v[i] = v[j];
        v[j] = t;
      }
    }
  }

  // Trim two samples from each end and average the stable middle region.
  long sum = 0;
  uint8_t count = 0;
  for (uint8_t i = 2; i < CAL_CAPTURE_SAMPLES - 2; i++) {
    sum += v[i];
    count++;
  }

  return (uint16_t)((sum + (count / 2)) / count);
}

void failKeypadCalibration(const String &reason) {
  lcd.backlight();
  keypadCalMode = false;
  keypadCalWaitingRelease = false;
  keypadCalNeedInitialRelease = false;
  keypadCalReleaseStableSinceMs = 0;
  // Do not overwrite the existing active/EEPROM calibration on failure.
  // A failed maintenance attempt should leave the previous working values intact.
  setLocalDisplay("CAL FAILED", reason);
  setDebugTag("CAL-F ");
}

void applyAndExitKeypadCalibrationMode() {
  lcd.backlight();
  if (!keypadCentersValid(keypadCalDraft)) {
    failKeypadCalibration("Bad values");
    return;
  }

  for (uint8_t i = 0; i < 5; i++) keypadCenter[i] = keypadCalDraft[i];
  saveKeypadCalibration(keypadCenter);

  keypadCalMode = false;
  keypadCalWaitingRelease = false;
  keypadCalNeedInitialRelease = false;
  keypadCalReleaseStableSinceMs = 0;
  setLocalDisplay("CAL SAVED", "EEPROM OK");
  setDebugTag("CAL-S ");
}

void updateKeypadCalibration() {
  if (!keypadCalMode) return;

  // If the Pi starts or resumes playback while calibration is open, leave the
  // maintenance mode without saving. This keeps the runtime serial protocol
  // deterministic during music playback.
  if (playLedMode != PLAY_LED_OFF || powerState != POWER_NORMAL) {
    keypadCalMode = false;
    keypadCalWaitingRelease = false;
    keypadCalNeedInitialRelease = false;
    keypadCalReleaseStableSinceMs = 0;
    setLocalDisplay("CAL ABORTED", "Playback active");
    setDebugTag("CAL-A ");
    return;
  }

  int raw = readKeypadAdcFiltered();
  unsigned long now = millis();

  // Critical guard after ENC+SELECT entry:
  // Do not accept the SELECT-release glitch, ADC bounce, or any leftover key
  // state as the first LEFT calibration sample. Calibration starts only after
  // A0 has been in the no-key region continuously for CAL_RELEASE_STABLE_MS.
  if (keypadCalNeedInitialRelease) {
    if (calibrationEntryControlsReleased(raw)) {
      if (keypadCalReleaseStableSinceMs == 0) keypadCalReleaseStableSinceMs = now;
      if ((now - keypadCalReleaseStableSinceMs) >= CAL_RELEASE_STABLE_MS) {
        keypadCalNeedInitialRelease = false;
        keypadCalReleaseStableSinceMs = 0;
        showKeypadCalPrompt();
      }
    } else {
      keypadCalReleaseStableSinceMs = 0;
      String line2 = "A0=" + String(raw);
      if (encSwStable == LOW) line2 = "ENC still ON";
      setLocalDisplay("RELEASE ALL", line2);
    }
    return;
  }

  // After each successful key capture, require a real release before accepting
  // the next key. The step is advanced immediately at capture time, so the LCD
  // can show the next requested key right away instead of staying on CAL LEFT.
  if (keypadCalWaitingRelease) {
    if (keypadAnalogReleased(raw)) {
      if (keypadCalReleaseStableSinceMs == 0) keypadCalReleaseStableSinceMs = now;
      if ((now - keypadCalReleaseStableSinceMs) >= CAL_RELEASE_STABLE_MS) {
        keypadCalWaitingRelease = false;
        keypadCalReleaseStableSinceMs = 0;

        if (keypadCalStep >= 5) {
          // The entry gesture is already deliberate, so avoid another fragile
          // SAVE/DISCARD button step. Save automatically after validation.
          if (keypadCentersValid(keypadCalDraft)) {
            setLocalDisplay("VERIFYING...", "Please wait");
            drawStatus();
            delay(350);
            applyAndExitKeypadCalibrationMode();
          } else {
            failKeypadCalibration("Check order");
          }
        } else {
          showKeypadCalPrompt();
        }
      }
    } else {
      keypadCalReleaseStableSinceMs = 0;
    }
    return;
  }

  if (keypadCalStep >= 5) return;

  // Calibration capture must not depend on current EEPROM centers.
  // The user follows the LCD sequence: LEFT -> UP -> DOWN -> RIGHT -> SELECT.
  // We therefore accept any stable press and store its raw A0 value into the
  // current step. Final validation still checks monotonic order and spacing.
  if (raw <= CAL_PRESS_MAX_ADC) {
    delay(DEBOUNCE_MS);
    raw = readKeypadAdcFiltered();

    if (raw <= CAL_PRESS_MAX_ADC) {
      if (!waitHeldForCalibrationCapture()) {
        return;
      }
      uint8_t capturedStep = keypadCalStep;
      uint16_t captured = captureKeypadRawValue();
      keypadCalDraft[capturedStep] = captured;

      // Advance immediately after a valid capture. This gives clear feedback
      // that LEFT was accepted and the next target is now UP, while
      // keypadCalWaitingRelease still prevents the held LEFT key from being
      // interpreted as another calibration input.
      keypadCalStep++;

      lcd.backlight();
      showKeypadCalRelease(capturedStep, captured);  // Solid LCD: measurement for this key is OK.
      drawStatus();
      keypadCalWaitingRelease = true;
      keypadCalReleaseStableSinceMs = 0;
      startButtonLedBlink(1);
    }
  }
}
void drawStatus() {
  updateDebugTagTimeout();

  // During power transition screens, use the full 16x2 LCD area.
  // Do not reserve the right side for the button debug tag or P1/P2/P3,
  // because messages such as "UNPLUG ADAPTER" must be shown completely.
  if (powerState != POWER_NORMAL) {
    lcd.setCursor(0, 0);
    printPadded16(l1Text);
    lcd.setCursor(0, 1);
    printPadded16(l2Text);
    return;
  }

  lcd.setCursor(0, 0);

  String line1 = l1Text;
  if (line1.length() > 10) line1 = line1.substring(0, 10);
  while (line1.length() < 10) line1 += ' ';

  String right6 = debugTag.length() > 0 ? padRight(debugTag, 6) : "      ";
  lcd.print(line1 + right6);

  lcd.setCursor(0, 1);
  lcd.print(makeLine2WithAccel(l2Text));
}

void reinitLcdController() {
  // Software recovery layer for the I2C LCD backpack/HD44780 state.
  // Cold start already performs lcd.init() in setup(); this function is used
  // at the second critical transition: first Raspberry Pi serial link.
  lcd.init();
  lcd.backlight();
  lcd.clear();
}

void notePiSeen() {
  lastPiSeenMs = millis();
  piLinked = true;
  everLinked = true;

  // If the link temporarily returns while a power transition is armed,
  // discard any earlier link-lost timestamp. Safe-to-unplug must be based
  // on the final heartbeat loss, not on a transient USB/serial gap.
  if (powerState == POWER_SHUTDOWN_ARMED || powerState == POWER_REBOOT_ARMED) {
    powerLinkLostMs = 0;
  }
}

bool powerMessageAllowed() {
  // Accept power-state commands only after a live Pi link exists.
  // This prevents boot-wait, USB replug, or PC firmware-upload situations
  // from being mistaken for a completed shutdown.
  return piLinked && everLinked;
}

void armShutdownDisplay() {
  if (!powerMessageAllowed()) return;
  powerState = POWER_SHUTDOWN_ARMED;
  powerCommandMs = millis();
  // Start fresh for every shutdown command. The safe timer starts only
  // after the heartbeat/link is actually lost in updateLinkLed().
  powerLinkLostMs = 0;
  setPlayLedMode(PLAY_LED_OFF);
  setLocalDisplay("SHUTTING DOWN", "PLEASE WAIT");
}

void armRebootDisplay() {
  if (!powerMessageAllowed()) return;
  powerState = POWER_REBOOT_ARMED;
  powerCommandMs = millis();
  powerLinkLostMs = 0;
  setPlayLedMode(PLAY_LED_OFF);
  setLocalDisplay("REBOOTING", "PLEASE WAIT");
}

void showPowerOffOk() {
  powerState = POWER_OFF_OK;
  setPlayLedMode(PLAY_LED_OFF);
  digitalWrite(PIN_LED_LINK, LOW);
  linkLedState = false;
  setLocalDisplay("POWER OFF OK", "UNPLUG ADAPTER");
}

void restartShutdownWaitIfPowerOk() {
  if (powerState == POWER_OFF_OK) {
    powerState = POWER_SHUTDOWN_ARMED;
    powerLinkLostMs = 0;
    setLocalDisplay("FINALIZING", "PLEASE WAIT");
  }
}

void pulseMidiLed() {
  buttonLedBlinkActive = false;
  digitalWrite(PIN_LED_MIDI, HIGH);
  midiLedUntilMs = millis() + MIDI_LED_PULSE_MS;
}

void startButtonLedBlink(uint8_t blinkCount) {
  if (blinkCount == 0) return;
  buttonLedBlinkActive = true;
  buttonLedBlinkRemainingToggles = blinkCount * 2;
  buttonLedBlinkState = true;
  digitalWrite(PIN_LED_MIDI, HIGH);
  midiLedUntilMs = 0;
  buttonLedBlinkNextMs = millis() + BUTTON_LED_BLINK_ON_MS;
}

void holdInputLed() {
  // Keep D11 on while local analog/encoder input is actively changing.
  // Repeated encoder/pot events extend this timeout, so the LED appears
  // continuously ON during adjustment and turns off shortly afterward.
  buttonLedBlinkActive = false;
  digitalWrite(PIN_LED_MIDI, HIGH);
  midiLedUntilMs = millis() + INPUT_LED_HOLD_MS;
}

void setPlayLedMode(PlayLedMode mode) {
  playLedMode = mode;
  playLedLastToggleMs = millis();
  if (mode == PLAY_LED_OFF) {
    playLedState = false;
    digitalWrite(PIN_LED_PLAY, LOW);
  } else if (mode == PLAY_LED_ON) {
    playLedState = true;
    digitalWrite(PIN_LED_PLAY, HIGH);
  } else {
    playLedState = true;
    digitalWrite(PIN_LED_PLAY, HIGH);
  }
}

void updatePlayLed() {
  if (playLedMode != PLAY_LED_BLINK) return;
  unsigned long now = millis();
  if (now - playLedLastToggleMs >= PLAY_LED_BLINK_MS) {
    playLedLastToggleMs = now;
    playLedState = !playLedState;
    digitalWrite(PIN_LED_PLAY, playLedState ? HIGH : LOW);
  }
}

void updateLinkLed() {
  unsigned long now = millis();

  if (piLinked && (now - lastPiSeenMs > LINK_TIMEOUT_MS)) {
    piLinked = false;
    piUiState = UI_UNKNOWN;
    if (powerState == POWER_SHUTDOWN_ARMED) {
      powerLinkLostMs = now;
      setLocalDisplay("FINALIZING", "PLEASE WAIT");
    } else if (powerState == POWER_REBOOT_ARMED) {
      powerLinkLostMs = now;
      setLocalDisplay("REBOOTING", "WAIT PI");
    } else if (powerState != POWER_OFF_OK) {
      setLocalDisplay("LINK LOST", "WAIT HELLO/HB");
    }
  }

  // Safe-to-unplug is shown only after:
  //   1) a valid PWR:SHUTDOWN was received while linked,
  //   2) HB/HELLO has timed out, and
  //   3) an additional post-link-loss safety delay has elapsed.
  if (powerState == POWER_SHUTDOWN_ARMED && !piLinked && powerLinkLostMs != 0 &&
      (now - powerLinkLostMs >= POWER_SAFE_DELAY_MS)) {
    showPowerOffOk();
  }

  if (powerState == POWER_REBOOT_ARMED && !piLinked && powerLinkLostMs != 0 &&
      (now - powerLinkLostMs >= POWER_SAFE_DELAY_MS)) {
    // Reboot is not a safe-unplug condition. Return to ordinary Pi-wait mode.
    powerState = POWER_NORMAL;
    powerLinkLostMs = 0;
    setLocalDisplay("WAIT PI", "REBOOT");
  }

  if (powerState == POWER_OFF_OK) {
    digitalWrite(PIN_LED_LINK, LOW);
    return;
  }

  if (piLinked) {
    digitalWrite(PIN_LED_LINK, HIGH);
    return;
  }

  if (now - lastBlinkMs >= LINK_BLINK_MS) {
    lastBlinkMs = now;
    linkLedState = !linkLedState;
    digitalWrite(PIN_LED_LINK, linkLedState ? HIGH : LOW);
  }
}

void updateMidiLed() {
  unsigned long now = millis();

  if (buttonLedBlinkActive) {
    if (now >= buttonLedBlinkNextMs) {
      buttonLedBlinkState = !buttonLedBlinkState;
      digitalWrite(PIN_LED_MIDI, buttonLedBlinkState ? HIGH : LOW);

      if (buttonLedBlinkRemainingToggles > 0) {
        buttonLedBlinkRemainingToggles--;
      }

      if (buttonLedBlinkRemainingToggles == 0) {
        buttonLedBlinkActive = false;
        buttonLedBlinkState = false;
        digitalWrite(PIN_LED_MIDI, LOW);
        midiLedUntilMs = 0;
      } else {
        buttonLedBlinkNextMs = now + (buttonLedBlinkState ? BUTTON_LED_BLINK_ON_MS : BUTTON_LED_BLINK_OFF_MS);
      }
    }
    return;
  }

  if (midiLedUntilMs != 0 && now >= midiLedUntilMs) {
    digitalWrite(PIN_LED_MIDI, LOW);
    midiLedUntilMs = 0;
  }
}

void setAccelDraftDelta(int delta) {
  int next = (int)accelDraft + delta;
  if (next < 1) next = 1;
  if (next > 3) next = 3;
  accelDraft = (uint8_t)next;
  showAccelSetupScreen();
}

int calcAccelMultiplier(unsigned long dt, uint8_t profile) {
  const AccelProfile &p = ACCEL_TABLE[profile - 1];
  if (dt <= p.tFast) return 3;
  if (dt <= p.tMedium) return 2;
  return 1;
}

void enterAccelSettingMode() {
  accelSettingMode = true;
  accelDraft = accelProfile;
  stableKey = KEY_NONE;
  lastSampledKey = KEY_NONE;
  keyLongSent = false;
  showAccelSetupScreen();
}

void applyAndExitAccelSettingMode() {
  accelProfile = accelDraft;
  accelSettingMode = false;
  sendAccelProfile();
  setEventLine1("ACCEL APPL");
  setCurrentStatusLine2();
}

void cycleAccelProfileByEncoderLongPress() {
  accelProfile++;
  if (accelProfile > 3) accelProfile = 1;
  accelDraft = accelProfile;
  accelSettingMode = false;
  sendAccelProfile();

  String line1 = "ENC ACCEL";
  setEventLine1(line1);
  setCurrentStatusLine2();
  setDebugTag("E-LP  ");
}


bool encoderSelectComboHeld() {
  return encSwStable == LOW && stableKey == KEY_SELECT;
}

void resetEncoderSelectComboState() {
  calComboStartMs = 0;
  calComboConsumed = false;
  selectEncOverlap = false;
}

void updateKeypadCalibrationEntryCombo() {
  if (keypadCalMode || accelSettingMode || powerState != POWER_NORMAL) {
    resetEncoderSelectComboState();
    return;
  }

  if (encoderSelectComboHeld()) {
    selectEncOverlap = true;
    if (calComboStartMs == 0) calComboStartMs = millis();

    if (!calComboConsumed && (millis() - calComboStartMs) >= CAL_COMBO_HOLD_MS) {
      calComboConsumed = true;

      // Consume both physical inputs. Do not leak SELECT/ENC long or short
      // messages to the Pi when this maintenance combo is used.
      keyLongSent = true;
      encSwLongSent = true;

      enterKeypadCalibrationMode();
    }
    return;
  }

  // If either side of the combo is released before the hold time, leave the
  // overlap flag in place until SELECT release so updateKeypad() can suppress
  // a stray BTN:SEL short event from a failed calibration-entry attempt.
  if (encSwStable != LOW && stableKey != KEY_SELECT) {
    resetEncoderSelectComboState();
  } else {
    calComboStartMs = 0;
  }
}

void sendButtonMessage(KeyCode k, bool isLongPress) {
  if (!canSendRuntimeEvents()) return;
  switch (k) {
    case KEY_LEFT:   sendLine(isLongPress ? "BTN:LEFT_LP"  : "BTN:LEFT"); break;
    case KEY_UP:     sendLine(isLongPress ? "BTN:UP_LP"    : "BTN:UP"); break;
    case KEY_DOWN:   sendLine(isLongPress ? "BTN:DOWN_LP"  : "BTN:DOWN"); break;
    case KEY_RIGHT:  sendLine(isLongPress ? "BTN:RIGHT_LP" : "BTN:RIGHT"); break;
    case KEY_SELECT: sendLine(isLongPress ? "BTN:SEL_LP"   : "BTN:SEL"); break;
    default: break;
  }
  startButtonLedBlink(isLongPress ? 2 : 1);
  showButtonEvent(String(keyName(k)), isLongPress, k);
}

void updateKeypad() {
  if (keypadCalMode) return;

  int raw = readKeypadAdcFiltered();
  KeyCode sampled = decodeKeyFromA0(raw);
  unsigned long now = millis();

  if (sampled != lastSampledKey) {
    lastSampledKey = sampled;
    keyChangedMs = now;
  }

  if ((now - keyChangedMs) < DEBOUNCE_MS) return;

  if (sampled == stableKey) {
    if (stableKey != KEY_NONE && !keyLongSent && (now - keyPressedMs) >= LONGPRESS_MS) {
      if (!accelSettingMode) {
        // SELECT is part of the local maintenance combo with the encoder
        // switch. While the encoder is held, do not send BTN:SEL_LP to Pi.
        if (!(stableKey == KEY_SELECT && encSwStable == LOW)) {
          sendButtonMessage(stableKey, true);
        }
      }
      keyLongSent = true;
    }
    return;
  }

  KeyCode prevStable = stableKey;
  stableKey = sampled;

  // Previous key released: emit exactly one short event if long press was not sent.
  if (prevStable != KEY_NONE && stableKey == KEY_NONE) {
    if (!keyLongSent) {
      if (accelSettingMode) {
        switch (prevStable) {
          case KEY_UP:     setAccelDraftDelta(+1); break;
          case KEY_DOWN:   setAccelDraftDelta(-1); break;
          case KEY_SELECT: applyAndExitAccelSettingMode(); break;
          case KEY_LEFT:   accelSettingMode = false; setEventLine1("ACCEL CANC"); setCurrentStatusLine2(); break;
          default: break;
        }
      } else {
        // If SELECT overlapped with the encoder switch, it was an attempted
        // local maintenance combo. Suppress the short SELECT message too;
        // otherwise the Pi-side UI may receive an unintended SELECT.
        if (!(prevStable == KEY_SELECT && selectEncOverlap)) {
          sendButtonMessage(prevStable, false);
        }
      }
    }
    keyPressedMs = 0;
    keyLongSent = false;
    return;
  }

  // New key pressed: start timing only. Short press will be decided on release.
  if (stableKey != KEY_NONE) {
    keyPressedMs = now;
    keyLongSent = false;
  }
}

void encoderIsrUpdate() {
  uint8_t encoded = (digitalRead(PIN_ENC_A) == HIGH ? 0x02 : 0x00) |
                    (digitalRead(PIN_ENC_B) == HIGH ? 0x01 : 0x00);

  if (!encIsrReady) {
    encIsrLastEncoded = encoded;
    encIsrReady = true;
    return;
  }

  if (encoded == encIsrLastEncoded) return;

  uint8_t transition = (encIsrLastEncoded << 2) | encoded;
  int8_t delta = 0;

  // Same valid-transition table as the former polling decoder.
  switch (transition) {
    case 0b0001:
    case 0b0111:
    case 0b1110:
    case 0b1000:
      delta = -1;
      break;
    case 0b0010:
    case 0b1011:
    case 0b1101:
    case 0b0100:
      delta = +1;
      break;
    default:
      delta = 0;
      break;
  }

  if (delta != 0) {
    // Direction reversal before a complete detent should not consume the first
    // click after reversal. Discard the unfinished partial step, as before.
    if (encIsrTransitionAccum != 0 &&
        ((delta > 0 && encIsrTransitionAccum < 0) ||
         (delta < 0 && encIsrTransitionAccum > 0))) {
      encIsrTransitionAccum = 0;
    }

    encIsrTransitionAccum += delta;

    if (encIsrTransitionAccum >= ENC_TRANSITIONS_PER_STEP) {
      encIsrTransitionAccum = 0;
      if (encIsrStepAccum < 100) encIsrStepAccum++;
    } else if (encIsrTransitionAccum <= -ENC_TRANSITIONS_PER_STEP) {
      encIsrTransitionAccum = 0;
      if (encIsrStepAccum > -100) encIsrStepAccum--;
    }
  } else {
    // Illegal two-bit jumps are treated as bounce/noise and resynced.
    encIsrTransitionAccum = 0;
  }

  encIsrLastEncoded = encoded;
}

void encoderIsrA() {
  encoderIsrUpdate();
}

void encoderIsrB() {
  encoderIsrUpdate();
}

void processEncoderDirection(int direction, unsigned long now) {
  holdInputLed();

  if (keypadCalMode) {
    // Ignore encoder rotation during keypad calibration.
  } else if (accelSettingMode) {
    setAccelDraftDelta(direction);
  } else {
    unsigned long dt = (lastEncStepMs == 0) ? 9999UL : (now - lastEncStepMs);
    int mult = calcAccelMultiplier(dt, accelProfile);
    int step = direction * mult;
    sendEncStep(step);
    showEncoderEvent(step);
    lastEncStepMs = now;
  }
}

void consumeEncoderIsrSteps(unsigned long now) {
  int8_t pending;

  noInterrupts();
  pending = encIsrStepAccum;
  encIsrStepAccum = 0;
  interrupts();

  while (pending > 0) {
    processEncoderDirection(+1, now);
    pending--;
  }

  while (pending < 0) {
    processEncoderDirection(-1, now);
    pending++;
  }
}

void updateEncoder() {
  unsigned long now = millis();

  consumeEncoderIsrSteps(now);

  int sw = digitalRead(PIN_ENC_SW);
  if (sw != lastEncSw) {
    lastEncSw = sw;
    encSwChangedMs = now;
  }

  if ((now - encSwChangedMs) >= DEBOUNCE_MS && sw != encSwStable) {
    encSwStable = sw;

    if (encSwStable == LOW) {
      // Do not emit ENC_PUSH immediately. Wait until release so a long press
      // can be used exclusively for acceleration-profile cycling.
      encSwPressedMs = now;
      encSwLongSent = false;
    } else {
      // Released. If no long press was already handled, emit the normal short
      // encoder-push button event.
      if (encSwPressedMs != 0 && !encSwLongSent) {
        if (keypadCalMode) {
          // Encoder short press is deliberately ignored in calibration mode.
        } else if (accelSettingMode) {
          applyAndExitAccelSettingMode();
          startButtonLedBlink(1);
          setDebugTag("E-SP  ");
        } else {
          // If this encoder press overlapped SELECT, treat it as a local
          // calibration-entry attempt and do not leak ENC_PUSH to the Pi.
          if (!selectEncOverlap) {
            if (canSendRuntimeEvents()) sendLine("BTN:ENC_PUSH");
            startButtonLedBlink(1);
            setEventLine1("BTN:ENCPSH");
            setCurrentStatusLine2();
            setDebugTag("E-SP  ");
          }
        }
      }
      encSwPressedMs = 0;
      encSwLongSent = false;
    }
  }

  if (encSwStable == LOW && !encSwLongSent && encSwPressedMs != 0 && (now - encSwPressedMs) >= LONGPRESS_MS) {
    // Encoder + SELECT is handled by updateKeypadCalibrationEntryCombo().
    // Do not treat it as the normal encoder long press.
    if (!keypadCalMode && stableKey == KEY_SELECT) {
      return;
    }

    startButtonLedBlink(2);
    if (keypadCalMode) {
      if (keypadCalStep >= 5) {
        applyAndExitKeypadCalibrationMode();
      } else {
        lcd.backlight();
        keypadCalMode = false;
        keypadCalWaitingRelease = false;
        keypadCalNeedInitialRelease = false;
        keypadCalReleaseStableSinceMs = 0;
        setLocalDisplay("CAL CANCEL", "Not saved");
        setDebugTag("CAL-C ");
      }
    } else {
      cycleAccelProfileByEncoderLongPress();
    }
    encSwLongSent = true;
  }
}

void updatePot() {
  if (keypadCalMode) return;

  unsigned long now = millis();
  int raw = analogRead(PIN_POT);

  // Keep POT reporting reasonably sensitive for Pi-side volume/control.
  bool shouldSend = (abs(raw - lastPotSent) >= POT_DELTA_SEND && (now - lastPotSentMs) >= POT_SEND_MS);

  if (shouldSend) {
    sendPotValue(raw);
    showPotEvent(raw);
    lastPotSent = raw;
    lastPotSentMs = now;
  }

  // Use a larger, independent threshold for the local activity LED.
  // This prevents small A2 noise, especially when connected to Pi USB/ground,
  // from continuously extending the D11 hold timer.
  if (lastPotLedRaw < 0) {
    lastPotLedRaw = raw;
  } else if (abs(raw - lastPotLedRaw) >= POT_DELTA_LED) {
    holdInputLed();
    lastPotLedRaw = raw;
  }
}

void handleIncomingLine(String s) {
  s.trim();
  if (s.length() == 0) return;

  if (s == "HELLO") {
    bool wasLinked = piLinked;
    bool firstLink = !wasLinked;

    notePiSeen();

    // The I2C LCD is fully initialized at cold start, but the first Pi link
    // establishment is a second critical state transition. Reinitialize the
    // LCD once here so a marginal or glitched LCD controller/backpack state is
    // realigned before the linked status is drawn. Avoid doing this during
    // keypad calibration because calibration deliberately controls the LCD.
    if (firstLink && !keypadCalMode) {
      reinitLcdController();
    }

    if (powerState == POWER_REBOOT_ARMED) {
      powerState = POWER_NORMAL;
      powerLinkLostMs = 0;
      if (firstLink) setLocalDisplay("PI LINKED", linkUiText());
    } else if (powerState == POWER_OFF_OK) {
      // If communication resumes after the safe-unplug screen, the Pi was not
      // really finished. Re-arm shutdown instead of falling back to WAIT PI.
      powerState = POWER_SHUTDOWN_ARMED;
      powerLinkLostMs = 0;
      setLocalDisplay("FINALIZING", "PLEASE WAIT");
    } else if (firstLink) {
      setLocalDisplay("PI LINKED", linkUiText());
    }

    if (firstLink && !keypadCalMode) {
      drawStatus();
      lastLcdRefreshMs = millis();
    }

    sendReady();
    sendAccelProfile();
    return;
  }

  if (s == "HB") {
    bool wasLinked = piLinked;
    notePiSeen();
    if (powerState == POWER_REBOOT_ARMED) {
      powerState = POWER_NORMAL;
      powerLinkLostMs = 0;
      setLocalDisplay("PI LINKED", linkUiText());
    } else if (powerState == POWER_OFF_OK) {
      // If any heartbeat comes back after POWER_OFF_OK, the OK screen was
      // premature. Go back to shutdown-finalizing mode and restart the safe timer.
      powerState = POWER_SHUTDOWN_ARMED;
      powerLinkLostMs = 0;
      setLocalDisplay("FINALIZING", "PLEASE WAIT");
    } else if (!wasLinked && powerState == POWER_NORMAL && !keypadCalMode) {
      // If HB is the first message after a timeout, clear any stale LINK LOST
      // line immediately. Otherwise line 1 may remain stale until local input.
      setLocalDisplay("PI LINKED", linkUiText());
      drawStatus();
      lastLcdRefreshMs = millis();
    }
    return;
  }

  if (s == "UI:READY") {
    bool wasLinked = piLinked;
    notePiSeen();
    restartShutdownWaitIfPowerOk();
    piUiState = UI_READY;
    lastUiSeenMs = millis();
    if (powerState == POWER_NORMAL) {
      if (!wasLinked && !keypadCalMode) {
        // UI:READY may be the first message after a timeout. Refresh both
        // lines so stale LINK LOST is not left on line 1.
        setLocalDisplay("PI LINKED", linkUiText());
        drawStatus();
        lastLcdRefreshMs = millis();
      } else {
        setCurrentStatusLine2();
      }
    }
    return;
  }

  if (s == "UI:BUSY") {
    bool wasLinked = piLinked;
    notePiSeen();
    restartShutdownWaitIfPowerOk();
    piUiState = UI_BUSY;
    lastUiSeenMs = millis();
    if (powerState == POWER_NORMAL) {
      if (!wasLinked && !keypadCalMode) {
        // UI:BUSY may be the first message after a timeout. Refresh both
        // lines so stale LINK LOST is not left on line 1.
        setLocalDisplay("PI LINKED", linkUiText());
        drawStatus();
        lastLcdRefreshMs = millis();
      } else {
        setCurrentStatusLine2();
      }
    }
    return;
  }

  if (s == "ACK:BTN") {
    notePiSeen();
    restartShutdownWaitIfPowerOk();
    scheduleAckDebugTag("ACK-B ");
    return;
  }

  if (s == "ACK:ENC") {
    notePiSeen();
    restartShutdownWaitIfPowerOk();
    scheduleAckDebugTag("ACK-E ");
    return;
  }

  if (s == "ACT:MIDI") {
    notePiSeen();
    restartShutdownWaitIfPowerOk();
    pulseMidiLed();
    return;
  }

  if (s == "PLAY:OFF") {
    notePiSeen();
    restartShutdownWaitIfPowerOk();
    setPlayLedMode(PLAY_LED_OFF);
    return;
  }

  if (s == "PLAY:ON") {
    notePiSeen();
    restartShutdownWaitIfPowerOk();
    setPlayLedMode(PLAY_LED_ON);
    return;
  }

  if (s == "PLAY:BLINK") {
    notePiSeen();
    restartShutdownWaitIfPowerOk();
    setPlayLedMode(PLAY_LED_BLINK);
    return;
  }

  if (s == "PWR:SHUTDOWN" || s == "SHUTDOWN") {
    if (powerMessageAllowed()) {
      notePiSeen();
      armShutdownDisplay();
    }
    return;
  }

  if (s == "PWR:REBOOT" || s == "REBOOT") {
    if (powerMessageAllowed()) {
      notePiSeen();
      armRebootDisplay();
    }
    return;
  }

  // Ignore legacy Pi->Uno messages such as SF:, VOL:, STATUS:, PAGE:, GAIN:
}

void updateSerialRx() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (rxLine.length() > 0) {
        handleIncomingLine(rxLine);
        rxLine = "";
      }
    } else {
      if (rxLine.length() < 80) rxLine += c;
    }
  }
}

void setup() {
  pinMode(PIN_ENC_A, INPUT_PULLUP);
  pinMode(PIN_ENC_B, INPUT_PULLUP);
  pinMode(PIN_ENC_SW, INPUT_PULLUP);
  pinMode(PIN_LED_LINK, OUTPUT);
  pinMode(PIN_LED_PLAY, OUTPUT);
  pinMode(PIN_LED_MIDI, OUTPUT);

  // Initialize quadrature state before enabling interrupts. On UNO, D2/D3
  // map to interrupt 0/1, so both A and B edges are captured immediately.
  encIsrLastEncoded = (digitalRead(PIN_ENC_A) == HIGH ? 0x02 : 0x00) |
                      (digitalRead(PIN_ENC_B) == HIGH ? 0x01 : 0x00);
  encIsrTransitionAccum = 0;
  encIsrStepAccum = 0;
  encIsrReady = true;
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_A), encoderIsrA, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_B), encoderIsrB, CHANGE);

  digitalWrite(PIN_LED_LINK, LOW);
  digitalWrite(PIN_LED_PLAY, LOW);
  digitalWrite(PIN_LED_MIDI, LOW);

  Serial.begin(115200);
  analogReference(DEFAULT);
  loadKeypadCalibration();

  lcd.init();
  lcd.backlight();
  lcd.clear();
  setLocalDisplay("UNO-1", "WAIT HELLO/HB");
  drawStatus();

  // Give the Pi several chances to catch UNO_READY while its serial
  // reconnect handler is still settling after an UNO reset. Runtime messages
  // such as ACCEL/POT are deliberately not sent here; ACCEL is sent after HELLO.
  for (uint8_t i = 0; i < 3; i++) {
    delay(120);
    sendReady();
  }
}

void loop() {
  updateSerialRx();
  updatePlayLed();
  updateKeypadCalibration();
  updateKeypad();
  updateKeypadCalibrationEntryCombo();
  updateEncoder();
  updatePot();
  updateLinkLed();
  updateMidiLed();

  unsigned long now = millis();

  unsigned long readyInterval;
  if (keypadCalMode) {
    // Calibration deliberately suppresses runtime BTN/ENC/POT events, but the
    // serial link should not look dead to the Pi-side monitor.
    readyInterval = READY_REPEAT_CAL_MS;
  } else {
    readyInterval = piLinked ? READY_REPEAT_MS : READY_REPEAT_UNLINKED_MS;
  }
  if ((now - lastReadySentMs) >= readyInterval) {
    sendReady();
  }

  updatePendingAckDebugTag();

  if (calDenyUntilMs != 0 && now >= calDenyUntilMs && !keypadCalMode && powerState == POWER_NORMAL) {
    calDenyUntilMs = 0;
    setEventLine1("RUN MODE");
    setCurrentStatusLine2();
  }

  if ((now - lastLcdRefreshMs) >= LCD_REFRESH_MS) {
    drawStatus();
    lastLcdRefreshMs = now;
  }
}
