# A1 AX8850 16GB

Explicit 16GB option, paired AXCL 3.16.0 runtime and PAC from the immutable
vendor input in upstream.lock.json. The generic 8GB packages remain unchanged.
All four packages conflict with the old generic cohort, so APT must remove that
optional cohort when selecting 16GB. The core system and Wi-Fi packages remain.

For a normal platform release, `release.yml` invokes
`scripts/build-release-optionals.py`. The product release lock is the only
platform version source: its `revision` becomes the exact kernel, headers and
BSP dependency, while the AXCL package revision is derived from the product
release version. The component lock retains only immutable upstream/source and
runtime/firmware inputs. `axcl-16g.yml` and its explicit component version fields
remain a legacy emergency-maintenance path and must not be used to assemble a
new platform release.

New packages enter noble-testing; publication alone does not establish hardware
acceptance. No service is automatically started by package installation. After
confirming card capacity and cooling:

```sh
sudo dspi-config source channel testing
sudo dspi-config update install <release-version>
sudo dshanpi-axcl check
sudo dshanpi-axcl test
```

The helper checks board/kernel, BTF configuration and the module structure size
against the original pwm_fan module before loading any AXCL modules. The driver
package depends exactly on the release lock's `linux-headers-vendor-rk35xx`
revision; the selector binds the matching image and BSP revision. Unchanged
runtime and firmware may be reused only at the exact version and SHA-256 pinned
in the component lock.

The original `dshanpi2` source has compiled successfully against the new headers
and produced all five expected modules with matching vermagic and module layout.
That is a build compatibility result, not a claim that module loading, PAC
initialization or NPU inference has passed on the new image.

The six-stream reference is pinned separately to demo commit
2aa772bbf16b8a904ee6ca57877c0e602208bf49. Real inference, RTSP/HTTP decoding,
recording and restart must be recorded before calling the complete path verified.
A1 CM5, R1 and Avaota A1 are excluded from this optional package set.
