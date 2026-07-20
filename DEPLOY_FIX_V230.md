
## Root Causes Identified

### 1. Malformed Filename (FIXED)
A DXF file was accidentally saved with the Python repr of a BytesIO object as its filename:
`<_io.BytesIO object at 0x7f1802c31080>`

The `<`, `>`, and space characters break Vercel's git checkout phase.

**Fix**: Removed the file from git and added .gitignore patterns to prevent recurrence.

### 2. Pro Features on Hobby Plan (FIXED)
The Vercel project had Pro-only features enabled while on the Hobby plan:
- `productionDeploymentsFastLane: true`
- `ssoProtection: {"deploymentType": "preview"}`
- `protectedSourcemaps: true`
- `oidcTokenConfig: {"enabled": true, "issuerMode": "team"}`
- `enableAffectedProjectsDeployments: true`
- `enableExternalRewriteCaching: true`

These caused the "Resource provisioning failed" error at the integrations step.

**Fix**: Disabled all Pro features via Vercel API (PATCH /v9/projects/{id}).

## Verification
- Frontend builds cleanly locally (vite build → 5.43s, 1955 modules, no errors)
- All Pro features disabled via API
- Bad file removed from git
