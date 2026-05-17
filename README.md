# NFPA 72 Calculator

## ⚠️ Historical Acknowledgments

**Previous claims in this repository were incorrect:**
- "FireAI" and "FireAlarmAI" names are misleading - this is an NFPA 72 calculator, not AI
- "Production Ready" claims were premature
- "67% success" claims in commit d429e48 were fraudulent - reverted
- Auto-detection does not work - manual input is required

## What This Tool Does

- Extracts geometry from floor plan PDFs (wall detection)
- Calculates NFPA 72-2022 compliant detector coverage
- Requires MANUAL room type input via `--room-types` JSON file
- No automatic room type detection - engineer must verify all inputs

## Usage

```bash
# Run with manual room types
python3 run_full_pipeline.py floor_plan.pdf --room-types room_types.json

# Without room types - all rooms show as unknown with 0 detectors
python3 run_full_pipeline.py floor_plan.pdf --non-interactive
```

## Known Limitations

- NO automatic room type detection
- NO validation on room size vs room type
- Engineer must manually input room types
- Large spaces (>500m²) require special review
- Output requires PE (Fire Protection Engineer) review

## Room Types Sample

Edit `room_types_sample.json` to match room names in your PDF:

```json
{
  "rooms": {
    "room_1": "atrium",
    "room_2": "corridor",
    "room_3": "kitchen"
  }
}
```

## Status

- NOT production ready
- REQUIRES engineer verification
- NOT an AI system
