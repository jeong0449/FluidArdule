# Fluid Ardule

A DIY Raspberry Pi and Arduino-based MIDI sound module system that supports instant keyboard playback, General MIDI synthesis (FluidSynth), real-time synthesis (Yoshimi), and audio file playback in a single integrated platform.

Fluid Ardule combines software synthesis, hardware control, and MIDI routing into a compact, custom-built instrument platform.

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

## Overview

- Raspberry Pi: synthesis engine (FluidSynth, Yoshimi, playback, control, PCM5102A-based I<sup>2</sup>S DAC, CP2102-based USB-to-UART bridge, TFT-LCD)
- UNO-1: UI controller (buttons, encoder, potentiometer, LEDs)
- UNO-2: MIDI router / bridge subsystem (USB and DIN MIDI ingress; not required if using a USB MIDI keyboard controller)

UNO-2 (Uno MIDI Bridge) is maintained as a separate project due to its strong independence.

## What does it do?

- Act as a standalone General MIDI (GM) sound module — connect a keyboard and play instantly
- Accept MIDI input from USB or DIN (DIN I/O via UNO-2 MIDI bridge)
- Play MIDI files and perform real-time synthesis using FluidSynth or Yoshimi
- Play audio files (MP3, OGG, WAV, WMA, and other common formats)
- Control parameters via hardware UI (UNO-1)
- Output audio via I2S DAC or USB DAC

## Related Projects

- [Nano Ardule](https://github.com/jeong0449/NanoArdule)
- [uno-midi-bridge](https://github.com/jeong0449/uno-midi-bridge) (now essentially identical to UNO-2)

## Status

Work in progress. This repository documents the overall system architecture
and integrates components developed across related projects.

## Status

🎬 **Latest Demo (YouTube Shorts)**  
https://www.youtube.com/shorts/FQxRp7cAwEk
