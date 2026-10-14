---
record_id: CR-2026-10-14-avaota-a1-t527-image-release
date: 2026-10-14
repository: dshanpi-build
requirements:
  - REQ-REL-AVAOTA-T527-20261014-001
---
# Avaota A1 T527 fixed image and APT release

## 需求与范围

The user requested the same fixed-version delivery loop used for DShanPI boards for `avaota-a1`,
based on the Allwinner T527 platform. This release fixes the current ArmBianOS and dspi-config source
commits, builds the exact DEB cohort plus CLI and GNOME images on the controlled local builder, publishes
the signed package cohort to the testing APT channel and uploads the fixed image assets directly to
`dshanpi/ArmBianOS` Releases. It does not claim stable or physical-board acceptance.
The two older Avaota A1 testing-only cohorts are replaced atomically because the GitHub Pages repository
cannot retain both old T527 kernel cohorts and the new fixed cohort within its enforced capacity budget.

## 业务逻辑

The release lock is the version fact source for product `avaota-a1`, release `2026.10.14-1` and Armbian
revision `25.11.0-trunk.20261014.1`. The product keeps its own APT component, BSP, T527 legacy kernel,
device tree and core/desktop release metadata. Both image variants consume the same exact signed package
cohort and expose the standard initial login contract. Complete image work runs locally; GitHub-hosted
CI remains available for signed APT publication and later promotion without rebuilding image bytes.
The reviewed purge removes only Avaota A1 testing manifests `2026.10.08-1` and `2026.10.09-1`, then
garbage-collects only pool objects with no remaining manifest reference. Stable indexes and every package
still referenced by another product or release remain unchanged.

## 流程

```mermaid
flowchart TD
  A[Fixed Avaota A1 release lock] --> B[Validate source commits product and executor]
  B -->|invalid or existing version| C[Reject without build or overwrite]
  B -->|valid| D[Build T527 kernel BSP dspi-config and exact DEBs locally]
  D --> E[Build CLI and GNOME images from exact DEBs]
  E --> F[Read-only image and SHA-256 validation]
  F -->|failure| G[Retain evidence and stop without publication]
  F -->|pass| H[Publish signed cohort to noble-testing]
  H --> H2[Atomically replace old Avaota testing cohorts and keep referenced bytes]
  H2 --> I[Verify public index signature package bytes and dependency simulation]
  I -->|failure| G
  I -->|pass| J[Prepare fixed Release assets and login notes]
  J --> K[Direct local upload to ArmBianOS prerelease]
  K --> L[Verify public tag assets sizes hashes and notes]
  L --> M[Await Avaota A1 physical-board acceptance]
  M -->|accepted| N[Promote identical APT bytes and Release metadata to stable]
```

## 安全与失败分支

- The source commits, product, revision, tag, image names and asset list are immutable inputs.
- GitHub-hosted Actions must reject complete-image testing before checkout or build; local image upload
  refuses existing tags and unexpected assets.
- Package identities with changed content require a new Debian version; historical packages and Releases
  are not deleted or overwritten.
- Missing T527 headers, kernel/headers mismatch, wrong DTB, unsigned source configuration, dependency
  failure or image verification failure stops publication.
- Upload or build failures are visible and are not treated as success; recovery reuses only verified bytes.
- Stable promotion requires separate Avaota A1 hardware evidence and never rebuilds the testing cohort.
- The purge rejects a missing target cohort, a non-testing target, a product/version mismatch or any pool
  object that remains referenced; it never deletes stable metadata.

## 测试报告

| 类型 | 命令/检查 | 结果 | 证据 |
| --- | --- | --- | --- |
| Policy | `python3 tools/check-delivery-policy.py --peer ../ArmBianOS --peer ../dspi-config` | PASS | Local output before modification |
| Plan | `scripts/build-product.sh avaota-a1 products/avaota-a1/releases/2026.10.14-1.lock.json --print-plan` | PASS | Fixed commits, legacy branch and CLI/Desktop variants printed |
| Unit | `python3 -m unittest discover -s tests -v` | PASS | 65 tests passed locally |
| Shell | `bash tests/test.sh` | PASS | `dshanpi-build tests passed` |
| Package build | Exact T527 DEB cohort | NOT-RUN | Local build output |
| Image validation | CLI and GNOME read-only verification | NOT-RUN | Local verification logs |
| Public APT | Signature, index, package hashes and simulated install | NOT-RUN | Public endpoint checks |
| Public Release | Tag, six fixed assets, hashes and login notes | NOT-RUN | GitHub Release API |
| Hardware | Boot, display, storage, Ethernet/Wi-Fi, USB and reboot recovery | NOT-RUN | No Avaota A1 board evidence supplied |

## 未完成项

All build and publication steps remain pending at record creation time. Avaota A1 physical-board testing
is not available in this session, so the image must remain a prerelease and the package cohort must remain
in testing until separate board evidence is committed.

The first signed Pages candidate built successfully in run `38561145467` but publication was stopped by
the 950 MB capacity gate. The SSH fallback run `38563975060` stopped before repository download because
that backend has no configured credentials. Neither failed attempt changed the public repository. The
reviewed replacement purge is required before retrying the Pages publication.

## 交付影响

This adds a reproducible Avaota A1/T527 complete-image release without consuming GitHub-hosted image-build
minutes. Once the fixed image is installed, later ordinary DEB additions and updates use the signed APT
maintenance path and do not require customers to reflash the system.
