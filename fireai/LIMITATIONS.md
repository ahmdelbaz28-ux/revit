# Known Limitations

- **Maximum room area**: 5,000 m² (automated design refused beyond).
- **Maximum dimension**: 1,000 m (width/depth) – rooms exceeding this are rejected.
- **Height limits**: Two-tier ceiling height system per NFPA 72-2022:
  - **Soft limit** (PE review required): > 15.24 m (50 ft) — coverage radius table boundary exceeded
  - **Hard limit** (design rejected): > 18.288 m (60 ft) — spot-type smoke detectors NOT permitted per §17.7.3.2.4
  - Heights below 3.0 m may require special considerations
- **Smoke detector spacing**: FLAT 9.1 m (30 ft) per NFPA 72-2022 §17.7.3.2.3 — NO height-based spacing reduction. For ceilings above 6.096 m (20 ft), stratification makes spot-type smoke detection unreliable per §17.7.1.11; consider beam detectors (§17.7.4.6) or aspirating systems (§17.7.4.7).
- **Heat detector spacing**: Height-adjusted per NFPA 72 Table 17.6.3.5.1 (1% per foot reduction above 10 ft).
- **Polygon complexity**: Up to 5,000 vertices accepted.
- **String lengths**: Room identifiers limited to 200 characters.
- **Imported files**: DWG/RVT parsing is not yet integrated; use JSON polygon data.
- **Rate limits**: 30 req/min per room, 10 req/min per floor/project upload.