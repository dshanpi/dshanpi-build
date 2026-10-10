---
name: maintain-dshanpi-delivery
description: Maintain pinned DShanPI DEB recipes, signed APT releases, product image orchestration and release evidence in dshanpi-build.
---

# maintain-dshanpi-delivery

Read root AGENTS.md and [DELIVERY_POLICY.md](../../../DELIVERY_POLICY.md) before work. Run policy and indexed-source hygiene checks; with sibling checkouts use --peer. The repository is the sole release orchestrator; board/kernel/DT sources belong in ArmBianOS, client interaction in dspi-config.

For a new machine or handoff, read [the server guide](../../../docs/new-server.md). For current limitations and prior findings, read [the development handoff](../../../docs/development-handoff.md).

- Keep optional components under packages/<component>; pin upstream commit or archive SHA and put new source adaptations in reviewable patches. Never replace a vendor archive in place.
- Board profiles belong to BSP. AXCL capacity selects a paired runtime/PAC and explicit package conflicts; it is not another board and cannot be silently upgraded from 8GB to 16GB.
- Package-maintenance locks with maintenance_adapter use their matching build-*-release.py adapter, not build-product.sh. Full image plans use build-product.sh and must have a fresh revision when contents change.
- Reuse signed historical bytes. Changing payload, dependencies or maintainer scripts requires a Debian version increase. Compare candidate hashes before claiming byte-identical refactoring.
- Publish testing first through the fixed workflow. Stable reuses exactly tested bytes. G12 applies to every image. A passed policy check or retained artifact does not prove GitHub Release publication.
- Keep functional changes and evidence in separate commits, linked by source/package hashes. Run Python/Shell tests, syntax and diff checks; preserve public-download evidence and distinguish dependency simulation from hardware rollback.
- Signing keys and personal credentials stay outside Git. Do not copy output/work trees into commits; review indexed paths and run tools/check-repository-hygiene.py before pushing.
