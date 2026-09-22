# Workspace move — 2026-09-16

The user requested moving `Update2` to `handvox` and removing unused files, then clarified that documents and important images must be retained.

- New project location: `C:/Users/Ult_Orange/Desktop/handvox`.
- Updated the active manifest's experiment location and experiment-index report paths without changing evaluation scores.
- Updated virtual-environment activation paths and regenerated 18 existing console launchers for the new interpreter location; packages were not downloaded or replaced.
- Original documents, important images, source, models, training/testing data, reports and backups were retained.
- Deletion commands were rejected by the execution policy, including a narrowly scoped bytecode-cache deletion. No cleanup deletion is claimed.
- Windows blocked renaming the open workspace directory. Project contents were moved to the new directory instead. The old `Update2` directory contains no files; an empty `.git` directory remains there. Do not use it as the project.
- Pre-move preservation inventory is in `tmp/workspace_cleanup/protected.json`; the previous evaluation object is in `tmp/workspace_cleanup/evaluation_before.json`.

Open the project from its new location and launch `HandVox.bat`. Old absolute paths inside historical reports/backups remain as provenance and were not rewritten.

## Verification

- All 2,180 protected files match their pre-move SHA-256 values.
- The active model loads with 19 classes and unchanged Accuracy 76.14678899%; the relocated source experiment exists.
- The relocated Python and `pip.exe` work. `git fsck --no-dangling` passed.
- Full suite: 166 tests, 165 passed and 1 skipped.
- Started the main app from the new directory.
