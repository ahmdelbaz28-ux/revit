# Operations Runbook — Vercel Webhook, SonarQube, AHJ Engagement

**Document ID:** OPS-RUNBOOK-2026-07-08
**Author:** AI Assistant (V143 hardening)
**Status:** ACTIVE — Requires human action for completion
**Scope:** Three operational tasks that cannot be fully automated by an AI agent
and require human/dashboard access.

---

## Task 1: Re-link Vercel GitHub Integration Webhook

### Problem

The GitHub → Vercel auto-deploy webhook was returning 404 (the Vercel deploy
hook ID `kHEPjW3IYR` is no longer valid). As a workaround, the
`.github/workflows/trigger-vercel.yml` workflow triggers Vercel deploys via
the Vercel REST API. This works but has limitations:

- Burns the Vercel free plan quota (100 deploys/day)
- Requires maintaining `VERCEL_DEPLOY_TOKEN` secret in GitHub
- Adds ~30-60s latency vs. native webhook
- No automatic PR preview deployments

### Solution

Re-link the Vercel GitHub integration via the Vercel dashboard. Once the
webhook is working, downgrade the `trigger-vercel.yml` workflow to
`workflow_dispatch` only (manual trigger as a fallback).

### Step-by-Step Procedure

> ⚠️ **Prerequisites**: You need admin access to both the GitHub repository
> (`ahmdelbaz28-ux/revit`) and the Vercel project (`revit`).

#### Step 1: Disconnect the broken integration

1. Go to https://vercel.com/dashboard
2. Select the **`ahmdelbaz28-ux/revit`** project
3. Click **Settings** → **Git**
4. Find the **GitHub** integration section
5. Click **Disconnect** (or **Remove** if already disconnected)
6. Confirm the disconnection

#### Step 2: Reconnect GitHub

1. In the same **Settings → Git** page, click **Connect Git Repository**
2. Select **GitHub** as the provider
3. Authorize Vercel to access your GitHub account (if not already done)
4. Select the **`ahmdelbaz28-ux/revit`** repository
5. Configure the integration:
   - **Production Branch**: `main`
   - **Preview Branches**: `feat/*`, `fix/*`, `hotfix/*`
   - **Production Deployments**: Enabled on push to `main`
   - **Preview Deployments**: Enabled on PR
   - **Cancel Previous Deployments**: Enabled (saves quota)

#### Step 3: Verify the webhook

1. Go to https://github.com/ahmdelbaz28-ux/revit/settings/hooks
2. You should see a Vercel webhook (URL like `https://api.vercel.com/v1/integrations/...`)
3. Click **Recent Deliveries** — should show no errors
4. Make a trivial commit to `main` (e.g., update a comment)
5. Check https://vercel.com/dashboard — a new deployment should appear
   within 30 seconds
6. Check GitHub → Actions → `Trigger Vercel Deploy` workflow — it should
   also run (this is expected; we'll disable it in Step 4)

#### Step 4: Downgrade the fallback workflow

Once the webhook is confirmed working, downgrade
`.github/workflows/trigger-vercel.yml` to manual-trigger only:

```yaml
# Change this:
on:
  push:
    branches:
      - main
    paths:
      - 'frontend/**'
      - 'vercel.json'
      - '.vercelignore'
      - 'public/**'
  workflow_dispatch:

# To this:
on:
  workflow_dispatch:  # Manual trigger only — webhook is the primary trigger now
```

This can be done via a PR or directly on `main`. After this change, the
workflow only runs when manually triggered from the Actions tab.

#### Step 5: Verify quota recovery

1. Monitor https://vercel.com/dashboard/usage for 24 hours
2. Confirm that deploy count is driven by webhook (not by the workflow)
3. If the webhook is stable, the `VERCEL_DEPLOY_TOKEN` GitHub secret can
   eventually be removed (but keep it for at least 1 week as a safety net)

### Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Webhook still 404 after reconnect | Vercel project ID mismatch | Verify `prj_Y6Qr828DXS83tWF1LntFakyofMrf` matches the project in Vercel dashboard |
| No webhook appears in GitHub hooks | Vercel app not authorized for the org | Go to GitHub → Settings → Applications → Vercel → Configure → grant access to `ahmdelbaz28-ux/revit` |
| Webhook delivers but no deploy | Branch filter mismatch | Confirm Production Branch is `main` (not `master`) |
| Deploys fail with "no framework detected" | `vercel.json` missing or framework misconfigured | Verify `vercel.json` has `"framework": "vite"` |

---

## Task 2: Run SonarQube Scanner After NOSONAR Removal

### Problem

The V143 hardening removed 430 file-level `# NOSONAR` suppressions across
the codebase. SonarQube will now analyze lines that were previously
silenced. This may surface **new warnings** that were hidden by the
file-level suppression.

### Solution

Run `sonar-scanner` against the SonarCloud project
(`ahmdelbaz28-ux_revit`) and triage any new findings.

### Prerequisites

1. **SonarCloud token**: Generate at
   https://sonarcloud.io/account/security/ (generate a token with
   "Execute Analysis" scope)
2. **sonar-scanner CLI**: Install via one of:
   - **Linux/macOS**: `brew install sonar-scanner` (macOS) or download from
     https://docs.sonarsource.com/sonarqube/latest/analyzing-source-code/scanners/sonarscanner/
   - **Docker**: `docker run --rm -v "$PWD:/usr/src" sonarsource/sonar-scanner-cli`
3. **Project key**: `ahmdelbaz28-ux_revit` (from `sonar-project.properties`)
4. **Organization**: `ahmdelbaz28-ux` (from `sonar-project.properties`)

### Step-by-Step Procedure

#### Step 1: Set up the token

```bash
export SONAR_TOKEN="your_sonarcloud_token_here"
```

> ⚠️ **Never commit the token.** Add it to `.env` (gitignored) or use a
> CI secret. The token has analyze-scope only, but still shouldn't be
> leaked.

#### Step 2: Run the scanner

```bash
cd /home/z/my-project/work/revit

# Option A: Local sonar-scanner CLI
sonar-scanner \
  -Dsonar.projectKey=ahmdelbaz28-ux_revit \
  -Dsonar.organization=ahmdelbaz28-ux \
  -Dsonar.sources=. \
  -Dsonar.host.url=https://sonarcloud.io \
  -Dsonar.login=$SONAR_TOKEN

# Option B: Docker (no local install needed)
docker run --rm \
  -v "$PWD:/usr/src" \
  -e SONAR_SCANNER_OPTS="-Dsonar.projectKey=ahmdelbaz28-ux_revit" \
  sonarsource/sonar-scanner-cli \
  -Dsonar.organization=ahmdelbaz28-ux \
  -Dsonar.sources=. \
  -Dsonar.host.url=https://sonarcloud.io \
  -Dsonar.login=$SONAR_TOKEN
```

#### Step 3: Wait for analysis

The scan takes 5-15 minutes depending on codebase size and SonarCloud
queue. Progress is visible at:
https://sonarcloud.io/project/activity?id=ahmdelbaz28-ux_revit

#### Step 4: Review findings

1. Go to https://sonarcloud.io/project/issues?id=ahmdelbaz28-ux_revit
2. Filter by:
   - **Status**: Open
   - **Severity**: Blocker, Critical, Major (skip Minor/Info for first pass)
   - **Since**: Previous 7 days (to see only new findings from NOSONAR removal)
3. For each finding, classify as:
   - **FALSE POSITIVE**: Mark as "Won't Fix" with reason "False positive"
   - **ACCEPTED RISK**: Mark as "Won't Fix" with reason and a per-line
     `# NOSONAR — <rule>: <justification>` suppression
   - **REAL BUG**: Create a GitHub issue and fix it

#### Step 5: Compare before/after metrics

1. Go to https://sonarcloud.io/project/metrics?id=ahmdelbaz28-ux_revit
2. Compare these metrics before and after the NOSONAR removal:
   - **Bugs**: should NOT increase (if it does, we uncovered real bugs)
   - **Vulnerabilities**: should NOT increase
   - **Code Smells**: MAY increase (previously suppressed findings now visible)
   - **Coverage**: should stay the same (we added 189 tests)
   - **Duplications**: should stay the same or decrease

#### Step 6: Document results

Append the scan results to `NOSONAR_AUDIT.md` Section "Phase 2 Verification":
- Total new findings: ___
- False positives: ___
- Accepted risks (with justification): ___
- Real bugs found and fixed: ___

### Expected Outcome

Based on the audit in `NOSONAR_AUDIT.md`:
- **Bugs**: Expected to increase slightly (some file-level suppressions were
  hiding real issues). Each must be triaged.
- **Code Smells**: Expected to increase significantly (S3776 cognitive
  complexity, S1192 duplicated literals were previously file-level suppressed).
  These are pre-existing; they were just hidden.
- **Security Hotspots**: Should NOT increase (no security-relevant code was
  unsuppressed in a way that would change analysis).

### CI Integration (Optional)

To run SonarQube on every PR, add to `.github/workflows/`:

```yaml
name: SonarCloud Analysis
on:
  push:
    branches: [main]
  pull_request:
    types: [opened, synchronize, reopened]
jobs:
  sonarcloud:
    name: SonarCloud
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Shallow clones should be disabled for better analysis
      - name: SonarCloud Scan
        uses: SonarSource/sonarcloud-github-action@master
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
```

Add `SONAR_TOKEN` as a GitHub secret first.

---

## Task 3: AHJ Engagement for ProofCertificate Acceptance

### Problem

The `ProofCertificate` (in `fireai/core/spatial_engine/proof_certificate.py`)
generates a mathematical proof that every point in a room is within NFPA 72
coverage radius R of a detector, using the δ-conservative grid method. This
proof is generated automatically by the platform.

However, the **Authority Having Jurisdiction (AHJ)** — typically the local
fire marshal or building department — must formally accept this proof method
before any design using it can be permitted. Without AHJ acceptance, the
ProofCertificate is mathematically valid but legally meaningless.

### Solution

Engage the AHJ in writing to obtain formal acceptance of the
δ-conservative grid verification method. This is a human-to-human process
that cannot be automated.

### Who is the AHJ?

The AHJ varies by jurisdiction:

| Location | Typical AHJ |
|----------|-------------|
| USA — most states | State Fire Marshal's Office + local Building Official |
| USA — large cities | City Fire Department, Fire Prevention Bureau |
| USA — federal (GSA, military) | Authority specific to the agency (e.g., DoD UFC 3-600-01) |
| Egypt (project context) | Civil Defense Authority (المدفوعة المدنية) + local municipality |
| GCC | Civil Defense + municipality |

> **Always confirm the AHJ with the local building department BEFORE
> starting a project.** Different jurisdictions have different acceptance
> criteria for computational proofs.

### Step-by-Step Procedure

#### Step 1: Prepare the technical package

Compile the following for the AHJ:

1. **Proof method documentation** (from `ENGINEERING_REVIEW_REQUIRED.md`):
   - The δ-conservative grid method description
   - The triangle-inequality mathematical proof
   - The grid resolution (δ = 0.20 m) justification
   - NFPA 72 §17.7.4.2.3.1 reference (R = 0.7 × S)

2. **Sample ProofCertificate** (generate one for a test room):
   ```bash
   cd /home/z/my-project/work/revit
   python -c "
   from fireai.core.spatial_engine.proof_certificate import ProofCertificateGenerator
   # Generate a sample certificate for a 10×10 m room
   # (see tests/test_proof_certificate.py for usage example)
   "
   ```

3. **PE/FPE sign-off** (from `ENGINEERING_REVIEW_REQUIRED.md`):
   - The signed per-change blocks for the ProofCertificate method
   - The Master Approval Block (if obtained)

4. **Validation evidence**:
   - Hand calculations for the same room (independent verification)
   - CFD/FDS simulation results if available (strongest evidence)
   - Full-scale test data if available (strongest evidence)

5. **Standards references**:
   - NFPA 72-2022 §17.7.4.2.3.1 (coverage radius)
   - NFPA 72-2022 Annex B.2 (engineering guide)
   - ISO 10303-21 (STEP format, used for certificate serialization)

#### Step 2: Schedule a pre-application meeting

Contact the AHJ and request a **pre-application meeting** (also called
"concept review" or "preliminary design review"). This is a standard
practice for non-standard design methods.

- **Purpose**: Present the ProofCertificate method and obtain informal
  feedback before formal submission
- **Duration**: 30-60 minutes
- **Attendees**: AHJ fire protection engineer, project PE/FPE, software
  architect (if the AHJ has technical questions)
- **Outcome**: Either "looks acceptable, proceed with formal submission"
  or "we need X, Y, Z before we can review"

#### Step 3: Formal submission

Submit the technical package (Step 1) as part of the building permit
application. The AHJ will:

1. Review the proof method
2. May request additional documentation (e.g., third-party review)
3. May request modifications (e.g., finer grid resolution, additional
   safety factors)
4. Issue an **acceptance letter** or **approval stamp**

#### Step 4: Document the acceptance

Once accepted, document in the project file:

1. **AHJ acceptance letter** (scan, store in project records)
2. **AHJ reference number** (add to `ENGINEERING_REVIEW_REQUIRED.md`
   Master Approval Block, "AHJ Reference" field)
3. **Acceptance date**
4. **Accepted scope** (which occupancy types, building heights, detector
   types are covered)
5. **Any conditions** (e.g., "accepted only for smoke detectors, not heat
   detectors" or "accepted only up to 10m ceiling height")

#### Step 5: Update the ProofCertificate generator

If the AHJ imposed conditions (Step 4.5), update
`fireai/core/spatial_engine/proof_certificate.py` to enforce them:

- If "smoke detectors only" → add a `detector_type` parameter and reject
  heat detector certificates
- If "up to 10m ceiling" → add a ceiling height check
- If "finer grid" → update `grid_step_m` default

Each change must go through the PE/FPE sign-off process again per
`ENGINEERING_REVIEW_REQUIRED.md`.

### AHJ Engagement Letter Template

```
[Project Letterhead]

Date: _______________

To: [AHJ Name and Title]
    [AHJ Organization]
    [Address]

Subject: Request for Acceptance of Computational Coverage Verification Method
         Project: [Project Name]
         Project Address: [Address]

Dear [AHJ Name],

We are submitting for your review a computational method for verifying
fire alarm detector coverage per NFPA 72-2022 §17.7.4.2.3.1. The method
uses a δ-conservative grid verification with the following parameters:

  - Grid resolution (δ): 0.20 m
  - Coverage radius (R): 0.7 × S (per NFPA 72 §17.7.4.2.3.1)
  - Effective radius (R_eff): R − δ√2/2
  - Verification: every grid point must be within R_eff of a detector

The method has been reviewed and signed by:
  Engineer: [Name], PE/FPE License #[Number], [State]
  Review Date: [Date]

We request your formal acceptance of this method for the above-referenced
project. We are available for a pre-application meeting at your
convenience.

Enclosed:
  1. Proof method documentation (including mathematical proof)
  2. Sample ProofCertificate for a test room
  3. PE/FPE sign-off documentation
  4. Validation evidence (hand calculations + CFD results)
  5. NFPA 72 standards references

Sincerely,

[Project Engineer Name], PE/FPE
[Title]
[Contact Information]
```

### Timeline Expectation

| Step | Typical Duration |
|------|-----------------|
| Prepare technical package | 1-2 weeks |
| Schedule pre-application meeting | 1-3 weeks (AHJ-dependent) |
| Pre-application meeting | 1 day |
| Formal submission review | 2-8 weeks (AHJ-dependent) |
| AHJ acceptance letter | 1-2 weeks after review |
| **Total** | **4-15 weeks** |

> ⚠️ **Start this process EARLY** — ideally during schematic design, not
> during construction documents. AHJ rejection at the CD stage can delay
> a project by months.

### Fallback if AHJ Rejects

If the AHJ does NOT accept the computational proof method:

1. **Manual verification**: Hand-calculate coverage for every room and
   include the calculations in the permit drawings
2. **Third-party review**: Hire an independent FPE to review and stamp
   the coverage calculations
3. **Physical testing**: For high-profile projects, conduct a full-scale
   smoke test (expensive but definitive)
4. **Conservative over-design**: Add 10-20% more detectors than the
   minimum required, so even if the proof has a small error, the design
   still meets code

In all cases, the platform's ProofCertificate can still be used
internally as a design aid, but the permit submission must use the
AHJ-accepted method.

---

## Revision History

| Rev | Date | Author | Change |
|-----|------|--------|--------|
| 1.0 | 2026-07-08 | AI Assistant (V143) | Initial runbook — 3 operational tasks documented with step-by-step procedures, troubleshooting, and templates. |
