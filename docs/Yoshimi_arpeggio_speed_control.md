# Controlling the Apparent Arpeggio Speed of Yoshimi Presets

## Background

Fluid Ardule uses Yoshimi instrument presets (`.xiz`) as one of its
internal sound engines.

While testing presets in the **Arpeggios** category, it became desirable
to change the apparent arpeggio speed during live performance using the
Fluid Ardule rotary encoder.

The first assumption was that these presets were synchronized to
Yoshimi's global BPM setting. However, changing the global BPM did not
affect the audible repetition speed.

This document records the investigation and the control method finally
adopted in Fluid Ardule.

## Initial BPM Tests

Yoshimi provides a global BPM command:

``` text
set bpm <value>
```

The relevant preset was loaded with:

``` text
load instrument /home/pi/sf2/yoshimi_links/Arpeggios__0001-Arpeggio1.xiz
```

Changing the global BPM, for example:

``` text
set bpm 60
set bpm 180
```

did not change the apparent arpeggio speed.

This indicated that the preset was not behaving as a conventional MIDI
arpeggiator driven directly by the global tempo.

## Investigation of the Preset Structure

Several possible timing sources were examined through the Yoshimi
command-line interface.

These included:

-   Frequency LFO rate
-   LFO BPM synchronization
-   ADDsynth voice parameters
-   Voice delay

Changing these parameters did not alter the characteristic repeated-note
speed that was being investigated.

Inspection of the preset structure and further CLI experiments
eventually identified a part effect associated with the sound.

The relevant context can be entered with:

``` text
/
set part 1
set effect 2 echo
```

A successful context change produces a prompt similar to:

``` text
@ p1+ eff 2 ECho-3?
```

The critical parameter was the Echo `Delay`.

For example:

``` text
set delay 10
```

and:

``` text
set delay 100
```

produced clearly different repetition speeds.

This confirmed that the apparent arpeggio timing of the tested preset is
largely controlled by the delay time of:

``` text
Part 1
  Effect 2
    Echo
      Delay
```

In other words, the preset named `Arpeggio1` does not expose its
apparent speed as a simple global BPM-controlled MIDI arpeggiator
parameter.

For the purpose of live control in Fluid Ardule, the useful timing
parameter is the Echo Delay.

## Why the UI Does Not Claim True BPM Control

The Yoshimi Echo effect also provides a BPM-related option. However,
experiments showed that it did not behave as a direct numeric BPM
control for this purpose.

Therefore Fluid Ardule does **not** send the displayed value directly to
Yoshimi as BPM.

Instead, the UI presents a BPM-like **Arpeggio Speed** value and
converts it to an Echo Delay value.

The displayed number is intended to approximate the perceived repetition
tempo rather than claim exact MIDI clock synchronization.

## Empirical Calibration

An initial mapping was used:

``` text
echo_delay = round(6000 / raw_speed)
```

The apparent tempo was then measured by listening and comparing the
repeated pattern with a tempo reference.

The following approximate observations were obtained:

    Raw speed input   Apparent tempo
  ----------------- ----------------
                 60               52
                 75               66
                100               83
                120              100
                140              126
                160              133
                180              140
                200              162
                220              181
                240              200

A simple linear approximation gave:

``` text
apparent_bpm ≈ 0.797 × raw_speed + 5.13
```

The inverse relation is therefore:

``` text
raw_speed ≈ (display_bpm - 5.13) / 0.797
```

Fluid Ardule uses the following two-stage conversion:

``` text
raw_speed = round((display_bpm - 5.13) / 0.797)

echo_delay = round(6000 / raw_speed)
```

The final Echo Delay value is constrained to the valid Yoshimi range.

This is an empirical calibration for the tested Yoshimi arpeggio preset
behavior. It should not be interpreted as a general Yoshimi BPM
conversion formula.

## Yoshimi CLI Control Sequence

The runtime control sequence used by Fluid Ardule is conceptually:

``` text
/
set part 1
set effect 2 echo
set delay <calculated_delay>
```

The commands are sent to the already running Yoshimi process through its
open standard input.

Yoshimi is **not restarted**, and the instrument is **not reloaded**,
when the encoder changes Arpeggio Speed.

This allows speed adjustment during live performance.

## Test Utility

The standalone calibration and runtime test utility is available at:

[`scripts/test_yoshimi_art_speed_calibrated.py`](../scripts/test_yoshimi_art_speed_calibrated.py)

On the Fluid Ardule system, the corresponding script is located at:

``` text
~/scripts/test_yoshimi_art_speed_calibrated.py
```

This is the calibrated revision of the test utility. An initial test
mapping was used to collect apparent-tempo measurements, and the script
was then revised once using the resulting empirical linear calibration.
The script therefore documents the same measured conversion adopted by
the Fluid Ardule runtime implementation.

The script starts Yoshimi in headless mode, loads the target `.xiz`
instrument, keeps Yoshimi standard input open, and sends runtime CLI
commands for Echo Delay control.

Typical test values are:

``` text
60
90
120
150
180
210
240
```

The utility reports the conversion chain in the following form:

``` text
Arp BPM 120 -> calibrated speed 144 -> Echo Delay 42
```

It can also reload the current instrument to verify runtime preset
loading.

## Fluid Ardule UI Integration

The feature is exposed as:

``` text
Arpeggio Speed
```

It is available from the Extension submenu and from the Quick Menu.

When the Arpeggio Speed screen is active, the encoder adjusts the
displayed speed value. The screen also shows a non-selectable operation
hint:

``` text
Rotate Encoder to adjust
```

The hint is rendered separately from menu rows so that it is not
mistaken for an item accessible with the Up/Down buttons.

The adjustment step is one display unit. Faster encoder movement can
still move through the range quickly through the existing encoder delta
handling.

The current value is also shown in the Yoshimi Arpeggios preset list.

## Scope and Limitations

This implementation is intentionally conservative.

It assumes that the currently selected Yoshimi preset belongs to the
Arpeggios category and uses the tested Echo-based timing structure.

It does not attempt to provide a universal tempo controller for every
Yoshimi instrument.

The displayed Arpeggio Speed is:

-   empirically calibrated,
-   close to the perceived repetition tempo,
-   useful for live performance,
-   but not MIDI-clock-synchronized BPM.

Future presets may require a different timing parameter or a
preset-specific control profile.

## Conclusion

The original goal was to control the speed of a Yoshimi arpeggio preset.

The investigation showed that changing global BPM, LFO rate, or voice
delay did not control the audible repetition speed. The decisive
parameter was the Echo Delay in Part 1 Effect 2.

Fluid Ardule therefore implements live **Arpeggio Speed** control by
converting a BPM-like display value into an empirically calibrated
Yoshimi Echo Delay value.

The important practical result is simple:

``` text
Encoder rotation
    -> Arpeggio Speed
    -> calibrated speed conversion
    -> Yoshimi Echo Delay
    -> immediate change during performance
```

What initially looked like an arpeggiator tempo problem turned out to be
an echo timing problem.
