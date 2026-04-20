# Fluid Ardule

A DIY Raspberry Pi and Arduino based MIDI sound module system.

Fluid Ardule combines software synthesis, hardware control, and MIDI routing
into a compact custom-built instrument platform.

## Overview

- Raspberry Pi: synthesis engine (FluidSynth, Yoshimi, playback, control, PCM5102A-based I<sup>2</sup>S DAC, CP2102-based USB-to-UART bridge, TFT-LCD)
- UNO-1: UI controller (buttons, encoder, potentiometer, LEDs)
- UNO-2: MIDI router / bridge subsystem (USB and DIN MIDI ingress; not required if using a USB MIDI keyboard controller)

UNO-2 (Uno MIDI Bridge) is maintained as a separate project due to its strong independence.

## Related Projects

- [Nano Ardule](https://github.com/jeong0449/NanoArdule)
- [uno-midi-bridge](https://github.com/jeong0449/uno-midi-bridge) (now essentially identical to UNO-2)

## Status

Work in progress. This repository documents the overall system architecture
and integrates components developed across related projects.
