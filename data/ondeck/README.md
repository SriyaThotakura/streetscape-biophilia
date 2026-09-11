# On-deck capture — closing the validation loop

The geometric deck model (`svf_deck`) is currently **unvalidated**: the CV audit
was shot from the street, ~30 m off-centreline, so it measures a different thing
(the reconciliation proved r≈0, because the elevated deck itself blocks the
street-level sky). The only honest ground truth is imagery captured **on the deck**.
This folder is where that imagery goes.

## Field protocol (≈45 min walk)

1. **Walk the deck** Gansevoort → 34th St. Stop roughly every **40 m** (~48 stops
   over the 1.86 km) — denser near the towers (26th–30th St) where enclosure varies fast.
2. **One photo per stop**, phone held at **eye level, pointing forward along the deck**
   (the same view a walker has — *not* up at the sky, not at your feet). Portrait or
   landscape is fine; keep it consistent.
3. **Record position** at each stop, easiest of:
   - the **nearest access point** + your rough distance past it → convert to `s_m`
     using the table in `manifest.csv`, **or**
   - just rely on **phone GPS** (leave `s_m`/`lat`/`lng` blank — EXIF is read
     automatically). GPS on the deck is a little noisy but fine at 40 m spacing.
4. **30–50 photos is plenty.** Even 30 gives a real correlation.

## Then run

```
# drop the photos in this folder, fill manifest.csv (or rely on EXIF), then:
python scripts/validate_ondeck.py --ingest data/ondeck
# add --model nvidia/segformer-b5-finetuned-cityscapes-1024-1024 to match the project exactly
```

It segments sky with the same SegFormer pipeline, pulls `geom_svf_deck` at each
`s_m`, and reports **r / R² / RMSE** of measured on-deck sky vs the model, writing
`data/ondeck_validation.json`.

## Reading the result

- **R² ≥ 0.5** — geometry predicts on-deck perception → the deck model (and the
  whole self-enclosure argument) is grounded in real perception.
- **0.25–0.5** — partial; building massing explains some of it, vegetation and the
  deck's own planting/structure the rest.
- **< 0.25** — weak; on-deck sky isn't mainly building-geometric. That's not a
  failure — it's a finding. Look at *which* frames diverge (likely the densely
  planted stretches) and report that.

Any of these outcomes is publishable; leaving it unrun is the one weak spot.
