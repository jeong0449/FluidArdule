# Fluid Ardule

A DIY Raspberry Pi and Arduino based MIDI sound module system.

FluidArdule combines software synthesis, hardware control, and MIDI routing
into a compact custom-built instrument platform.

## Overview

- Raspberry Pi: synthesis engine (FluidSynth, playback, control)
- UNO-1: UI controller (buttons, encoder, display)
- UNO-2: MIDI router / bridge subsystem (USB and DIN MIDI ingress)

UNO-2 is maintained as a separate project due to its strong independence.

## Related Projects

- [NanoArdule](https://github.com/jeong0449/NanoArdule)
- [uno-midi-bridge](https://github.com/jeong0449/uno-midi-bridge)

## Status

Work in progress. This repository documents the overall system architecture
and integrates components developed across related projects.
