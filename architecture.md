# Fluid Ardule Architecture

**Created:** 2026-04-17

## System Architecture

```mermaid
flowchart LR

    KBD1[USB MIDI Keyboard] -->|USB| UNO2[UNO-2<br/>MIDI Router / Bridge]
    KBD2[DIN MIDI Keyboard] --> UNO2

    KBD1 -->|USB direct, <br>treated as raw MIDI| PI[Raspberry Pi]

    UNO2 -->|DIN MIDI| EXT[External MIDI Module]
    UNO2 -->|USB-serial| BRIDGE[uno-midi-bridge<br/>Python / C]

    BRIDGE -->|ALSA MIDI| PI

    PI --> FS[FluidSynth / Player Engine]
    PI --> TFT[TFT-LCD]

    CTRL[Buttons / Encoder / Potentiometer] --> UNO1[UNO-1<br/>UI Controller]
    UNO1 -->|Serial / Events| PI

    FS --> DAC[I2S DAC / USB Audio]
    DAC --> OUT[Audio Output]
````
This diagram illustrates the data flow within the FluidArdule system.

MIDI performance data enters either through UNO-2 (USB/DIN routing) or directly via USB to the Raspberry Pi, while user control inputs (buttons, encoder, potentiometer) are handled by UNO-1 and forwarded to the Pi.

The Raspberry Pi acts as the central processing unit, running FluidSynth and managing playback, while also driving the display output.

Audio is finally rendered through a default I2S DAC or an external USB DAC, completing the signal chain from input to sound output.
