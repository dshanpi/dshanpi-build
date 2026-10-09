# A1 AX8850 16GB

Explicit 16GB option, paired AXCL 3.16.0 runtime and PAC from the immutable
vendor input in upstream.lock.json. The generic 8GB packages remain unchanged.
All four new packages conflict with the old generic cohort; APT must remove that
optional cohort when selecting 16GB. The core system and Wi-Fi packages remain.

Build via scripts/build-axcl-16g-packages.py, publish only using the committed
maintenance plan and axcl-16g.yml. New packages enter noble-testing; publication
alone does not establish hardware acceptance. No service is automatically started
by package installation. After confirming card capacity and cooling:

```sh
sudo apt update
sudo apt install dshanpi-a1-release-core=2026.10.09-4 dshanpi-a1-axcl-16g=3.16.0+dshanpi2
sudo dshanpi-axcl check
sudo dshanpi-axcl test
```

The helper checks board/kernel, BTF configuration and the module structure size
against the original pwm_fan module before loading any AXCL modules. Existing
headers 25.11.0-trunk.20261008.4 lack a pahole dependency. If they were installed
without pahole, first install pahole, reinstall that exact headers package, and
rebuild affected DKMS modules before reboot. Installing pahole alone does not
repair an already corrupted headers configuration. The source fix is ArmBianOS
PR #4; this release reuses the historical headers bytes and does not claim to
publish corrected headers. A newly versioned kernel/headers cohort is still due.

The six-stream reference is pinned separately to demo commit
2aa772bbf16b8a904ee6ca57877c0e602208bf49. Real inference, RTSP/HTTP decoding,
recording and restart must be recorded before calling the complete path verified.
A1 CM5, R1 and Avaota A1 are excluded from this optional package set.
