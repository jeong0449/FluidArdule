/*
  Fluid Ardule UNO-1 integrated diagnostic firmware
  1602 I2C LCD edition
*/

#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// --------------------------------------------------
// User-editable version
// --------------------------------------------------
const char FW_VERSION[] = "v2026-04-18a";

// --------------------------------------------------
// LCD
// --------------------------------------------------
LiquidCrystal_I2C lcd(0x27, 16, 2);   // change to 0x3F if needed

// --------------------------------------------------
// Pins
// --------------------------------------------------
#define ENC_A   2
#define ENC_B   3
#define ENC_SW  A1
#define KEY_PIN A0
#define POT_PIN A2
#define LED_PIN LED_BUILTIN
#define LED_READY LED_PIN
#define LED_PRESS 12
#define LED_ACTIVITY 11

// --------------------------------------------------
// Button codes
// --------------------------------------------------
#define BTN_NONE   0
#define BTN_RIGHT  1
#define BTN_UP     2
#define BTN_DOWN   3
#define BTN_LEFT   4
#define BTN_SELECT 5

// --------------------------------------------------
// Measured threshold map from user's board
// --------------------------------------------------
const int ADC_THR_LEFT   = 180;
const int ADC_THR_UP     = 280;
const int ADC_THR_DOWN   = 450;
const int ADC_THR_RIGHT  = 650;
const int ADC_THR_SELECT = 900;

// --------------------------------------------------
// Encoder state (ISR/shared)
// --------------------------------------------------
volatile uint8_t encLastState = 0;
volatile int8_t encQuarterAcc = 0;
volatile long encPendingSteps = 0;
volatile unsigned long edgeCountA = 0;
volatile unsigned long edgeCountB = 0;

int lastSW = HIGH;
unsigned long swPressCount = 0;
unsigned long swLongPressCount = 0;
bool swLatchedPressed = false;
bool swLatchedLongTriggered = false;
unsigned long swLatchedPressedAt = 0;

long logicalPos = 0;
long encStepCount = 0;

const int8_t ENC_TABLE[16] = {
   0, -1,  1,  0,
   1,  0,  0, -1,
  -1,  0,  0,  1,
   0,  1, -1,  0
};

// --------------------------------------------------
// Gain
// --------------------------------------------------
int gainModeIndex = 1; // start x2
const uint8_t gainTable[4] = {1, 2, 3, 4};

// --------------------------------------------------
// LCD refresh / page
// --------------------------------------------------
unsigned long lastLcdUpdate = 0;
const unsigned long LCD_INTERVAL_MS = 100;
uint8_t lcdPage = 0;

const unsigned long LONG_PRESS_MS = 700;
unsigned long gainDisplayUntil = 0;
const unsigned long LAST_BTN_HOLD_MS = 1000;
const unsigned long POT_PRANK_INTERVAL_MS = 1000;

const unsigned long SHORT_BLINK_MS = 60;
const unsigned long DOUBLE_BLINK_GAP_MS = 40;
const unsigned long ACTIVITY_HOLD_MS = 80;

bool deviceReady = false;
unsigned long ledPressPhaseUntil = 0;
uint8_t ledPressPhase = 0;  // 0=idle, 1=ON(short or first), 2=gap before second, 3=second ON
bool ledPressDouble = false;
unsigned long ledActivityUntil = 0;

// display smoothing
const uint8_t DISPLAY_AVG_N = 4;
int btnAdcHist[DISPLAY_AVG_N] = {1023,1023,1023,1023};
uint8_t btnAdcHistPos = 0;
long btnAdcHistSum = 1023L * DISPLAY_AVG_N;
int buttonAdcDisplay = 1023;

int potCCHist[DISPLAY_AVG_N] = {0,0,0,0};
uint8_t potCCHistPos = 0;
int potCCHistSum = 0;
int potCCDisplay = 0;

// --------------------------------------------------
// Keypad state
// --------------------------------------------------
int stableBtn = BTN_NONE;
int rawBtnNow = BTN_NONE;

unsigned long btnPressCount[6] = {0,0,0,0,0,0};
int buttonAdcRaw = 1023;
int latchedPressedBtn = BTN_NONE;
bool latchedLongTriggered = false;
unsigned long latchedPressedAt = 0;

int lastCompletedBtn = BTN_NONE;
bool lastCompletedWasLongPress = false;
unsigned long lastCompletedBtnAt = 0;

// --------------------------------------------------
// Pot state
// --------------------------------------------------
int potRaw = 0;
int potAvg = 0;
int potCC = 0;
int lastPotCC = -1;

bool prankModeActive = false;
bool prankScreenToggle = false;
unsigned long lastPrankToggle = 0;

// --------------------------------------------------
// Encoder acceleration state
// --------------------------------------------------
unsigned long lastStepUs = 0;

// --------------------------------------------------
// Helpers
// --------------------------------------------------
const __FlashStringHelper* buttonNameF(int btn) {
  switch (btn) {
    case BTN_RIGHT:  return F("RIGHT");
    case BTN_UP:     return F("UP");
    case BTN_DOWN:   return F("DOWN");
    case BTN_LEFT:   return F("LEFT");
    case BTN_SELECT: return F("SELECT");
    default:         return F("NONE");
  }
}

const __FlashStringHelper* buttonShortF(int btn) {
  switch (btn) {
    case BTN_RIGHT:  return F("R");
    case BTN_UP:     return F("U");
    case BTN_DOWN:   return F("D");
    case BTN_LEFT:   return F("L");
    case BTN_SELECT: return F("S");
    default:         return F("---");
  }
}

int currentGain() {
  return gainTable[gainModeIndex];
}

void printPaddedLong(long value, uint8_t width) {
  char buf[12];
  ltoa(value, buf, 10);
  uint8_t len = 0;
  while (buf[len]) len++;
  while (len < width) {
    lcd.print(' ');
    width--;
  }
  lcd.print(buf);
}

void formatRightAlignedInt(char* out, uint8_t width, long value) {
  char buf[12];
  ltoa(value, buf, 10);
  uint8_t len = 0;
  while (buf[len]) len++;
  uint8_t pad = (len < width) ? (width - len) : 0;
  uint8_t i = 0;
  while (i < pad) out[i++] = ' ';
  uint8_t j = 0;
  while (buf[j] && i < width) out[i++] = buf[j++];
  while (i < width) out[i++] = ' ';
  out[width] = 0;
}

void pushBtnAdcDisplaySample(int v) {
  btnAdcHistSum -= btnAdcHist[btnAdcHistPos];
  btnAdcHist[btnAdcHistPos] = v;
  btnAdcHistSum += v;
  btnAdcHistPos = (btnAdcHistPos + 1) % DISPLAY_AVG_N;
  buttonAdcDisplay = (int)(btnAdcHistSum / DISPLAY_AVG_N);
}

void pushPotCCDisplaySample(int v) {
  potCCHistSum -= potCCHist[potCCHistPos];
  potCCHist[potCCHistPos] = v;
  potCCHistSum += v;
  potCCHistPos = (potCCHistPos + 1) % DISPLAY_AVG_N;
  potCCDisplay = (int)(potCCHistSum / DISPLAY_AVG_N);
}


void lcdWrite16(uint8_t row, const char* text) {
  char buf[17];
  uint8_t i = 0;
  while (i < 16 && text[i] != '\0') {
    buf[i] = text[i];
    i++;
  }
  while (i < 16) {
    buf[i++] = ' ';
  }
  buf[16] = '\0';
  lcd.setCursor(0, row);
  lcd.print(buf);
}


void printBtnCompact() {
  if (stableBtn != BTN_NONE) {
    lcd.print(buttonShortF(stableBtn));
    lcd.print(F("   "));
    return;
  }

  if (lastCompletedBtn != BTN_NONE && (millis() - lastCompletedBtnAt) < LAST_BTN_HOLD_MS) {
    switch (lastCompletedBtn) {
      case BTN_RIGHT:  lcd.print(lastCompletedWasLongPress ? F("R-LP  ") : F("(R)   ")); return;
      case BTN_UP:     lcd.print(lastCompletedWasLongPress ? F("U-LP  ") : F("(U)   ")); return;
      case BTN_DOWN:   lcd.print(lastCompletedWasLongPress ? F("D-LP  ") : F("(D)   ")); return;
      case BTN_LEFT:   lcd.print(lastCompletedWasLongPress ? F("L-LP  ") : F("(L)   ")); return;
      case BTN_SELECT: lcd.print(lastCompletedWasLongPress ? F("S-LP  ") : F("(S)   ")); return;
    }
  }

  lcd.print(F("----- "));
}


void triggerShortBlink() {
  ledPressDouble = false;
  ledPressPhase = 1;
  ledPressPhaseUntil = millis() + SHORT_BLINK_MS;
}

void triggerLongBlink() {
  ledPressDouble = true;
  ledPressPhase = 1;
  ledPressPhaseUntil = millis() + SHORT_BLINK_MS;
}

void triggerActivity() {
  ledActivityUntil = millis() + ACTIVITY_HOLD_MS;
}

void updateInputLeds() {
  unsigned long now = millis();
  bool pressOn = false;

  if (ledPressPhase != 0 && (long)(ledPressPhaseUntil - now) <= 0) {
    if (!ledPressDouble) {
      ledPressPhase = 0;
    } else {
      if (ledPressPhase == 1) {
        ledPressPhase = 2;
        ledPressPhaseUntil = now + DOUBLE_BLINK_GAP_MS;
      } else if (ledPressPhase == 2) {
        ledPressPhase = 3;
        ledPressPhaseUntil = now + SHORT_BLINK_MS;
      } else {
        ledPressPhase = 0;
      }
    }
  }

  if (ledPressPhase == 1 || ledPressPhase == 3) {
    pressOn = true;
  }

  bool activityOn = (long)(ledActivityUntil - now) > 0;

  digitalWrite(LED_READY, deviceReady ? HIGH : LOW);
  digitalWrite(LED_PRESS, pressOn ? HIGH : LOW);
  digitalWrite(LED_ACTIVITY, activityOn ? HIGH : LOW);
}
// --------------------------------------------------
// Button decode
// --------------------------------------------------
int decodeButtonThreshold(int val) {
  if (val < ADC_THR_LEFT)   return BTN_LEFT;
  if (val < ADC_THR_UP)     return BTN_UP;
  if (val < ADC_THR_DOWN)   return BTN_DOWN;
  if (val < ADC_THR_RIGHT)  return BTN_RIGHT;
  if (val < ADC_THR_SELECT) return BTN_SELECT;
  return BTN_NONE;
}

void updateButtonStableState() {
  buttonAdcRaw = analogRead(KEY_PIN);
  pushBtnAdcDisplaySample(buttonAdcRaw);
  rawBtnNow = decodeButtonThreshold(buttonAdcRaw);
  stableBtn = rawBtnNow;
}

void handleButtonCountingAndActions() {
  static int prevStableBtn = BTN_NONE;

  if (prevStableBtn == BTN_NONE && stableBtn != BTN_NONE) {
    latchedPressedBtn = stableBtn;
    latchedLongTriggered = false;
    latchedPressedAt = millis();

    Serial.print(F("BTN press: "));
    Serial.print(buttonNameF(stableBtn));
    Serial.print(F(" adc="));
    Serial.println(buttonAdcRaw);
  }

  if (stableBtn != BTN_NONE && latchedPressedBtn == stableBtn && !latchedLongTriggered) {
    if ((millis() - latchedPressedAt) >= LONG_PRESS_MS) {
      latchedLongTriggered = true;
      lastCompletedBtn = latchedPressedBtn;
      lastCompletedWasLongPress = true;
      lastCompletedBtnAt = millis();
      triggerLongBlink();

      if (latchedPressedBtn == BTN_SELECT) {
        gainModeIndex++;
        if (gainModeIndex >= 4) gainModeIndex = 0;
        noInterrupts();
        encPendingSteps = 0;
        encQuarterAcc = 0;
        interrupts();
        logicalPos = 0;
        encStepCount = 0;
        lastStepUs = 0;
        gainDisplayUntil = millis() + LAST_BTN_HOLD_MS;

        Serial.print(F("=== GAIN TOGGLED: x"));
        Serial.print(currentGain());
        Serial.println(F(" ==="));
      }

      Serial.print(F("BTN long: "));
      Serial.println(buttonNameF(latchedPressedBtn));
    }
  }

  if (prevStableBtn != BTN_NONE && stableBtn == BTN_NONE) {
    if (latchedPressedBtn != BTN_NONE) {
      lastCompletedBtn = latchedPressedBtn;
      lastCompletedWasLongPress = latchedLongTriggered;
      lastCompletedBtnAt = millis();

      if (latchedLongTriggered) {
        Serial.print(F("BTN release after LP: "));
        Serial.println(buttonNameF(latchedPressedBtn));
      } else {
        btnPressCount[latchedPressedBtn]++;
        triggerShortBlink();

        Serial.print(F("BTN release/count: "));
        Serial.print(buttonNameF(latchedPressedBtn));
        Serial.print(F(" count="));
        Serial.println(btnPressCount[latchedPressedBtn]);
      }
    }
    latchedPressedBtn = BTN_NONE;
    latchedLongTriggered = false;
  }

  prevStableBtn = stableBtn;
}

// --------------------------------------------------
// ISR-based encoder decode
// --------------------------------------------------
void handleEncoderISR() {
  uint8_t a = (uint8_t)digitalRead(ENC_A);
  uint8_t b = (uint8_t)digitalRead(ENC_B);
  uint8_t newState = (a << 1) | b;

  if (a != ((encLastState >> 1) & 0x01)) edgeCountA++;
  if (b != (encLastState & 0x01)) edgeCountB++;

  uint8_t idx = (encLastState << 2) | newState;
  int8_t q = ENC_TABLE[idx];
  encLastState = newState;

  if (q == 0) return;

  encQuarterAcc += q;

  if (encQuarterAcc >= 4) {
    encPendingSteps += 1;
    encQuarterAcc = 0;
  } else if (encQuarterAcc <= -4) {
    encPendingSteps -= 1;
    encQuarterAcc = 0;
  }
}

// --------------------------------------------------
// Consume encoder steps in main loop with acceleration
// --------------------------------------------------
int accelFromDt(unsigned long dtUs) {
  if (dtUs < 2500UL) return 8;
  if (dtUs < 5000UL) return 6;
  if (dtUs < 9000UL) return 4;
  if (dtUs < 18000UL) return 2;
  return 1;
}

void processEncoderSteps() {
  long pending;

  noInterrupts();
  pending = encPendingSteps;
  encPendingSteps = 0;
  interrupts();

  while (pending != 0) {
    int dir = (pending > 0) ? 1 : -1;
    pending -= dir;

    unsigned long nowUs = micros();
    unsigned long dtUs = (lastStepUs == 0) ? 50000UL : (nowUs - lastStepUs);
    lastStepUs = nowUs;

    int accel = accelFromDt(dtUs);
    int delta = dir * currentGain() * accel;

    encStepCount += dir;
    logicalPos += delta;
    triggerActivity();

    Serial.print(dir > 0 ? F("ENC CW   step=") : F("ENC CCW  step="));
    Serial.print(encStepCount);
    Serial.print(F(" gain=x"));
    Serial.print(currentGain());
    Serial.print(F(" accel=x"));
    Serial.print(accel);
    Serial.print(F(" pos="));
    Serial.print(logicalPos);
    Serial.print(F(" dtUs="));
    Serial.println(dtUs);
  }
}

// --------------------------------------------------
// Encoder switch
// --------------------------------------------------
void checkSwitch() {
  int sw = digitalRead(ENC_SW);

  if (sw != lastSW) {
    delay(5);
    sw = digitalRead(ENC_SW);

    if (sw != lastSW) {
      if (sw == LOW) {
        swLatchedPressed = true;
        swLatchedLongTriggered = false;
        swLatchedPressedAt = millis();
        Serial.println(F("SW pressed"));
      } else {
        if (swLatchedPressed) {
          if (!swLatchedLongTriggered) {
            swPressCount++;
            lcdPage ^= 1;
            triggerShortBlink();
            Serial.print(F("SW pressed  count="));
            Serial.print(swPressCount);
            Serial.print(F(" page="));
            Serial.println(lcdPage);
            Serial.println(F("SW released"));
          } else {
            Serial.println(F("SW released after LP"));
          }
          swLatchedPressed = false;
          swLatchedLongTriggered = false;
        }
      }
      lastSW = sw;
    }
  }

  if (sw == LOW && swLatchedPressed && !swLatchedLongTriggered) {
    if ((millis() - swLatchedPressedAt) >= LONG_PRESS_MS) {
      swLatchedLongTriggered = true;
      swLongPressCount++;
      triggerLongBlink();
      Serial.print(F("SW long count="));
      Serial.println(swLongPressCount);
    }
  }
}

// --------------------------------------------------
// Pot
// --------------------------------------------------
void updatePot() {
  potRaw = analogRead(POT_PIN);
  potAvg = (potAvg * 3 + potRaw) >> 2;
  potCC = map(potAvg, 0, 1023, 0, 127);

  if (potCC < 0) potCC = 0;
  else if (potCC > 127) potCC = 127;

  pushPotCCDisplaySample(potCC);

  if (potCC != lastPotCC) {
    lastPotCC = potCC;
    triggerActivity();
    Serial.print(F("POT raw="));
    Serial.print(potRaw);
    Serial.print(F(" avg="));
    Serial.print(potAvg);
    Serial.print(F(" cc="));
    Serial.println(potCC);
  }
}

// --------------------------------------------------
// LCD
// --------------------------------------------------
void updateLcd() {
  unsigned long now = millis();
  if (now - lastLcdUpdate < LCD_INTERVAL_MS) return;
  lastLcdUpdate = now;

  prankModeActive = (potCC <= 63);
  if (prankModeActive) {
    if ((now - lastPrankToggle) >= POT_PRANK_INTERVAL_MS) {
      prankScreenToggle = !prankScreenToggle;
      lastPrankToggle = now;
    }

    if (!prankScreenToggle) {
      lcdWrite16(0, "Fluid Ardule");
      char line2[32];
      snprintf(line2, sizeof(line2), "FW %s", FW_VERSION);
      lcdWrite16(1, line2);
    } else {
      lcdWrite16(0, "Boot screen demo");
      lcdWrite16(1, "Pot > 50% to rtn");
    }
    return;
  }

  int sw = digitalRead(ENC_SW);

  char line0[17];
  char line1[17];
  memset(line0, ' ', 16);
  memset(line1, ' ', 16);
  line0[16] = '\0';
  line1[16] = '\0';

  // Line 0: "B:<btn>   A0:<adc>"
  line0[0] = 'B';
  line0[1] = ':';
  lcd.setCursor(2, 0); // temporary for printBtnCompact width estimate not used here

  const char* btnBuf = "---";
  if (stableBtn != BTN_NONE) {
    switch (stableBtn) {
      case BTN_RIGHT: btnBuf = "R"; break;
      case BTN_UP: btnBuf = "U"; break;
      case BTN_DOWN: btnBuf = "D"; break;
      case BTN_LEFT: btnBuf = "L"; break;
      case BTN_SELECT: btnBuf = "S"; break;
    }
  } else if (lastCompletedBtn != BTN_NONE && (millis() - lastCompletedBtnAt) < LAST_BTN_HOLD_MS) {
    switch (lastCompletedBtn) {
      case BTN_RIGHT: btnBuf = lastCompletedWasLongPress ? "R-LP" : "(R)"; break;
      case BTN_UP: btnBuf = lastCompletedWasLongPress ? "U-LP" : "(U)"; break;
      case BTN_DOWN: btnBuf = lastCompletedWasLongPress ? "D-LP" : "(D)"; break;
      case BTN_LEFT: btnBuf = lastCompletedWasLongPress ? "L-LP" : "(L)"; break;
      case BTN_SELECT: btnBuf = lastCompletedWasLongPress ? "S-LP" : "(S)"; break;
    }
  }
  snprintf(line0, sizeof(line0), "B:%-4s A0:%4d", btnBuf, buttonAdcDisplay);

  if (gainDisplayUntil > now) {
    snprintf(line1, sizeof(line1), "Gain x%d", currentGain());
  } else if (lcdPage == 0) {
    snprintf(line1, sizeof(line1), "Gx%d P:%5ld S:%d", currentGain(), logicalPos, sw == LOW ? 0 : 1);
  } else {
    snprintf(line1, sizeof(line1), "V:%3d St:%4ld%c", potCCDisplay, encStepCount, sw == LOW ? '*' : ' ');
  }

  lcdWrite16(0, line0);
  lcdWrite16(1, line1);
}

// --------------------------------------------------
// Setup
// --------------------------------------------------
void setup() {
  pinMode(ENC_A, INPUT_PULLUP);
  pinMode(ENC_B, INPUT_PULLUP);
  pinMode(ENC_SW, INPUT_PULLUP);
  pinMode(LED_READY, OUTPUT);
  pinMode(LED_PRESS, OUTPUT);
  pinMode(LED_ACTIVITY, OUTPUT);
  digitalWrite(LED_READY, LOW);
  digitalWrite(LED_PRESS, LOW);
  digitalWrite(LED_ACTIVITY, LOW);

  Serial.begin(115200);

  lcd.init();
  lcd.backlight();
  lcd.clear();

  uint8_t a = (uint8_t)digitalRead(ENC_A);
  uint8_t b = (uint8_t)digitalRead(ENC_B);
  encLastState = (a << 1) | b;
  lastSW = digitalRead(ENC_SW);

  buttonAdcRaw = analogRead(KEY_PIN);
  potAvg = analogRead(POT_PIN);
  potCC = map(potAvg, 0, 1023, 0, 127);
  if (potCC < 0) potCC = 0;
  else if (potCC > 127) potCC = 127;

  for (uint8_t i = 0; i < DISPLAY_AVG_N; i++) {
    btnAdcHist[i] = buttonAdcRaw;
    potCCHist[i] = potCC;
  }
  btnAdcHistSum = (long)buttonAdcRaw * DISPLAY_AVG_N;
  potCCHistSum = potCC * DISPLAY_AVG_N;
  buttonAdcDisplay = buttonAdcRaw;
  potCCDisplay = potCC;

  attachInterrupt(digitalPinToInterrupt(ENC_A), handleEncoderISR, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENC_B), handleEncoderISR, CHANGE);

  lcd.setCursor(0, 0);
  lcd.print(F("UNO-1 Diag 1602"));
  lcd.setCursor(0, 1);
  lcd.print(FW_VERSION);
  delay(900);
  lcd.clear();
  lastPrankToggle = millis();
  prankScreenToggle = false;

  Serial.println(F("================================"));
  Serial.println(F("Fluid Ardule UNO-1 diagnostic"));
  deviceReady = true;
  Serial.println(F("1602 LCD edition"));
  Serial.println(F("Encoder: interrupt + full-step + acceleration"));
  Serial.print(F("Version: "));
  Serial.println(FW_VERSION);
  Serial.println(F("================================"));
}

// --------------------------------------------------
// Loop
// --------------------------------------------------
void loop() {
  updateButtonStableState();
  handleButtonCountingAndActions();
  processEncoderSteps();
  checkSwitch();
  updatePot();
  updateLcd();
  updateInputLeds();
}
