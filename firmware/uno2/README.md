# UNO-2 Firmware

Fluid Ardule uses **UNO-2** as its MIDI input / routing engine.

The UNO-2 firmware is maintained in the NanoArdule repository and should be installed from the following location:

👉 https://github.com/jeong0449/NanoArdule/tree/main/firmware/ardule_usb_midi_host

## What this firmware does

UNO-2 receives MIDI input from:

- USB MIDI devices via USB Host Shield
- DIN MIDI IN via UART RX

and forwards MIDI data to:

- DIN MIDI OUT
- USB-serial output for Raspberry Pi

In the Fluid Ardule system, this allows UNO-2 to act as the dedicated MIDI router, while the Raspberry Pi handles synthesis through FluidSynth.

## Installation

1. Open the firmware directory:

   https://github.com/jeong0449/NanoArdule/tree/main/firmware/ardule_usb_midi_host

2. Download or clone the NanoArdule repository.

3. Open the Arduino sketch:

   ardule-usb-midi-host.ino

4. Upload it to the Arduino Uno used as **UNO-2**.

## Note

This repository does not duplicate the UNO-2 firmware source code.  
Please use the firmware from the NanoArdule repository above to avoid version mismatch.
