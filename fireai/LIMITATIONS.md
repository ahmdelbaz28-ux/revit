# Known Limitations

- **Maximum room area**: 5,000 m² (automated design refused beyond).
- **Maximum dimension**: 1,000 m (width/depth) – rooms exceeding this are rejected.
- **Height clamping**: Heights < 3.0 m or > 15.24 m are clamped to the NFPA 72 range and must be reviewed by a licensed PE.
- **Polygon complexity**: Up to 5,000 vertices accepted.
- **String lengths**: Room identifiers limited to 200 characters.
- **Imported files**: DWG/RVT parsing is not yet integrated; use JSON polygon data.
- **Rate limits**: 30 req/min per room, 10 req/min per floor/project upload.