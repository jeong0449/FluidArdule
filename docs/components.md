## 🧩 Main Components

- **Raspberry Pi 3 Model B** — main controller
- **Arduino Uno R3** — UI controller (UNO-1)
- **3.5" SPI TFT LCD (ILI9486)** — display
- **I2S DAC (PCM5102A)** — audio output
- **Custom Analog Keypad** — 5-button resistor-encoded input (single ADC)
- **Rotary Encoder Module** — with push switch
- **Potentiometer (10kΩ)** — volume control
- **LEDs + resistors** — status indicators

### Custom Analog Keypad

The current keypad uses five individual pushbuttons and a resistor-encoding network connected to a single Arduino ADC input.

```text
5V
 │
10kΩ (pull-up)
 │
A0
 ├─ Button 1 ─ 680Ω ─ GND
 ├─ Button 2 ─ 2.2kΩ ─ GND
 ├─ Button 3 ─ 5.1kΩ ─ GND
 ├─ Button 4 ─ 20kΩ ─ GND
 └─ Button 5 ─ 47kΩ ─ GND
````

Each button produces a unique ADC value that can be distinguished by the firmware.

> [!NOTE]
> Early versions of Fluid Ardule used a commercially available 5-button analog keypad module. While functional, the module occasionally required recalibration and offered limited flexibility for panel integration.
>
> The current design uses five individual pushbuttons and a custom resistor-encoding network connected to a single Arduino ADC input. This approach simplifies mechanical integration and allows the keypad layout to be customized for the enclosure.
>
> A key improvement is the firmware's self-calibration feature. During calibration, the actual ADC values are measured and stored in EEPROM, allowing the system to compensate for resistor tolerances, ADC variation, wiring differences, and long-term drift.
>
>In practice, the self-calibration mechanism proved more important than the exact resistor values themselves and significantly improved long-term reliability.

### PCM5102A DAC Note

> [!NOTE]  
> The I2S DAC board (based on the PCM5102A DAC module) shown in the photo may require hardware configuration before use.  
> On some variants, several solder pads (both sides) must be bridged with solder blobs to enable proper I2S operation (e.g., setting the board to slave mode or enabling output).  
>  
> Please refer to the following resources for details and pad configuration:  
> 👉 https://raspberrypi.stackexchange.com/questions/76188/how-to-make-pcm5102-dac-work-on-raspberry-pi-zerow  
> 👉 https://youtu.be/1T9PKLeBDFc?si=3qDlUETTKLare8zq  

---

## 🔧 Optional Components

- I2C 16x2 Character LCD Module (1602 LCD with I2C backpack)
- USB to TTL Serial Converter Module (CP2102-based)
