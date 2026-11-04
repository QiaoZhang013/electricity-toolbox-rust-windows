# Windows incremental updates implementation plan

> For agentic workers: use superpowers:executing-plans inline. A fresh-context
> whole-change review is required at the end; no per-task implementer agents.

**Goal:** small, verified Windows updates that reuse the runtime and preserve data.
**Architecture:** shared routing, Windows file patch/staging, existing Rust helper
transaction, independent Windows release builder and complete-installer fallback.
**Tech Stack:** Python standard-library tar/xz/hash/file links, existing Rust
serde/sha2/std, original Tk and NSIS.
**Spec:** docs/superpowers/specs/2026-11-04-windows-delta-update-design.md

## Global constraints

- Windows 10 / 11 x64; unchanged original Tk layout and separate repository.
- Full NSIS remains available, data is outside install/stage, cancellation never
  downloads the fallback, all paths and inventories are independently checked.
- Keep development checkout; task started clean at c1ca8f7. Local build artifacts,
  auth/profile/configuration stay ignored. Publish only after acceptance.

## Review focus

- Windows names/reparse points and archives may escape a naive POSIX validator.
- Hard links must be broken before modification; old running bytes stay intact.
- Runtime files modified after staging must prevent committing a mixed baseline.
- Disk/rename/relaunch failure must preserve recoverable old installation/data.
- A cancelled patch, or failed transfer before app exit, must keep old app usable.

## Tasks

1. [x] Add failing tests for Windows route and archive/staging behavior in
   `desktop/tests/python/test_windows_delta.py`. Add Windows platform parameter
   to shared route function in `desktop/python/delta_update.py`; implement
   `desktop/python/windows_delta.py`: inventory, validate_inventory, create_patch,
   clone_installation, apply_patch, prepare_update and safe owned-stage cleanup.
   Verify old bytes, target inventory, links, malicious inputs and cancellation.
2. [x] Add failing schema-2 actual-helper tests in
   `desktop/tests/python/test_windows_update_helper.py`; extend
   `native/price-xlsx/src/windows_update.rs`, using a focused Windows delta module
   if needed. Preserve schema-1 behavior. Test staging/plan mutation, process
   timeout, rollback, data/registry preservation and real relaunch.
3. [x] Add failing client/UI tests in `test_windows_update.py`/`test_update_ui.py`.
   Integrate optional index discovery, shared route, staged download, fallback,
   cancellation, schema-2 handoff/helper and safe cleanup in windows_update.py.
   Existing macOS/default route behavior must remain unchanged. Include Windows
   module in packaging runtime source. If adding resume, test real short local
   HTTP transfers including dropped response, validated 206 and ignored Range.
4. [x] Add release-builder tests and `packaging/windows/build_updates.py`.
   Retain history and three verified direct patches; integrate build.ps1 and
   document initial-full/then-incremental operation and full-only resets.
5. [ ] Run focused/full updater and relevant Tk/service/WPS tests. Fresh-context
   review, address concrete findings, rerun affected tests. Version.py set 0.1.28
   with concrete notes and results; compile native service and host, refresh
   payload, build/accept full installer and three historical patches. Preserve
   registry/shortcuts and verify runtime reuse and Excel read-back.
6. [ ] Commit/push only task source to origin/development, read back, archive
   exact source commit. Verify tag/notes, upload draft full/source/patch/index
   assets, server digest checks; perform authentic incremental transaction and
   old-client bootstrap validation. Publish verified release; update main direct
   links/Actions only. Public/update checks and concise evidence/limitations.

## Execution ledger

- Ruling: follow explicit repository preference for direct implementation on
  development; no extra design approval/menu, and no worktree branch switch.
  The prior answer proposed incremental updates, which the user now requested.
- Ruling: stage a complete tree using hard links then rename directories, rather
  than mutating installed files in place. This preserves transaction rollback
  and avoids repeatedly decompressing or copying unchanged runtime files.
- Ruling: bootstrap is one final full update; subsequent update speed must be
  demonstrated using the new updater, without claiming legacy 0.1.27 can parse it.

- Tasks 1–4: Windows core 11/11; client/resume 17/17; builder 3/3; full updater regression 68 tests, 15 mac-only skipped; native helper 12/12 and service 12/12 passed before final review. WPS compatibility 5/5 passed.
- Final review: one fresh-context read-only reviewer. No critical/minor findings. Important preservation race accepted: late-added/replaced unmanaged installation files could be lost. Actual-helper tests reproduced both cases; related full fallback preservation test also failed. Fix pass compares all unmanaged extras before delta commit and preserves unknown regular extras during full installation. Final RED→GREEN and suite gate pending rebuild.
- Final: Ruling: installer/three historical patches/public attachment integrity/live bootstrap/incremental relaunch/Excel readback — reviewer cannot establish these from source; executor must run these acceptance gates before publishing. Cost if wrong: broken updates or data loss. Windows10/macOS machine execution remains unavailable and must be disclosed.

- Final: Ruling: include official uninstall.exe in the managed patch tree — inspecting the actual NSIS script proved old uninstallers enumerate old resource filenames and would leave newly added files. Two genuine 0.1.27 installations have identical uninstaller SHA-256, so baselines are reproducible. Core roundtrip test failed with old-uninstaller retention; fix now updates/validates the target uninstaller. Cost if wrong: incomplete uninstall; actual isolated uninstall gate required.

- Final: fixed unmanaged-extra preservation race — test_delta_rejects_added_or_atomically_replaced_unknown_local_files and test_full_update_preserves_unknown_local_files RED→GREEN; updater suite 70 tests green (15 mac-only skipped). Official-uninstaller roundtrip RED→GREEN, Windows core11/11 green. Fresh reviewer reported no other Critical/Important or deferred Minor findings.
