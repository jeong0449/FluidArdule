# Yoshimi Startup Hang Caused by Zero-Byte Configuration File

**Date:** 2026-06-20\
**Project:** Fluid Ardule\
**Component:** Yoshimi Synthesizer\
**Status:** Identified (workaround established)

------------------------------------------------------------------------

# Summary

A rare startup failure was observed when launching Yoshimi from both the
command line and Fluid Ardule.

Instead of completing initialization, Yoshimi became stuck immediately
after:

``` text
Start-up Synth-Instance(0)...
```

CPU usage remained near 100%, no sound was produced, and the synthesizer
never became operational.

Investigation showed that the problem was caused by a corrupted,
zero-byte configuration file.

------------------------------------------------------------------------

# Symptoms

-   Yoshimi hangs during startup.
-   CPU usage remains close to 100%.
-   No audio output.
-   Fluid Ardule cannot load Yoshimi instruments.
-   ALSA MIDI connection appears normal.
-   Restarting the Fluid Ardule service does not resolve the issue.

Typical startup output:

``` text
Missing application start-up configuration.
yoshimi 2.3.3.3 is starting...

Start-up Synth-Instance(0)...
```

------------------------------------------------------------------------

# Investigation

Manual launch:

``` bash
yoshimi -i -A -a
```

still hung.

Running with a clean HOME:

``` bash
HOME=/tmp/yoshimi-clean yoshimi -i -A -a
```

started immediately.

This isolated the problem to the user configuration.

------------------------------------------------------------------------

# Root Cause

The configuration directory contained:

``` text
~/.config/yoshimi/

yoshimi-0.instance
yoshimi.banks
yoshimi.config
```

The file `yoshimi.config` had a size of **0 bytes**, preventing Yoshimi
from completing startup.

------------------------------------------------------------------------

# Recovery

Delete the corrupted file:

``` bash
rm ~/.config/yoshimi/yoshimi.config
```

Yoshimi recreates it automatically during the next successful startup.

------------------------------------------------------------------------

# Verification

  Test                   Result
  ---------------------- ------------
  Manual startup         Successful
  Fluid Ardule startup   Successful
  Instrument loading     Normal
  Audio output           Normal

------------------------------------------------------------------------

# Additional Finding

During the investigation it was discovered that occasional Yoshimi audio
glitches were not caused by Yoshimi itself, but by excessive TFT
rendering performed by the Python UI.

Reducing background display updates dramatically lowered CPU usage and
eliminated the glitches.

------------------------------------------------------------------------

# Lessons Learned

The failure originated from a corrupted configuration rather than the
Yoshimi executable itself.

Reinstalling Fluid Ardule or Yoshimi is unnecessary. Removing the
zero-byte configuration file fully restores operation.

------------------------------------------------------------------------

# Future Monitoring

Continue monitoring configuration integrity after abnormal shutdowns to
determine what conditions may produce an incomplete configuration write.
