# Fluid Ardule Responsiveness Tuning Guide

**Revision:** 2026-06-17

## Purpose

This document summarizes all tuning parameters that affect the
responsiveness of Fluid Ardule. The goal is to achieve the best possible
user experience while maintaining reliable MIDI playback and audio
stability on Raspberry Pi 3B.

------------------------------------------------------------------------

# Design Philosophy

Responsiveness is determined by two independent layers.

1.  **UNO-1 firmware**
    -   Detect user input as accurately as possible.
    -   Never lose encoder detents.
    -   Minimize button latency while avoiding false triggers.
2.  **Python UI**
    -   Consume every encoder event.
    -   Reflect movement naturally on the display.
    -   Avoid excessive TFT refresh that could disturb real-time audio.

------------------------------------------------------------------------

# UNO-1 Firmware

## Interrupt-driven rotary encoder

Previous firmware relied on polling.

Current firmware uses hardware interrupts (ISR).

Benefits:

-   No detectable encoder step loss.
-   Reliable fast rotation.
-   Accurate ENC:+/-N reporting.

------------------------------------------------------------------------

## Encoder transition scaling

Parameter

``` cpp
ENC_TRANSITIONS_PER_STEP
```

Purpose

Converts quadrature transitions into logical encoder steps.

Higher value

-   Lower sensitivity
-   Smaller ENC magnitude

Lower value

-   Higher sensitivity
-   Larger ENC magnitude

------------------------------------------------------------------------

## Button debounce

Parameter

``` cpp
DEBOUNCE_MS
```

Current value

``` cpp
25
```

Effect

Smaller values improve responsiveness but increase the possibility of
switch bounce being interpreted as multiple presses.

Recommended operating range

-   20--30 ms

------------------------------------------------------------------------

# Python Runtime

## Menu navigation

Previous implementation

    ENC:+3
        ↓
    DOWN button

Every encoder event behaved like a single button press.

Current implementation

    ENC:+3
        ↓
    Move menu by three items

This preserves the physical movement of the encoder.

------------------------------------------------------------------------

## Navigation debounce

Previous implementation rejected encoder events arriving within a short
interval.

This filter has been removed.

Reason

The encoder is now hardware-debounced by the UNO ISR firmware, making
the additional Python timing filter unnecessary.

------------------------------------------------------------------------

## TFT rendering interval

Parameter

``` python
RENDER_MIN_INTERVAL
```

Current value

``` python
0.10
```

Purpose

Limits framebuffer refresh frequency.

Lower values

Advantages

-   Faster visual response

Disadvantages

-   Higher CPU usage
-   More framebuffer traffic
-   Increased possibility of MIDI/audio jitter

The current value represents a balanced compromise for Raspberry Pi 3B.

------------------------------------------------------------------------

# Observed Results

Encoder

-   No observable missed detents.
-   Rapid five-step rotation produces five-step menu movement.

Buttons

-   Noticeably quicker response.

Display

-   May visually update in two stages during very rapid movement.
-   Internal navigation remains correct.

------------------------------------------------------------------------

# Future Improvements

Possible future work includes

-   Row-level redraw instead of larger menu redraws.
-   Adaptive render interval.
-   Raspberry Pi 4/5 specific performance profile.
-   Independent tuning profile for higher-performance hardware.

------------------------------------------------------------------------

# Summary

The responsiveness improvement is the result of coordinated tuning
across both software layers.

UNO-1 now guarantees reliable input acquisition.

Python now preserves encoder movement instead of treating it as repeated
button events.

The remaining limitation is no longer input handling but deliberate
display refresh throttling for audio stability, representing a
well-balanced design for Fluid Ardule on Raspberry Pi 3B.
