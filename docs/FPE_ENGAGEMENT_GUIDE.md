# FPE Engagement Guide — How to Find and Work with a Fire Protection Engineer

**Version:** 1.0  
**Date:** 2026-05-15  
**Purpose:** Guide for finding and engaging an FPE for FireAI review

---

## 1. Why You Need an FPE

FireAI is a **fire alarm system design and verification tool**.
- Lives are at stake if the system fails
- Professional Engineer (PE) licensure is typically required
- Liability protection requires FPE sign-off

---

## 2. Where to Find FPEs

### 2.1 Professional Organizations

| Organization | Website | Member Search |
|--------------|---------|--------------|
| SFPE (Society of Fire Protection Engineers) | sfpe.org | Find a Member |
| NFPA | nfpa.org | Member Directory |
| AIA (American Institute of Architects) | aia.org | Find Architects |
| Local PE Boards | state-specific | License Lookup |

### 2.2 Fire Alarm Companies

| Type | Examples |
|------|---------|
| Manufacturers | Honeywell, Siemens, Notifier, Bosch |
| Distributors | ADI, Grainger, MSC |
| Installers | Local fire alarm contractors |

### 2.3 Academic Institutions

| Type | Contact |
|------|--------|
| Fire Engineering Programs | University engineering departments |
| Research Labs | NFRI, UL Fire Labs |

---

## 3. How to Approach an FPE

### 3.1 Initial Contact

**What to say:**
```
Subject: Fire Alarm Design Verification Tool Review

I am developing an automated fire alarm design verification tool (FireAI)
that analyzes CAD drawings for NFPA 72 compliance.

Would you be available for a 30-minute introductory call to:
1. Review the system's approach
2. Discuss NFPA 72 compliance requirements
3. Explore potential review/consultation opportunities?

I can share technical documentation and test results.
```

### 3.2 What to Prepare Before Contact

Before reaching out, have ready:
1. [x] Technical overview of FireAI
2. [x] NFPA 72 compliance approach
3. [x] Test results documentation
4. [x] Known limitations list
5. [x] EULA for beta users

### 3.3 What FPEs Typically Ask

| Question | Your Answer |
|----------|-----------|
| "Who's liable?" | EULA limits liability, PE sign-off required |
| "What NFPA standard?" | NFPA 72 (2022) |
| "What's the failure mode?" | Documented in KNOWN_ISSUES.md |
| "How verified?" | See V&V_RESULTS.md |

---

## 4. Compensation Models

### 4.1 Standard Options

| Model | Typical Rate | What's Included |
|-------|------------|----------------|
| Hourly Consultation | $150-300/hr | Review calls, questions |
| Technical Review | $500-2000 | Full system review |
| Ongoing Advisory | $1000-5000/mo | Regular consultation |
| Sign-off | $2000-10000+ | Project-specific PE stamp |

### 4.2 Alternative Arrangements

- **University partnership** - Research collaboration
- **Industry sponsorship** - Vendor introduction
- **Public benefit** - Non-profit engagement

---

## 5. FireAI Documentation for FPE Review

When you engage an FPE, share these:

| Document | Location | Purpose |
|----------|----------|---------|
| DECISION_LOG.md | docs/decisions/ | All critical decisions |
| V&V_RESULTS.md | docs/vnv/ | Test results |
| KNOWN_ISSUES.md | docs/issues/ | Limitations |
| FPE_REVIEW_CHECKLIST.md | docs/ | Review protocol |
| 4TIER_DOC.md | docs/ | System architecture |

---

## 6. Liability Considerations

### 6.1 What Requires FPE Sign-off

- Final design approval
- Permit applications
- AHJ submissions
- Construction documents

### 6.2 What FireAI Can Do (Without FPE)

- Preliminary analysis
- Coverage calculations
- Design suggestions
- Bill of quantities
- **NOT:** Final approval

### 6.3 Disclaimer Language

```
FireAI provides analysis for informational purposes only.
All designs require Professional Engineer review and approval
before construction or permit submission.
```

---

## 7. Sample FPE Outreach Email

```
Subject: Fire Alarm Design Tool Review - Technical Discussion

Dear [FPE Name],

I am reaching out regarding FireAI, an automated fire alarm 
design verification tool that I have developed.

TECHNICAL OVERVIEW:
- Analyzes CAD/PDF drawings for NFPA 72 compliance
- 4-tier confidence system (text → CV → raster → reverse scale)
- Open source (GitHub: ahmdelbaz28-ux/revit)

DOCUMENTATION AVAILABLE:
- Decision log with threshold justification
- V&V results on test drawings
- Known limitations document
- FPE review checklist

I would appreciate the opportunity to:
1. Walk through the system's approach
2. Get your feedback on the methodology
3. Discuss potential consultation or review opportunities

Available for a 30-minute call at your convenience.

Best regards,
[Your Name]
[Your Contact]
```

---

## 8. Rejection Handling

### Common FPE Concerns

| Concern | Response |
|--------|----------|
| "Not my expertise" | Fire alarm is specialized - find SFPE member |
| "No time" | Offer compensation or academic partnership |
| "Liability concerns" | EULA + clear limitations documented |
| "Need more assurance" | Offer extended documentation |

### If Rejected

1. Thank them for their time
2. Ask for referrals to other FPEs
3. Try alternative sources (vendors, contractors)

---

## 9. Success Metrics

Track your FPE engagement:

| Metric | Target |
|--------|--------|
| Initial contacts | 10+ |
| Responses | 3+ |
| Meetings scheduled | 1-2 |
| Review commitment | 1 |

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-05-15 | Initial guide |