# FireAI Data Flow Documentation

## Table of Contents
1. [Overview](#overview)
2. [Data Flow Architecture](#data-flow-architecture)
3. [Core Data Flows](#core-data-flows)
4. [ETAP Integration Data Flow](#etap-integration-data-flow)
5. [GIS Integration Data Flow](#gis-integration-data-flow)
6. [Safety Validation Data Flow](#safety-validation-data-flow)
7. [Study Execution Data Flow](#study-execution-data-flow)
8. [Data Transformation Pipelines](#data-transformation-pipelines)
9. [Data Storage and Persistence](#data-storage-and-persistence)
10. [Data Security and Privacy](#data-security-and-privacy)

## Overview

This document describes the comprehensive data flow architecture of the FireAI platform, detailing how data moves through the system, transformations that occur, and the various integration points with external systems like ETAP and GIS platforms. The data flow is designed with safety, security, and reliability as primary concerns.

### Purpose
The data flow documentation serves as a reference for:
- Developers implementing new features
- Architects designing system extensions
- Security teams reviewing data handling
- Operations teams monitoring system performance
- Compliance teams ensuring regulatory adherence

### Key Principles
- **Safety-First**: All data flows include safety validation checkpoints
- **Traceability**: Complete audit trail for all data transformations
- **Security**: End-to-end encryption and access controls
- **Reliability**: Resilient data flow with retry mechanisms
- **Performance**: Optimized data pathways for efficiency

## Data Flow Architecture

### Multi-Layer Data Flow Model

```
┌─────────────────────────────────────────────────────────────────────┐
│                          INPUT LAYER                                │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │   Web UI    │  │    API      │  │    CLI      │  │   Mobile    │ │
│  │             │  │             │  │             │  │             │ │
│  │   JSON      │  │   JSON      │  │   JSON      │  │   JSON      │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       VALIDATION LAYER                              │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                Safety Validation Pipeline                       ││
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      ││
│  │  │ Input    │  │ Schema   │  │ Risk     │  │ Access   │      ││
│  │  │ Check    │  │ Valid.   │  │ Assess.  │  │ Control  │      ││
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘      ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     ORCHESTRATION LAYER                             │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                   Study Manager                                 ││
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐             ││
│  │  │  Routing    │ │  Queue      │ │  Schedule   │             ││
│  │  │             │ │             │ │             │             ││
│  │  └─────────────┘ └─────────────┘ └─────────────┘             ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       PROCESSING LAYER                              │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐│
│  │   ETAP      │  │    GIS      │  │    ML       │  │   Database  ││
│  │ Integration │  │   Mapping   │  │  Engine     │  │   Access    ││
│  │             │  │             │  │             │  │             ││
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       OUTPUT LAYER                                  │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                   Result Assembly                               ││
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐││
│  │  │ Validation  │ │ Formatting  │ │ Serialization││ Compression│││
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       STORAGE LAYER                                 │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐│
│  │   Primary   │  │    Audit    │  │   Cache     │  │  Archive    ││
│  │   Storage   │  │   Log       │  │             │  │             ││
│  │             │  │             │  │             │  │             ││
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

## Core Data Flows

### 1. User Request Flow
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   User Input    │───▶│  Validation     │───▶│  Authentication │
│   (JSON/Params) │    │  Pipeline       │    │  & Authorization│
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                ┌──────▼──────┐         ┌─────▼─────┐
         │                │  Sanitization│         │  Session  │
         │                │    & Safety   │         │   Check   │
         │                │   Validation │         │           │
         │                └──────────────┘         └───────────┘
         └────────────────────────────────────────────────────────┘
                                │
                         ┌──────▼──────┐
                         │  Route      │
                         │  Selection  │
                         └─────────────┘
```

### 2. Study Configuration Flow
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Study Config   │───▶│  Schema       │───▶│  Business Logic │
│  (User Input)   │    │  Validation   │    │  Validation     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                ┌──────▼──────┐         ┌─────▼─────┐
         │                │  Safety     │         │  Risk     │
         │                │  Assessment │         │  Analysis │
         │                └─────────────┘         └───────────┘
         └────────────────────────────────────────────────────────┘
                                │
                         ┌──────▼──────┐
                         │  Configuration│
                         │  Assembly   │
                         └─────────────┘
```

### 3. Data Processing Flow
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Raw Data       │───▶│  Preprocessing │───▶│  Transformation │
│  (ETAP/GIS/ML)  │    │  Pipeline      │    │  Engine         │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                ┌──────▼──────┐         ┌─────▼─────┐
         │                │  Validation │         │  Security │
         │                │  & Quality  │         │  Check    │
         │                │  Assurance  │         │           │
         │                └─────────────┘         └───────────┘
         └────────────────────────────────────────────────────────┘
                                │
                         ┌──────▼──────┐
                         │  Processed   │
                         │  Data Store  │
                         └─────────────┘
```

## ETAP Integration Data Flow

### ETAP Request Flow
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Study Request  │───▶│  ETAP-Specific  │───▶│  Safety        │
│  (Electrical    │    │  Validation     │    │  Validation    │
│  Analysis)      │    │                 │    │                │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                ┌──────▼──────┐         ┌─────▼─────┐
         │                │  Data       │         │  Access   │
         │                │  Formatting │         │  Control  │
         │                │             │         │           │
         │                └─────────────┘         └───────────┘
         └────────────────────────────────────────────────────────┘
                                │
                         ┌──────▼──────┐
                         │  ETAP API   │
                         │  Call       │
                         └─────────────┘
                                │
                         ┌──────▼──────┐
                         │  Response   │
                         │  Processing │
                         └─────────────┘
```

### ETAP Response Flow
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  ETAP Response  │───▶│  Data Parsing  │───▶│  Validation    │
│  (Raw Format)   │    │  & Structure   │    │  & Cleanup     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                ┌──────▼──────┐         ┌─────▼─────┐
         │                │  Safety     │         │  Format   │
         │                │  Verification│         │  Standard│
         │                │             │         │  Conversion│
         │                └─────────────┘         └───────────┘
         └────────────────────────────────────────────────────────┘
                                │
                         ┌──────▼──────┐
                         │  Internal   │
                         │  Data Model │
                         └─────────────┘
```

## GIS Integration Data Flow

### GIS Data Flow
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Location Data  │───▶│  Geospatial   │───▶│  Coordinate    │
│  (Coordinates,  │    │  Validation   │    │  Transformation│
│  Maps, Etc.)    │    │               │    │               │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                ┌──────▼──────┐         ┌─────▼─────┐
         │                │  Projection │         │  Spatial  │
         │                │  Validation │         │  Indexing │
         │                │             │         │           │
         │                └─────────────┘         └───────────┘
         └────────────────────────────────────────────────────────┘
                                │
                         ┌──────▼──────┐
                         │  GIS API    │
                         │  Integration│
                         └─────────────┘
                                │
                         ┌──────▼──────┐
                         │  Visualization│
                         │  Pipeline   │
                         └─────────────┘
```

## Safety Validation Data Flow

### Multi-Level Safety Validation
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Initial Data   │───▶│  Input Safety  │───▶│  Business Rule │
│  (Raw Request)  │    │  Check         │    │  Validation    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                ┌──────▼──────┐         ┌─────▼─────┐
         │                │  Risk       │         │  Compliance│
         │                │  Assessment │         │  Check     │
         │                │             │         │           │
         │                └─────────────┘         └───────────┘
         └────────────────────────────────────────────────────────┘
                                │
                         ┌──────▼──────┐
                         │  Safety     │
                         │  Gate       │
                         └─────────────┘
                                │ Yes/No
                         ┌──────▼──────┐
                         │  Proceed or │
                         │  Reject     │
                         └─────────────┘
```

### Safety Validation Stages
1. **Input Validation**: Checks for malformed data, injection attempts
2. **Schema Validation**: Ensures data conforms to expected structure
3. **Business Logic**: Validates against business rules and constraints
4. **Risk Assessment**: Evaluates potential impact and risk level
5. **Compliance Check**: Ensures adherence to regulatory requirements
6. **Access Control**: Verifies permissions and authorization

## Study Execution Data Flow

### Complete Study Execution Flow
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Study Request  │───▶│  Pre-execution │───▶│  Resource      │
│  (User Initiated)│    │  Validation    │    │  Allocation    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                ┌──────▼──────┐         ┌─────▼─────┐
         │                │  Queue      │         │  Execution│
         │                │  Management │         │  Planning │
         │                │             │         │           │
         │                └─────────────┘         └───────────┘
         └────────────────────────────────────────────────────────┘
                                │
                         ┌──────▼──────┐
                         │  Execution  │
                         │  Pipeline   │
                         └─────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   ETAP        │    │    GIS        │    │    ML         │
│   Processing  │    │   Processing  │    │   Processing  │
│               │    │               │    │               │
└───────────────┘    └───────────────┘    └───────────────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                ▼
                         ┌───────────────┐
                         │  Post-process │
                         │  Validation   │
                         └───────────────┘
                                │
                         ┌──────▼──────┐
                         │  Result     │
                         │  Assembly   │
                         └─────────────┘
```

## Data Transformation Pipelines

### Data Transformation Architecture
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Source Data    │───▶│  Parser &      │───▶│  Transformer   │
│  (Various      │    │  Validator     │    │  Pipeline      │
│  Formats)      │    │               │    │               │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                ┌──────▼──────┐         ┌─────▼─────┐
         │                │  Enrichment │         │  Quality  │
         │                │  Pipeline   │         │  Assurance│
         │                │             │         │           │
         │                └─────────────┘         └───────────┘
         └────────────────────────────────────────────────────────┘
                                │
                         ┌──────▼──────┐
                         │  Target     │
                         │  Format     │
                         └─────────────┘
```

### Transformation Types
- **Format Conversion**: Converting between different data formats (JSON, XML, CSV)
- **Schema Mapping**: Translating between different data schemas
- **Data Enrichment**: Adding metadata and contextual information
- **Aggregation**: Combining multiple data sources into unified views
- **Normalization**: Standardizing data representations
- **Encryption**: Securing sensitive data during transit/storage

## Data Storage and Persistence

### Storage Architecture Flow
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Processed Data │───▶│  Storage       │───▶│  Primary DB    │
│  (Ready for    │    │  Classification│    │  (PostgreSQL)  │
│  Storage)      │    │               │    │               │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                ┌──────▼──────┐         ┌─────▼─────┐
         │                │  Cache      │         │  Archive  │
         │                │  Layer      │         │  Storage  │
         │                │             │         │  (Cold)   │
         │                └─────────────┘         └───────────┘
         └────────────────────────────────────────────────────────┘
                                │
                         ┌──────▼──────┐
                         │  Backup &   │
                         │  Recovery   │
                         └─────────────┘
```

### Storage Categories
- **Hot Storage**: Frequently accessed operational data
- **Warm Storage**: Less frequently accessed but active data
- **Cold Storage**: Archived data for compliance/regulatory purposes
- **Cache Storage**: Temporary storage for performance optimization
- **Backup Storage**: Disaster recovery and backup systems

## Data Security and Privacy

### Security Data Flow
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Data Ingress   │───▶│  Encryption    │───▶│  Access        │
│  (Incoming)     │    │  Pipeline      │    │  Control       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                ┌──────▼──────┐         ┌─────▼─────┐
         │                │  Audit      │         │  Security  │
         │                │  Logging    │         │  Validation│
         │                │             │         │           │
         │                └─────────────┘         └───────────┘
         └────────────────────────────────────────────────────────┘
                                │
                         ┌──────▼──────┐
                         │  Data Egress│
                         │  Controls   │
                         └─────────────┘
```

### Privacy Protection Measures
- **Data Minimization**: Collecting only necessary data
- **Anonymization**: Removing personally identifiable information
- **Pseudonymization**: Replacing identifying data with artificial identifiers
- **Consent Management**: Tracking and managing user consent
- **Right to Deletion**: Supporting data deletion requests
- **Breach Notification**: Automated breach detection and notification

---

*This document represents the current data flow architecture as of the last update. All changes to the data flow should be reflected in this document to maintain accuracy.*