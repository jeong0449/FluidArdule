#!/bin/bash
sleep 1
/usr/bin/pkill fbi >/dev/null 2>&1 || true
/usr/bin/fbi -T 1 -d /dev/fb1 --noverbose -a /home/pi/sf2/FluidArdule_rot.png >/dev/null 2>&1

