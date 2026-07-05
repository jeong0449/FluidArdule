# Fluid Ardule Disaster Recovery

**First written: 2026-07-05**\
**Last verified: 2026-07-05**

This document describes how to create and restore a personal emergency
recovery image of a working Fluid Ardule system.

The purpose of this procedure is **disaster recovery, not image
distribution**.

The recovery image is a snapshot of a known working Fluid Ardule
installation and may contain development files, local configuration,
SoundFonts, Yoshimi settings, and other system-specific data.

The procedure below was verified by creating a compact image from a
working Fluid Ardule system, writing it to a different microSD card,
booting a Raspberry Pi 3B from that card, and confirming audio output.
The restored root filesystem also expanded automatically to use the
target card capacity.

------------------------------------------------------------------------

## 1. Reference System

Verified environment:

-   Raspberry Pi 3B
-   Raspberry Pi OS Trixie
-   Headless / Lite environment
-   Boot device: `/dev/mmcblk0`
-   Boot partition: `/dev/mmcblk0p1`
-   Root partition: `/dev/mmcblk0p2`
-   Boot mount point: `/boot/firmware`
-   Root mount point: `/`

Reference partition layout before backup:

``` text
NAME         SIZE FSTYPE MOUNTPOINTS
mmcblk0     29.8G
├─mmcblk0p1  512M vfat   /boot/firmware
└─mmcblk0p2 29.3G ext4   /
```

Check the Raspberry Pi OS release with:

``` bash
grep VERSION_CODENAME /etc/os-release
```

Verified output:

``` text
VERSION_CODENAME=trixie
```

------------------------------------------------------------------------

## 2. Why a Full Raw SD Image Is Not Recommended

A full-device copy such as:

``` bash
sudo dd if=/dev/mmcblk0 of=Fluid_Ardule.img bs=4M status=progress
```

creates an image with the exact size of the source device.

In the system tested here, the full raw image size was:

``` text
32010928128 bytes
```

Two cards both sold as "32 GB" can have different actual sector counts.
A raw image made from the slightly larger card may therefore fail to fit
on another nominally identical 32 GB card.

This problem was encountered in practice during Fluid Ardule recovery
testing.

For personal disaster recovery, a compact filesystem-based image is more
portable.

------------------------------------------------------------------------

## 3. Backup Tool: RonR's Raspberry Pi image-utils

This procedure uses RonR's Raspberry Pi `image-utils`, especially:

``` text
image-backup
image-check
image-mount
image-shrink
```

`image-backup` creates a bootable image based on the filesystem contents
instead of copying all unused sectors from the source card.

The `image-utils` documentation states that an image created by
`image-backup` is configured to **auto-expand on its first boot unless
the `-n` / `--noexpand` option is used**.

This point is important: the automatic expansion observed during the
Fluid Ardule recovery test was expected behavior of the image produced
by `image-backup`. It should not be attributed solely to Raspberry Pi
Imager.

For the procedure documented here, `image-backup` was run without
`--noexpand`.

Project source and documentation:

https://github.com/seamusdemora/RonR-RPi-image-utils

------------------------------------------------------------------------

## 4. Prepare a Separate Image Storage Device

The recovery image should be written to a filesystem separate from the
running root filesystem.

Do **not** create the backup image inside `/` or `/home`.

The running root filesystem is itself the backup source. Keeping the
output image on a separate mounted filesystem avoids placing the growing
image file inside the source tree being copied.

Connect a USB flash drive, USB SSD, or an SD card through a USB reader.

Identify all devices:

``` bash
lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINTS,MODEL
```

**Never assume a device name such as `/dev/sda` or `/dev/sdb`.**

Always determine the device and partition names from the actual `lsblk`
output before formatting, mounting, or writing.

------------------------------------------------------------------------

## 5. Recommended Filesystem for the Image Storage Device

If the recovery image will be moved physically between Raspberry Pi OS
and Windows, **exFAT is recommended**.

Reasons:

-   readable and writable by Raspberry Pi OS
-   readable and writable by Windows
-   supports files larger than 4 GB

FAT32 is unsuitable for the verified Fluid Ardule image because the
image is approximately 5.5 GB and FAT32 has a 4 GB single-file size
limit.

An ext4 storage partition works perfectly for `image-backup`, but
Windows does not natively provide normal Explorer access to ext4. This
can make physical transfer to a Windows PC inconvenient.

If the selected partition may be erased, format it as exFAT:

``` bash
sudo mkfs.exfat -n IMAGE_STORE /dev/sdXN
```

Replace `/dev/sdXN` only after confirming the actual partition name with
`lsblk`.

**WARNING: formatting destroys all existing data on the selected
partition.**

Create a mount point and mount the storage partition:

``` bash
sudo mkdir -p /mnt/usb
sudo mount /dev/sdXN /mnt/usb
df -h /mnt/usb
```

Confirm that sufficient free space is available.

------------------------------------------------------------------------

## 6. Create the Recovery Image

Run:

``` bash
sudo image-backup
```

When prompted for the image file, enter:

``` text
/mnt/usb/Fluid_Ardule_260705.img
```

The verified prompt sequence was:

``` text
Image file to create? /mnt/usb/Fluid_Ardule_260705.img

Initial image file ROOT filesystem size (MB) [5405]?

Added space for incremental updates after shrinking (MB) [0]?

Create /mnt/usb/Fluid_Ardule_260705.img (y/n)? y
```

For this personal emergency snapshot, the automatically calculated root
filesystem size of `5405` MB was accepted.

The default value of `0` MB for additional incremental-update space was
also accepted.

Do not arbitrarily choose a root filesystem size before seeing the value
calculated by `image-backup`.

The backup process may run `e2fsck` and `resize2fs` several times.

Messages such as:

``` text
Inode ... extent tree (at level 1) could be shorter. Optimize? no
```

are not necessarily fatal errors.

Wait until `image-backup` finishes and the shell prompt returns.

------------------------------------------------------------------------

## 7. Check the Image Size

Run:

``` bash
ls -lh /mnt/usb/Fluid_Ardule_260705.img
```

Verified result:

``` text
-rw-r--r-- 1 root root 5.5G Jul 5 09:37 /mnt/usb/Fluid_Ardule_260705.img
```

The source microSD card was approximately 32 GB, but the resulting
recovery image was approximately 5.5 GB.

This is expected. Unused space from the source card is not copied into
the compact image.

------------------------------------------------------------------------

## 8. Validate the Recovery Image

Run:

``` bash
sudo image-check /mnt/usb/Fluid_Ardule_260705.img
```

Confirm the check when prompted.

During the verified run, `image-check` reported:

``` text
Inode 6604 extent tree (at level 1) could be shorter. Optimize<y>? yes
```

After optimization it also reported:

``` text
rootfs: ***** FILE SYSTEM WAS MODIFIED *****
```

This did **not** indicate image corruption. `image-check` had modified
the filesystem while optimizing the extent tree.

The important final state was:

``` text
Filesystem state:         clean
```

------------------------------------------------------------------------

## 9. Create a SHA-256 Checksum

After `image-check`, create the checksum from the final checked image:

``` bash
sha256sum /mnt/usb/Fluid_Ardule_260705.img \
  | tee /mnt/usb/Fluid_Ardule_260705.img.sha256
```

Flush pending writes:

``` bash
sync
```

Unmount the storage device before removing it:

``` bash
sudo umount /mnt/usb
```

------------------------------------------------------------------------

## 10. Verify the Image on Windows

After copying the image to a Windows PC, open PowerShell in the image
directory.

Run:

``` powershell
Get-FileHash .\Fluid_Ardule_260705.img -Algorithm SHA256
```

To display only the hash:

``` powershell
(Get-FileHash .\Fluid_Ardule_260705.img -Algorithm SHA256).Hash
```

Compare the PowerShell result with the hash stored in:

``` text
Fluid_Ardule_260705.img.sha256
```

The values must match.

------------------------------------------------------------------------

## 11. Restore the Image to a microSD Card

Use Raspberry Pi Imager or another raw-image writing tool.

With Raspberry Pi Imager:

1.  Choose the custom image option.
2.  Select `Fluid_Ardule_260705.img`.
3.  Select the target microSD card.
4.  Write the image.
5.  Allow the write verification to complete.

Carefully verify the target device before writing.

The target card does not need to have the same exact physical sector
count as the original 32 GB card. It only needs to be large enough for
the compact image and its partitions.

Card quality still matters. During this recovery test, one low-cost card
showed much slower writing and verification and did not boot
successfully. The same image was then written to a new SanDisk card,
which wrote and verified much faster and booted successfully.

A failed boot from one questionable card is therefore not sufficient
evidence that the recovery image itself is defective.

------------------------------------------------------------------------

## 12. First Boot After Recovery

Insert the restored microSD card into the Raspberry Pi 3B and boot Fluid
Ardule.

Before changing the partition layout manually, check the current root
filesystem size:

``` bash
lsblk
df -h /
```

In the verified recovery test, the compact 5.5 GB image was written to a
nominal 32 GB SanDisk microSD card.

After the first successful boot:

``` text
Filesystem      Size  Used Avail Use% Mounted on
/dev/mmcblk0p2   29G  4.1G   24G  15% /
```

No manual filesystem expansion was required.

The root filesystem had already expanded to use the target card
capacity.

This behavior is consistent with `image-backup` documentation: images
created without `-n` / `--noexpand` auto-expand when first executed.

------------------------------------------------------------------------

## 13. Root Filesystem Expansion: Check First, Expand Only If Needed

**Do not run filesystem expansion automatically as a routine recovery
step.**

First check:

``` bash
lsblk
df -h /
```

If `/` already uses approximately the expected capacity of the target
microSD card, no further action is required.

For example:

``` text
/dev/mmcblk0p2   29G  4.1G   24G  15% /
```

on a nominal 32 GB card means expansion has already occurred.

Only if the restored root filesystem remains close to the compact image
size should manual expansion be considered.

For Raspberry Pi OS, run:

``` bash
sudo raspi-config
```

Use the filesystem expansion function available in the installed
version, then reboot if instructed:

``` bash
sudo reboot
```

After reboot, verify again:

``` bash
lsblk
df -h /
```

Raspberry Pi documentation notes that Raspberry Pi OS normally expands
the filesystem automatically on first boot. In this specific recovery
workflow, `image-backup` also explicitly prepares the resulting image
for first-run auto-expansion unless `--noexpand` is selected.

Therefore the correct recovery rule is:

> **Boot first, inspect `df -h /`, and expand manually only if the
> filesystem is still small.**

------------------------------------------------------------------------

## 14. Verified Fluid Ardule Recovery Result

The recovery procedure documented here was tested on 2026-07-05.

Verified sequence:

``` text
Working Fluid Ardule SD
        |
        | image-backup
        v
Fluid_Ardule_260705.img
        |
        | image-check
        v
Filesystem state: clean
        |
        | SHA-256 verification
        v
Windows PC
        |
        | Raspberry Pi Imager
        v
New SanDisk microSD card
        |
        | first boot
        v
Raspberry Pi 3B boot successful
Fluid Ardule running
Audio output confirmed
Root filesystem automatically expanded to 29G
```

The resulting image is therefore a **boot-tested Fluid Ardule emergency
recovery image**, not merely an unchecked backup file.

------------------------------------------------------------------------

## 15. Fluid Ardule A/B SD Card Strategy

Two microSD cards are recommended.

### Card A --- Stable System

The known working Fluid Ardule installation.

Use this card for normal operation and playing.

Avoid experimental OS upgrades or major system changes.

### Card B --- Test System

Use this card for:

-   Raspberry Pi OS updates
-   kernel changes
-   FluidSynth updates
-   Yoshimi updates
-   ALSA and MIDI tests
-   TFT configuration tests
-   systemd service changes

If Card B fails, return to Card A.

The offline recovery image provides an additional layer of protection:

``` text
Card A
Known working Fluid Ardule system

Card B
Development and OS test system

Fluid_Ardule_YYMMDD.img
Offline disaster recovery snapshot
```

------------------------------------------------------------------------

## 16. Recovery Policy

Create a new recovery image after major stable milestones, for example:

-   major Fluid Ardule feature completion
-   audio engine configuration changes
-   boot or systemd changes
-   Raspberry Pi OS upgrades
-   major Yoshimi or FluidSynth integration changes
-   hardware configuration changes affecting the operating system

Development directories such as:

``` text
~/dev
```

do not need to be cleaned before creating a personal disaster recovery
image.

For a private recovery snapshot, preserving development history and
local configuration may be useful.

Remember that such an image can contain private or machine-specific
data. **Do not publish the `.img` file merely because this recovery
procedure is public.**

This Markdown document may be published in the Fluid Ardule GitHub
repository. The recovery image itself should remain private unless it
has been deliberately sanitized for distribution.

------------------------------------------------------------------------

## 17. Important Lessons

1.  Nominally identical 32 GB microSD cards may have different physical
    capacities.
2.  A full raw-device image may not fit on another nominally identical
    32 GB card.
3.  A compact filesystem-based recovery image is more portable.
4.  The backup image should be created on a filesystem separate from the
    running root filesystem.
5.  FAT32 cannot store an image larger than 4 GB.
6.  exFAT is convenient for moving large image files between Raspberry
    Pi OS and Windows.
7.  ext4 works as backup storage but is inconvenient for direct physical
    transfer to a normal Windows installation.
8.  Always identify storage devices with `lsblk` before formatting or
    writing.
9.  Accept the root size calculated by `image-backup` unless there is a
    specific reason to override it.
10. Validate the image with `image-check`.
11. Create the SHA-256 checksum after the final image check.
12. `image-backup` images auto-expand on first execution unless
    `--noexpand` is used.
13. Check `df -h /` before attempting manual expansion.
14. microSD card quality can affect writing speed, verification speed,
    and boot reliability.
15. A recovery image is not proven until it has been written to another
    microSD card and successfully booted.

------------------------------------------------------------------------

## Final Verification Checklist

``` text
[x] image-backup completed
[x] image-check completed
[x] Filesystem state: clean
[x] SHA-256 checksum recorded
[x] Image copied to offline storage
[x] Image written to another microSD card
[x] Raspberry Pi 3B booted successfully
[x] Fluid Ardule UI started
[ ] MIDI input explicitly retested
[x] FluidSynth produced audio
[ ] Yoshimi explicitly retested
[x] TFT display worked
[ ] UNO controller communication explicitly retested
[x] Root filesystem auto-expanded
[x] Final root filesystem size verified: 29G
```

The `Fluid_Ardule_260705.img` image has passed the essential boot and
audio recovery test.

Additional peripheral checks may be completed later, but the image has
already been demonstrated to restore a bootable and audio-producing
Fluid Ardule system.
