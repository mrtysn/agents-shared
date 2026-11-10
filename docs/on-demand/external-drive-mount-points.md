# An attached drive may not be under /Volumes

**An external drive missing from `/Volumes` is not unmounted.** NTFS drives are mounted
read/write by Mounty (a menu bar app over macFUSE) at `~/.mounty/<VolumeName>`, and the
mount never appears under `/Volumes`. `diskutil list` shows no mount point at all, so it
cannot say either way.

To find a drive, ask for its device and the mount table, not the folder:

    diskutil list external                 # the device, e.g. disk4s1
    mount | grep -i disk4                  # where it is mounted, and with which driver
    diskutil info disk4s1 | grep -i 'Mount Point'

Only when `mount` has no line for the device is it unmounted. Then say so, and mounting
it (`diskutil mount readOnly <device>`) is a state change to confirm with the user, not a
check.

## Provenance

Nov 10 2026, notebook: asked to read the attached Elements drive, a session listed
`/Volumes` and `mount | grep /Volumes`, found nothing and answered "not mounted". Mounty had
it mounted read/write at `~/.mounty/Elements` all along; the user had to paste a screenshot of
the Mounty menu to correct it.
