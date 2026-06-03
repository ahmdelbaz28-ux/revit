# Known Limitations

- **Maximum room area**: 5,000 m² (automated design refused beyond).
- **Maximum dimension**: 1,000 m (width/depth) – rooms exceeding this are rejected.
- **Height limits**: Two-tier ceiling height system per NFPA 72-2022:
  - **Soft limit** (PE review required): > 15.24 m (50 ft) — coverage radius table boundary exceeded
  - **Hard limit** (design rejected): > 18.288 m (60 ft) — spot-type smoke detectors NOT permitted per §17.7.3.2.4
  - Heights below 3.0 m may require special considerations
- **Polygon complexity**: Up to 5,000 vertices accepted.
- **String lengths**: Room identifiers limited to 200 characters.
- **Imported files**: DWG/RVT parsing is not yet integrated; use JSON polygon data.
- **Rate limits**: 30 req/min per room, 10 req/min per floor/project upload.