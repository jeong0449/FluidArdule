# FluidArdule Architecture

**Created:** 2026-04-17

## System Architecture

```mermaid
flowchart LR

    KBD1[USB MIDI Keyboard] -->|USB| UNO2[UNO-2<br/>MIDI Router / Bridge]
    KBD2[DIN MIDI Keyboard] --> UNO2

    KBD1 -->|USB direct, treated as raw MIDI| PI[Raspberry Pi]

    UNO2 -->|DIN MIDI| EXT[External MIDI Module]
    UNO2 -->|USB-serial| BRIDGE[uno-midi-bridge<br/>Python / C]

    BRIDGE -->|ALSA MIDI| PI

    PI --> FS[FluidSynth / Player Engine]
    PI --> TFT[TFT / LCD Display]

    UNO1[UNO-1<br/>UI Controller] -->|Serial / Events| PI
    UNO1 --> CTRL[Buttons / Encoder / Potentiometer]

    FS --> DAC[I2S DAC / USB Audio]
    DAC --> OUT[Audio Output]
```
