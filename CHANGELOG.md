# Changelog

All notable changes to FireAI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- New NFPA 72-2022 compliance checks
- Enhanced acoustic modeling for notification appliances
- Real-time collaboration features for design teams
- Advanced 3D visualization engine

### Changed
- Improved performance for large building models
- Updated CAD parsing for newer file formats
- Enhanced error reporting and diagnostics

### Deprecated
- Legacy API endpoints (will be removed in v2.0)

### Removed
- Support for Python < 3.12

### Fixed
- Memory leak in geometry processing
- Race condition in concurrent analysis
- Incorrect coverage calculations for sloped ceilings

### Security
- Addressed potential injection in CAD file parsing
- Strengthened authentication for API endpoints

## [1.0.0] - 2026-06-11

### Added
- Initial release of FireAI Platform
- Core fire protection engineering engine
- NFPA 72 compliance checking
- AutoCAD and Revit integration
- Advanced detector placement algorithms
- Comprehensive audit trail system
- Multi-zone fire alarm system design
- Emergency voice communication planning
- Structural fire protection analysis
- Egress modeling and analysis

### Features
- **Automated Detector Placement**: Optimizes smoke and heat detector locations per NFPA 72
- **Compliance Verification**: Real-time checking against NFPA codes and local regulations
- **NAC Design**: Notification Appliance Circuit design with voltage drop calculations
- **Power Supply Allocation**: Automatic FACP and NAC power supply sizing
- **Integration Ready**: APIs for CAD software integration
- **Safety First**: Multiple validation layers and fail-safe mechanisms

### Safety Hardening
- V12 fixes for semantic substring collisions in detector identification
- V13 safety hardening for coverage verification
- V14 fixes for DC return path voltage drop calculations
- V19.1 RTI (Response Time Index) validation for shunt-trip systems
- V20.2 safety gate verification and proof validation

### Architecture
- Three-layer communication protocol (FACP)
- Distributed processing capability
- Pluggable compliance engine
- Extensible rule system
- Modular design for easy maintenance

### Performance
- Optimized spatial algorithms using Shapely/GEOS
- Parallel processing for large projects
- Efficient memory management
- Fast CAD file parsing

---

## Versioning

Major versions indicate significant architectural changes or safety hardening.
Minor versions add features and improvements.
Patch versions fix bugs and security issues.

## Safety Classification

- **Critical** - Safety-related fixes that prevent potential harm
- **High** - Important functionality improvements
- **Medium** - Feature enhancements
- **Low** - Minor improvements and documentation

---

**Note**: This changelog reflects the evolution of FireAI from its initial concept to a production-ready safety-critical system. All changes have undergone rigorous testing and safety validation.