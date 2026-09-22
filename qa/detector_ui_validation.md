# Camera UI validation — 2026-09-15

## Scope

- Compact 1080×680 camera view with separate recognition/sentence controls; experimental warning retained.
- Batched canvas rendering and bounded glyph cache replace repeated full-frame Thai text conversions.
- Passive rolling timings, actual prediction rate, and observed sequence time span; no guessed training FPS.
- Expire incomplete motion after landmarks remain missing past the existing release timeout.
- No model, label, training sequence, feature pipeline, confidence threshold, or acceptance-score changes.

## Automated checks

- `python -m unittest discover -s tests -q`: 166 tests, 165 passed, 1 skipped.
- Syntax compilation and whitespace checks for changed tracked files passed.
- Protected model, manifest, labels, gesture sequences and active gesture catalog SHA-256 values unchanged.
- Coverage includes disabled actions, preserving camera input, two color conversions per render, cached chrome, Thai/large-font layout, trial warning, missing landmarks, candidate vs confirmed state, stale sequence expiry, timing math, and all five sentence actions.

## Paired offline replay

The same existing local water-gesture preview was replayed for 120 frames, resized identically to 1280×720 in both runs. The first 10 frames were excluded from timing summaries. Camera-driver wait, native display, speech and history writes were disabled. First model inference warmup remains included. This is a rendering/runtime regression check, not a held-out accuracy evaluation.

| Measurement | Before | After |
| --- | ---: | ---: |
| Mean processing time/frame | 224.96 ms | 92.50 ms |
| Processing FPS | 4.45 | 10.81 |
| p95 processing time/frame | 249.28 ms | 100.08 ms |
| Mean landmark stage | 68.18 ms | 65.29 ms |
| Predictions | 91 | 91 |

All 91 transformed model inputs and all class probabilities matched exactly. The latest paired speedup is 2.43×. Earlier runs varied with machine load (before 5.92 FPS; new renderer 10–12 FPS), so these numbers are not a promised live-camera rate.

Local raw evidence: `tmp/detector_ui/before_final_pair.json`, `tmp/detector_ui/after_final_pair.json`; previous source snapshot: `tmp/detector_ui/run_detector_before.py`. Run `tools/profile_detector_replay.py --source <source.py> --video <same-video.mp4> --output <result.json>` to repeat.

## Native check and limits

- Opened the actual camera and inspected compact layout, warning, unavailable-action states and readable frame-rate display.
- Details button successfully expanded stage timings; close button released the camera and exited cleanly.
- Native observations around 13–14 FPS were not a controlled accuracy comparison and included periods without visible hand landmarks.
- Training clips do not contain reliable per-frame capture timestamps. The runtime still consumes 30 valid processed frames, without resampling or frame duplication. Their real duration can change when processing becomes faster.
- New-user accuracy, streaming word errors and gesture-end-to-word latency still require labeled live trials. No improved Accuracy/F1 claim is made.
