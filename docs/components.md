## 🧩 Main Components

- **Raspberry Pi 3 Model B** — main controller
- **Arduino Uno R3** — UI controller (UNO-1)
- **3.5" SPI TFT LCD (ILI9486)** — display
- **I2S DAC (PCM5102A)** — audio output
- **Analog Keypad Module** — 5-button resistor ladder (single ADC)
- **Rotary Encoder Module** — with push switch
- **Potentiometer (10kΩ)** — volume control
- **LEDs + resistors** — status indicators

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
