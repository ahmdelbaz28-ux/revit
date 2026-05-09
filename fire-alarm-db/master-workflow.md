# 🔥 Fire Alarm Design System — Master Workflow Map

## Project: Fire Alarm Design & Compliance Software
## Version: 1.0 | Date: 2026-05-09
## Author: baz (AI Consultant) + Ahmed (Project Owner)

---

## 📋 Executive Summary

This document defines the complete lifecycle of building a professional fire alarm design
software — from initial research to product launch. Every phase has clear inputs, outputs,
deliverables, acceptance criteria, and dependencies.

**Target Users:** Fire protection engineers, MEP consultants, electrical contractors
**Target Markets:** Egypt, GCC, Middle East (expandable globally)
**Applicable Standards:** NFPA 72, BS 5839-1, EN 54, Egyptian Code
**Project Type:** Safety-critical engineering design tool

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                      │
│   Web UI (React/Vue) or Desktop (Electron/WPF)           │
├─────────────────────────────────────────────────────────┤
│                    APPLICATION LAYER                      │
│   ┌──────────┐ ┌───────────┐ ┌────────────┐ ┌────────┐ │
│   │  Project  │ │  Design   │ │ Validation │ │ Report │ │
│   │  Manager  │ │  Engine   │ │  Engine    │ │ Engine │ │
│   └──────────┘ └───────────┘ └────────────┘ └────────┘ │
├─────────────────────────────────────────────────────────┤
│                    DOMAIN LAYER (Core)                    │
│   ┌──────────┐ ┌───────────┐ ┌────────────┐ ┌────────┐ │
│   │Spacing   │ │Voltage    │ │  Battery   │ │Coverage│ │
│   │Engine    │ │Drop Engine│ │  Calculator│ │Engine  │ │
│   │          │ │           │ │            │ │        │ │
│   │NFPA Rules│ │BS Rules   │ │EN Rules    │ │Egypt   │ │
│   └──────────┘ └───────────┘ └────────────┘ └────────┘ │
├─────────────────────────────────────────────────────────┤
│                    DATA LAYER                             │
│   ┌──────────┐ ┌───────────┐ ┌────────────┐ ┌────────┐ │
│   │ Standards │ │  Device   │ │  Project   │ │  User  │ │
│   │ Database  │ │  Database │ │  Database  │ │  Auth  │ │
│   └──────────┘ └───────────┘ └────────────┘ └────────┘ │
├─────────────────────────────────────────────────────────┤
│                    INFRASTRUCTURE                         │
│   Database (PostgreSQL) │ API (Node/Python) │ Storage    │
└─────────────────────────────────────────────────────────┘
```

---

## 🗺️ Phase Map — Overview

| Phase | Name | Duration | Key Deliverable |
|-------|------|----------|-----------------|
| **0** | Research & Discovery | 2-3 weeks | Market Analysis + Requirements Document |
| **1** | Requirements & Specs | 2 weeks | PRD + Functional Specifications |
| **2** | System Architecture & DB Design | 3 weeks | Architecture Doc + Database Schema + API Design |
| **3** | Core Calculation Engines | 5-6 weeks | All calculation engines tested & validated |
| **4** | Standards Engine & Rule System | 3-4 weeks | Configurable rule engine with NFPA/BS/EN rules |
| **5** | Floor Plan & Auto-Layout | 5-6 weeks | Floor plan import + device placement engine |
| **6** | UI/UX Development | 6-8 weeks | Complete user interface |
| **7** | Export, Reports & Integration | 3-4 weeks | DWG export, PDF reports, BIM integration |
| **8** | Testing & Validation | 4-5 weeks | QA, compliance validation, penetration testing |
| **9** | Beta, Feedback & Polish | 3-4 weeks | Beta program, bug fixes, UX refinements |
| **10** | Launch & Documentation | 2-3 weeks | Production deployment, docs, training |

**Estimated Total: 38-48 weeks (9-12 months)**

> ⚠️ This is a SERIOUS engineering tool. Rushing phases = safety liability. Each phase
> must be signed off before the next begins.

---

## Phase 0: Research & Discovery
### Duration: 2-3 weeks
### Goal: Understand the market, users, competition, and define the product vision

#### Tasks:
- [ ] **0.1** Market Research
  - Survey existing fire alarm design tools (AutoSPRINK, AFDS, CadPipe, etc.)
  - Identify gaps and opportunities
  - Analyze competitor pricing and features
  - Interview 5-10 target users (fire protection engineers in Egypt/GCC)
- [ ] **0.2** User Research
  - Create user personas (Junior Engineer, Senior Consultant, Contractor, AHJ Reviewer)
  - Document current workflow pain points
  - Identify must-have vs nice-to-have features
- [ ] **0.3** Technical Feasibility
  - Evaluate CAD library options (OpenCAD, libredwg, Teigha, AutoCAD API)
  - Evaluate technology stack options
  - Estimate infrastructure costs
- [ ] **0.4** Regulatory Landscape
  - Confirm applicable standards by target market
  - Identify certification requirements (if any)
  - Document Civil Defense approval requirements

#### Deliverables:
| # | Deliverable | Format | Owner |
|---|------------|--------|-------|
| D0.1 | Market Analysis Report | PDF | Research |
| D0.2 | User Personas & Journey Maps | PDF | UX/PM |
| D0.3 | Competitor Feature Matrix | Spreadsheet | PM |
| D0.4 | Technical Feasibility Report | PDF | Tech Lead |
| D0.5 | Product Vision Statement | 1-pager | PM + Owner |

#### Success Criteria:
- ✅ Clear understanding of what users need (not what we think they need)
- ✅ Identified at least 3 competitive advantages
- ✅ Technology stack decisions informed by feasibility study
- ✅ Owner sign-off on product direction

---

## Phase 1: Requirements & Specifications
### Duration: 2 weeks
### Goal: Define exactly what the software will do — no ambiguity

#### Tasks:
- [ ] **1.1** Write Product Requirements Document (PRD)
  - Define all features with priority (P0/P1/P2)
  - Define user stories for each feature
  - Define non-functional requirements (performance, security, reliability)
- [ ] **1.2** Define Functional Specifications
  - Input: What does the user provide? (floor plans, building type, standard selection)
  - Processing: What does the system calculate? (spacing, coverage, voltage, battery)
  - Output: What does the system produce? (device layout, reports, CAD drawings, calculations)
- [ ] **1.3** Define Data Requirements
  - Catalog all data entities and their relationships
  - Define the product database schema (manufacturer, model, specs, certifications)
  - Define the standards database structure (rules, tables, formulas)
  - Define the project database structure (buildings, floors, zones, devices)
- [ ] **1.4** Define Integration Requirements
  - CAD software integration (AutoCAD, Revit)
  - BIM/IFC support
  - PDF report generation
  - Cloud sync / collaboration

#### Deliverables:
| # | Deliverable | Format |
|---|------------|--------|
| D1.1 | Product Requirements Document | Markdown/PDF |
| D1.2 | Functional Specifications Document | Markdown/PDF |
| D1.3 | Data Entity Relationship Diagram | ERD (draw.io) |
| D1.4 | Feature Priority Matrix (MoSCoW) | Spreadsheet |
| D1.5 | User Story List (Jira/Linear) | Project Tool |

#### Key User Stories (Examples):
```
US-001: As a fire protection engineer, I want to import a floor plan (DWG/PDF/image)
        so that I can design the fire alarm system on the actual building layout.

US-002: As a fire protection engineer, I want to select a standard (NFPA 72 / BS 5839)
        so that the system applies the correct spacing and rules.

US-003: As a fire protection engineer, I want the system to auto-place detectors
        according to code spacing rules so that I can ensure compliance.

US-004: As a fire protection engineer, I want the system to calculate voltage drop
        on every NAC circuit and alert me if it exceeds limits.

US-005: As a fire protection engineer, I want to generate a complete set of shop
        drawings (DWG) and calculation reports (PDF) for Civil Defense submission.
```

#### Success Criteria:
- ✅ Every feature has a clear user story and acceptance criteria
- ✅ Data model covers 100% of domain entities
- ✅ All stakeholders agree on scope and priorities
- ✅ No ambiguous requirements remain

---

## Phase 2: System Architecture & Database Design
### Duration: 3 weeks
### Goal: Design the technical foundation — the most critical phase

#### Tasks:
- [ ] **2.1** Choose Technology Stack
  ```
  RECOMMENDED (for maximum flexibility):
  ├── Backend:     Python (FastAPI) or Node.js (Express/NestJS)
  │                 Reason: FastAPI excellent for calculation-heavy apps
  ├── Database:    PostgreSQL (relational data) + Redis (caching)
  ├── Frontend:    React/Next.js (web) or Electron (desktop)
  │                 Reason: Large ecosystem, CAD canvas libraries (Fabric.js, Konva.js)
  ├── CAD Engine:  OpenSCAD / libredwg / ezdxf (Python) for DWG read/write
  ├── PDF Engine:  ReportLab (Python) or Puppeteer (Node) for report generation
  ├── Auth:        JWT + OAuth2
  └── Deploy:      Docker + AWS/Azure
  ```
- [ ] **2.2** Design Database Schema
  - **standards_db**: Code rules, spacing tables, formulas, correction factors
  - **devices_db**: Manufacturer products with full specifications
  - **projects_db**: User projects, buildings, floors, zones, devices
  - **users_db**: Authentication, roles, permissions
  - See detailed schema in `database-schema.sql`
- [ ] **2.3** Design API Architecture
  - RESTful API with OpenAPI specification
  - Key endpoints: /projects, /buildings, /floors, /zones, /devices, /calculations, /reports
  - WebSocket for real-time collaboration
- [ ] **2.4** Design Calculation Engine Architecture
  - Plugin-based: each calculation is an independent module
  - Rule engine: configurable per standard (NFPA/BS/EN)
  - Every calculation returns: result + code reference + confidence level
- [ ] **2.5** Set Up Development Environment
  - Git repository with branching strategy (GitFlow)
  - CI/CD pipeline (GitHub Actions / GitLab CI)
  - Docker compose for local development
  - Code quality tools (ESLint, Prettier, pytest/jest)

#### Deliverables:
| # | Deliverable | Format |
|---|------------|--------|
| D2.1 | Architecture Decision Record (ADR) | Markdown |
| D2.2 | System Architecture Diagram | Diagram (draw.io) |
| D2.3 | Database Schema (DDL) | SQL file |
| D2.4 | API Specification (OpenAPI) | YAML/JSON |
| D2.5 | Database Schema ERD | Diagram |
| D2.6 | Development Environment Setup Guide | Markdown |

#### Success Criteria:
- ✅ Database schema normalized to 3NF (minimum)
- ✅ API design covers all user stories
- ✅ Development environment reproducible (Docker)
- ✅ CI pipeline running on every commit
- ✅ Architecture review by senior engineer

---

## Phase 3: Core Calculation Engines
### Duration: 5-6 weeks
### Goal: Build the mathematical brain of the system — SAFETY-CRITICAL CODE

> ⚠️ This is the most important phase. Every calculation must be:
> 1. Unit-tested with 100% code coverage
> 2. Validated against known examples from code books
> 3. Traceable to specific code sections
> 4. Reviewed by a licensed fire protection engineer

#### Tasks:
- [ ] **3.1** Spacing & Coverage Engine
  - Point detector spacing calculation (grid layout algorithm)
  - Corridor spacing calculation
  - Beam detector spacing calculation
  - Ceiling height correction algorithm
  - Beam/sloped ceiling adjustment
  - Coverage verification (is every point within detector range?)
  - Wall distance validation
  - Standard: NFPA 72 + BS 5839 + EN 54

- [ ] **3.2** Voltage Drop Engine
  - DC voltage drop formula: Vdrop = (2 × I × R × L) / 1000
  - Wire resistance lookup table (18-12 AWG, copper)
  - Temperature derating (fire conditions: +20% resistance)
  - Voltage drop per segment (chain calculation)
  - NAC circuit voltage analysis
  - SLC circuit voltage analysis
  - Auto-wire-gauge recommendation

- [ ] **3.3** Battery Calculation Engine
  - Standby load calculation (24hr quiescent)
  - Alarm load calculation (5min or 15min)
  - Total Ah requirement with safety factor (1.2x)
  - Temperature derating
  - End-of-life derating (80% capacity)
  - Battery size recommendation (standard sizes)
  - Charging system sizing

- [ ] **3.4** Strobe/Candela Engine
  - Room candela calculation: 0.0375 × area
  - Minimum candela determination (15 cd min)
  - Maximum candela cap (110 wall / 177 ceiling)
  - Multi-device room calculation (when single device insufficient)
  - Spacing calculation from candela rating

- [ ] **3.5** Sound Level Engine
  - Point-to-point sound attenuation calculation
  - Room acoustic estimation
  - 65 dBA / 75 dBA compliance check
  - Speaker tap setting optimization
  - Overlap verification

- [ ] **3.6** NAC Loading Engine
  - Total circuit current summation
  - Per-circuit loading check against panel rating
  - Device count per circuit tracking

- [ ] **3.7** Zone Validation Engine
  - Zone area check (max 2000m² per BS 5839)
  - Search distance check (max 60m per BS 5839)
  - Device count per zone (max 20 conventional)
  - Floor-per-zone validation

#### Deliverables:
| # | Deliverable | Format |
|---|------------|--------|
| D3.1 | Spacing Engine + Unit Tests | Python/JS module |
| D3.2 | Voltage Drop Engine + Unit Tests | Python/JS module |
| D3.3 | Battery Calculator + Unit Tests | Python/JS module |
| D3.4 | Candela/Sound Engine + Unit Tests | Python/JS module |
| D3.5 | Validation Engine + Unit Tests | Python/JS module |
| D3.6 | Calculation Validation Report | PDF (against manual calculations) |

#### Testing Strategy:
```
For EVERY calculation module:
1. Unit tests: minimum 20 test cases per module
2. Edge cases: zero, negative, maximum, boundary values
3. Validation: calculate manually → compare with engine → must match within 0.01%
4. Code reference: every test annotated with code section number
5. Review: peer review by licensed fire protection engineer
```

#### Success Criteria:
- ✅ All calculation engines pass 100% of unit tests
- ✅ Manual calculation validation matches within 0.01%
- ✅ Every formula traceable to specific code section
- ✅ Code coverage ≥ 95% for all calculation modules
- ✅ No calculation takes > 500ms for a typical project

---

## Phase 4: Standards Engine & Rule System
### Duration: 3-4 weeks
### Goal: Build a configurable rules engine that can switch between NFPA/BS/EN/Egyptian

#### Tasks:
- [ ] **4.1** Design Rule Engine Architecture
  - Each rule = independent, testable, referenceable object
  - Rules organized by: standard → category → section
  - Rule format: {condition, action, reference, exceptions, priority}
- [ ] **4.2** Implement NFPA 72 Rules
  - Import data from `fire-alarm-db/standards/nfpa72-rules.json`
  - Detector spacing rules (smooth ceiling, corridor, high ceiling, beams, slopes)
  - Notification requirements (audible min, visible min, T-3 pattern)
  - Pull station rules (location, height, travel distance)
  - Zone rules (if applicable)
  - Circuit class rules (A/B/C/D/X)
- [ ] **4.3** Implement BS 5839 Rules
  - Import data from `fire-alarm-db/standards/bs5839-rules.json`
  - Risk category system (L1-L5, P1-P2, M)
  - Detector spacing (different from NFPA!)
  - Sounder spacing rules
  - Zone rules (2000m², 60m search, 20 device max)
- [ ] **4.4** Implement EN 54 Rules
  - Product certification validation
  - Device class compatibility
- [ ] **4.5** Implement Egyptian Code Rules
  - Local modifications to NFPA/BS
  - Civil Defense specific requirements
- [ ] **4.6** Rule Conflict Resolution
  - When NFPA and BS give different answers → flag to user
  - User selects which standard to follow
  - System shows the rule from each standard side-by-side

#### Deliverables:
| # | Deliverable | Format |
|---|------------|--------|
| D4.1 | Rule Engine Core | Code module |
| D4.2 | NFPA 72 Rule Set | JSON + Code |
| D4.3 | BS 5839 Rule Set | JSON + Code |
| D4.4 | Rule Engine Test Suite | Test code |
| D4.5 | Standard Comparison Matrix | Spreadsheet |

#### Success Criteria:
- ✅ System can switch between NFPA/BS with one setting
- ✅ Every rule traceable to specific code section
- ✅ Conflicting rules identified and presented to user
- ✅ Adding new rules requires NO code changes (data-driven)

---

## Phase 5: Floor Plan & Auto-Layout Engine
### Duration: 5-6 weeks
### Goal: Enable floor plan import and automatic device placement

#### Tasks:
- [ ] **5.1** Floor Plan Import
  - DWG/DXF import (via ezdxf / libredwg)
  - PDF/image import with scale calibration
  - Layer management (walls, doors, rooms, furniture)
  - Room detection algorithm (identify enclosed spaces)
  - Floor plan coordinate system setup

- [ ] **5.2** Building Model
  - Multi-floor project structure
  - Floor dimensions and properties
  - Room polygons (defined by walls)
  - Occupancy type per room/floor
  - Ceiling height per room/floor
  - Standard selection per project

- [ ] **5.3** Auto-Placement Engine
  - Grid-based detector placement algorithm
  - Obstacle avoidance (columns, ducts, beams)
  - Pull station placement (near exits, within travel distance)
  - Notification appliance placement (coverage circles)
  - Manual override (user can move any device)
  - Real-time spacing validation feedback

- [ ] **5.4** Interactive Canvas
  - Zoom, pan, select, drag devices
  - Visual spacing guides (coverage circles, grid)
  - Color-coded validation (green = OK, yellow = warning, red = violation)
  - Room labeling and zone assignment
  - Device properties panel (edit settings)

- [ ] **5.5** Wiring Routing
  - Auto-route wiring between devices and panel
  - Wire length calculation
  - Wire type and gauge recommendation
  - Circuit assignment (IDC, NAC, SLC)
  - Wire routing on floor plan (visual)

#### Deliverables:
| # | Deliverable | Format |
|---|------------|--------|
| D5.1 | Floor Plan Import Module | Code |
| D5.2 | Building Model Module | Code |
| D5.3 | Auto-Placement Engine | Code |
| D5.4 | Interactive Canvas Component | UI Component |
| D5.5 | Wiring Router | Code |

#### Success Criteria:
- ✅ DWG files import within 3 seconds (typical file)
- ✅ Auto-placement covers ≥ 95% of rooms correctly
- ✅ User can override any auto-placed device
- ✅ Real-time validation feedback < 200ms

---

## Phase 6: UI/UX Development
### Duration: 6-8 weeks
### Goal: Build the complete user interface

#### Tasks:
- [ ] **6.1** Project Management UI
  - Dashboard: list projects, recent, templates
  - Project creation wizard (building info, standard selection, occupancy)
  - Project settings and configuration

- [ ] **6.2** Design Workspace UI
  - Floor plan canvas (from Phase 5)
  - Device palette (drag-and-drop from catalog)
  - Properties panel (device settings, zone assignment)
  - Layers panel (toggle visibility of circuits, zones)
  - Toolbar (select, place, route, measure, validate)

- [ ] **6.3** Calculation Dashboard UI
  - Voltage drop summary per circuit
  - Battery calculation summary
  - NAC loading bar chart
  - Zone coverage summary
  - Device count per type/zone/floor

- [ ] **6.4** Validation & Compliance UI
  - Real-time validation overlay on floor plan
  - Compliance report card (pass/fail per code section)
  - Code reference links (click → see the exact rule)
  - Warnings and errors list with resolution suggestions

- [ ] **6.5** Reports & Export UI
  - Device schedule table (editable)
  - Calculation sheets (voltage drop, battery)
  - Zone map
  - One-click report generation (PDF)
  - DWG export

- [ ] **6.6** Settings & Preferences
  - Default standard selection (NFPA/BS)
  - Default units (metric/imperial)
  - Default manufacturer preference
  - User profile and company info (for report headers)

#### Deliverables:
| # | Deliverable | Format |
|---|------------|--------|
| D6.1 | UI Design System (colors, fonts, components) | Figma |
| D6.2 | Complete Frontend Application | Code |
| D6.3 | User Manual (draft) | Markdown |

#### Success Criteria:
- ✅ All user stories implemented and tested
- ✅ Page load time < 3 seconds
- ✅ Mobile responsive (at minimum: reports viewable on tablet)
- ✅ Accessibility compliance (WCAG 2.1 AA)

---

## Phase 7: Export, Reports & Integration
### Duration: 3-4 weeks
### Goal: Professional output for submission to authorities

#### Tasks:
- [ ] **7.1** DWG Export
  - Export complete fire alarm floor plan as DWG
  - Layers: devices, wiring, zones, dimensions, labels
  - Title block with project info
  - NFPA 170 symbols
  - Compatible with AutoCAD 2018+

- [ ] **7.2** PDF Report Generation
  - Cover page with project info and logo
  - Table of contents
  - Floor plans with device layout
  - Device schedule (all devices listed)
  - Zone map
  - Voltage drop calculations (per circuit)
  - Battery calculation
  - NAC loading summary
  - Sequence of operations (integration interfaces)
  - Standard compliance checklist
  - Engineer stamp area

- [ ] **7.3** Bill of Materials (BOM)
  - Complete equipment list with quantities
  - Wire lengths by type and gauge
  - Accessories (backboxes, bases, modules)
  - Export as Excel/CSV

- [ ] **7.4** Revit/BIM Integration (Phase 2 — if demand exists)
  - Export fire alarm devices as Revit families
  - Import Revit floor plans
  - IFC2x3/IFC4 support

#### Deliverables:
| # | Deliverable |
|---|------------|
| D7.1 | DWG Export Module |
| D7.2 | PDF Report Generator |
| D7.3 | BOM Generator |
| D7.4 | Sample Output Package (DWG + PDF + BOM) |

#### Success Criteria:
- ✅ DWG opens correctly in AutoCAD with all layers
- ✅ PDF report is Civil Defense submission-ready
- ✅ BOM matches device count on floor plan exactly

---

## Phase 8: Testing & Validation
### Duration: 4-5 weeks
### Goal: Ensure the system produces correct, safe, compliant designs

#### Tasks:
- [ ] **8.1** Unit Testing
  - All calculation engines: 100% code coverage
  - All rules: tested against code book examples
  - All data operations: CRUD tests

- [ ] **8.2** Integration Testing
  - Full design workflow: import → place → calculate → validate → export
  - Multi-floor project testing
  - Multi-standard project testing

- [ ] **8.3** Compliance Validation
  - Create 10+ test projects with known correct answers
  - Compare software output with manual calculations
  - Engage a licensed fire protection engineer for review
  - Validate against actual approved shop drawings

- [ ] **8.4** Performance Testing
  - Large project: 50-floor building → response time
  - Concurrent users: 100+ simultaneous → no degradation
  - Database: 10,000 projects → query performance

- [ ] **8.5** Security Testing
  - OWASP Top 10 vulnerability scan
  - Penetration testing
  - Data encryption verification

- [ ] **8.6** User Acceptance Testing (UAT)
  - 5+ beta testers from target market
  - Feedback collection and triage
  - Bug prioritization and resolution

#### Deliverables:
| # | Deliverable |
|---|------------|
| D8.1 | Test Coverage Report |
| D8.2 | Compliance Validation Report |
| D8.3 | Performance Test Results |
| D8.4 | Security Audit Report |
| D8.5 | UAT Feedback Summary |

#### Success Criteria:
- ✅ All critical and high bugs resolved
- ✅ No calculation errors in compliance validation
- ✅ Page response time < 3 seconds (95th percentile)
- ✅ Zero critical security vulnerabilities
- ✅ UAT satisfaction score ≥ 4/5

---

## Phase 9: Beta, Feedback & Polish
### Duration: 3-4 weeks
### Goal: Real-world testing and refinement

#### Tasks:
- [ ] **9.1** Closed Beta Program
  - Invite 10-20 engineers from Egypt/GCC
  - Provide training materials and support
  - Collect structured feedback weekly
- [ ] **9.2** Bug Fix Sprint
  - Fix all P0 and P1 bugs from beta
  - Address top user pain points
  - Performance optimization
- [ ] **9.3** UX Polish
  - Refine based on real usage patterns
  - Add keyboard shortcuts and productivity features
  - Improve error messages and validation feedback
- [ ] **9.4** Documentation
  - Complete user manual
  - Video tutorials (3-5 minutes each)
  - FAQ and troubleshooting guide
  - API documentation (if applicable)

#### Deliverables:
| # | Deliverable |
|---|------------|
| D9.1 | Beta Feedback Report |
| D9.2 | Bug Fix Log |
| D9.3 | User Manual (final) |
| D9.4 | Video Tutorial Series |

---

## Phase 10: Launch & Documentation
### Duration: 2-3 weeks
### Goal: Production deployment and market launch

#### Tasks:
- [ ] **10.1** Production Deployment
  - Cloud infrastructure setup (AWS/Azure)
  - Database migration and seeding
  - SSL/TLS certificates
  - DNS configuration
  - Monitoring and alerting (uptime, errors, performance)
  - Backup strategy (daily automated backups)

- [ ] **10.2** Pricing & Licensing
  - Define pricing tiers (Free trial, Professional, Enterprise)
  - Subscription model (monthly/annual)
  - License management system

- [ ] **10.3** Marketing & Launch
  - Landing page with feature demo
  - Social media presence (LinkedIn, YouTube)
  - Email campaign to target audience
  - Conference/meeting presence (IFSEC, Intersec)

- [ ] **10.4** Support Infrastructure
  - Help desk / ticketing system
  - Knowledge base articles
  - Community forum (optional)

#### Deliverables:
| # | Deliverable |
|---|------------|
| D10.1 | Production Deployment Checklist |
| D10.2 | Pricing & Terms of Service |
| D10.3 | Landing Page |
| D10.4 | Launch Announcement |

---

## ⚡ Critical Success Factors

| Factor | Why It Matters |
|--------|---------------|
| **Calculation Accuracy** | ONE wrong calculation = liability. Zero tolerance. |
| **Code Compliance** | Every rule must be traceable to specific code section |
| **Peer Review** | Licensed fire protection engineer must validate |
| **User Input** | Don't build in a vacuum — involve real engineers from Day 1 |
| **Iterative Development** | Build MVP first (Phase 3-5 core), expand later |
| **Test-Driven Development** | Write tests BEFORE code for calculation engines |
| **Documentation** | Every design decision documented and traceable |

---

## 🚨 Risk Register

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Calculation errors | Medium | CRITICAL | TDD + engineer validation + automated testing |
| Wrong code interpretation | Medium | HIGH | Multiple source validation, expert review |
| CAD library limitations | Medium | MEDIUM | Prototype early in Phase 0, have backup options |
| Scope creep | High | MEDIUM | Strict MoSCoW prioritization, change control |
| User adoption resistance | Medium | HIGH | Involve users early, provide training, free trial |
| Performance issues (large projects) | Medium | MEDIUM | Performance testing in Phase 8, optimize early |

---

## 📊 What We Already Have (Head Start)

| Asset | Status | Location |
|-------|--------|----------|
| Standards Database (NFPA 72) | ✅ Complete | `fire-alarm-db/standards/nfpa72-rules.json` |
| Standards Database (BS 5839) | ✅ Complete | `fire-alarm-db/standards/bs5839-rules.json` |
| Standards Database (EN 54) | ✅ Complete | `fire-alarm-db/standards/en54-product-specs.json` |
| Standards Database (Egyptian Code) | ✅ Complete | `fire-alarm-db/standards/egyptian-code.json` |
| Device Types Database | ✅ Complete | `fire-alarm-db/devices/` |
| Notification Appliances Database | ✅ Complete | `fire-alarm-db/devices/notification-appliances.json` |
| Coverage/Spacing Rules | ✅ Complete | `fire-alarm-db/rules/coverage-spacing.json` |
| Zone Mapping Rules | ✅ Complete | `fire-alarm-db/rules/zone-mapping.json` |
| Circuit Loading Rules | ✅ Complete | `fire-alarm-db/rules/circuit-loading.json` |
| Integration Interfaces | ✅ Complete | `fire-alarm-db/rules/integration-interfaces.json` |
| NFPA 170 Symbols | ✅ Complete | `fire-alarm-db/rules/nfpa170-symbols.json` |
| Voltage Drop/Battery Calculations | ✅ Complete | `fire-alarm-db/calculations/` |
| Building/Occupancy Classification | ✅ Complete | `fire-alarm-db/building-types/` |
| Brand Registry | ✅ Complete | `fire-alarm-db/manufacturers/` |
| Product Template | ✅ Complete | `fire-alarm-db/manufacturers/product-data-template.json` |
| **TOTAL: ~225 KB of structured domain knowledge** | ✅ | **19 files** |

**This means Phase 2 (Database Design) and Phase 4 (Standards Engine) have a massive head start.**
