-- ============================================================================
-- Fire Alarm AI Design System - PostgreSQL Schema Extension
-- ============================================================================
-- New tables for AI-powered fire alarm design workflow
-- Compatible with PostgreSQL
-- ============================================================================

-- ============================================================================
-- Table: DesignProject
-- ============================================================================
CREATE TABLE DesignProject (
    ProjectID SERIAL PRIMARY KEY,
    ProjectName VARCHAR(255) NOT NULL,
    ClientName VARCHAR(255),
    Location VARCHAR(500),
    BuildingType VARCHAR(100),
    TotalArea DECIMAL(12,2),
    TotalFloors INTEGER,
    EngineerID INTEGER REFERENCES Users(UserID),
    Status VARCHAR(20) DEFAULT 'Draft' CHECK (Status IN ('Draft','InProgress','Reviewed','Approved','Rejected')),
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UpdatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_design_project_status ON DesignProject(Status);
CREATE INDEX idx_design_project_engineer ON DesignProject(EngineerID);

-- ============================================================================
-- Table: DesignStandard
-- ============================================================================
CREATE TABLE DesignStandard (
    StandardID SERIAL PRIMARY KEY,
    StandardName VARCHAR(100) NOT NULL,
    ParameterKey VARCHAR(100) NOT NULL,
    ParameterValue TEXT NOT NULL,
    Description VARCHAR(500),
    UNIQUE(StandardName, ParameterKey)
);

CREATE INDEX idx_design_standard_name ON DesignStandard(StandardName);

-- ============================================================================
-- Table: Room
-- ============================================================================
CREATE TABLE Room (
    RoomID SERIAL PRIMARY KEY,
    DesignProjectID INTEGER NOT NULL REFERENCES DesignProject(ProjectID) ON DELETE CASCADE,
    RoomName VARCHAR(255) NOT NULL,
    RoomType VARCHAR(100),
    Length DECIMAL(8,2),
    Width DECIMAL(8,2),
    Height DECIMAL(6,2),
    Area DECIMAL(10,2),
    OccupancyLoad INTEGER,
    FloorNumber INTEGER,
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_room_project ON Room(DesignProjectID);
CREATE INDEX idx_room_floor ON Room(DesignProjectID, FloorNumber);

-- ============================================================================
-- Table: DesignSession
-- ============================================================================
CREATE TABLE DesignSession (
    SessionID SERIAL PRIMARY KEY,
    DesignProjectID INTEGER NOT NULL REFERENCES DesignProject(ProjectID) ON DELETE CASCADE,
    AI_Version VARCHAR(50),
    InputType VARCHAR(20) CHECK (InputType IN ('Image','Manual','Hybrid')),
    ConfidenceScore DECIMAL(5,4),
    GeneratedBy INTEGER REFERENCES Users(UserID),
    GeneratedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    Notes TEXT
);

CREATE INDEX idx_design_session_project ON DesignSession(DesignProjectID);
CREATE INDEX idx_design_session_generated_by ON DesignSession(GeneratedBy);

-- ============================================================================
-- Table: AIDesignDevice
-- ============================================================================
CREATE TABLE AIDesignDevice (
    DesignDeviceID SERIAL PRIMARY KEY,
    SessionID INTEGER NOT NULL REFERENCES DesignSession(SessionID) ON DELETE CASCADE,
    RoomID INTEGER REFERENCES Room(RoomID),
    ProposedType VARCHAR(50) NOT NULL,
    X DECIMAL(10,4),
    Y DECIMAL(10,4),
    Z DECIMAL(10,4),
    Confidence DECIMAL(5,4),
    AI_Justification TEXT,
    IsApproved BOOLEAN DEFAULT FALSE,
    ApprovedBy INTEGER REFERENCES Users(UserID),
    ApprovedAt TIMESTAMP,
    RevisedX DECIMAL(10,4),
    RevisedY DECIMAL(10,4),
    RevisedZ DECIMAL(10,4),
    RevisionNote TEXT,
    DeviceID_Ref BIGINT REFERENCES Device(DeviceID),
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UpdatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_design_device_session ON AIDesignDevice(SessionID);
CREATE INDEX idx_ai_design_device_room ON AIDesignDevice(RoomID);
CREATE INDEX idx_ai_design_device_approved ON AIDesignDevice(IsApproved);
CREATE INDEX idx_ai_design_device_device_ref ON AIDesignDevice(DeviceID_Ref);

-- ============================================================================
-- Table: DesignFile
-- ============================================================================
CREATE TABLE DesignFile (
    FileID SERIAL PRIMARY KEY,
    SessionID INTEGER REFERENCES DesignSession(SessionID) ON DELETE CASCADE,
    ProjectID INTEGER REFERENCES DesignProject(ProjectID),
    FileName VARCHAR(255) NOT NULL,
    FileType VARCHAR(20) CHECK (FileType IN ('DWG','RVT','PDF','JSON','Excel')),
    FileContent BYTEA,
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_design_file_session ON DesignFile(SessionID);
CREATE INDEX idx_design_file_project ON DesignFile(ProjectID);

-- ============================================================================
-- Table: RevisionHistory
-- ============================================================================
CREATE TABLE RevisionHistory (
    RevisionID SERIAL PRIMARY KEY,
    DesignDeviceID INTEGER NOT NULL REFERENCES AIDesignDevice(DesignDeviceID) ON DELETE CASCADE,
    RevisedBy INTEGER REFERENCES Users(UserID),
    RevisionTimestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    OldValues JSONB,
    NewValues JSONB,
    Note TEXT
);

CREATE INDEX idx_revision_history_device ON RevisionHistory(DesignDeviceID);
CREATE INDEX idx_revision_history_timestamp ON RevisionHistory(RevisionTimestamp);

-- ============================================================================
-- Insert Default Design Standards
-- ============================================================================
INSERT INTO DesignStandard (StandardName, ParameterKey, ParameterValue, Description) VALUES
-- Egyptian Standards
('Egyptian', 'detector_spacing', '6.5', 'Maximum spacing between smoke detectors in meters'),
('Egyptian', 'max_detector_height', '9', 'Maximum ceiling height for standard detector placement'),
('Egyptian', 'min_audible_db', '85', 'Minimum audible notification level in dB'),
('Egyptian', 'manual_station_distance', '23', 'Maximum travel distance to manual station in meters'),

-- NFPA 72 Standards
('NFPA72', 'detector_spacing', '6.5', 'Standard detector spacing per NFPA 72'),
('NFPA72', 'max_detector_height', '9', 'Maximum mounting height'),
('NFPA72', 'min_audible_db', '85', 'Minimum sound level'),
('NFPA72', 'detector_per_zone', '50', 'Maximum devices per zone'),

-- Saudi Standards
('Saudi', 'detector_spacing', '6.0', 'Maximum detector spacing'),
('Saudi', 'max_detector_height', '8', 'Maximum ceiling height'),
('Saudi', 'civil_defense_required', 'true', 'Civil Defense connection required'),

-- Kuwait Standards
('Kuwait', 'detector_spacing', '6.5', 'Standard detector spacing'),
('Kuwait', 'monitoring_required', 'true', 'Central station monitoring required'),

-- Qatar Standards
('Qatar', 'detector_spacing', '6.5', 'Standard detector spacing'),
('Qatar', 'voice_evacuation', 'true', 'Voice evacuation required for high-rise');

-- ============================================================================
-- Insert Sample Device Types for AI
-- ============================================================================
INSERT INTO DeviceType (TypeName, Description) VALUES
('AIDetector', 'AI Proposed Smoke Detector'),
('AIHeatDetector', 'AI Proposed Heat Detector'),
('AIManualStation', 'AI Proposed Manual Call Point'),
('AINotification', 'AI Proposed Notification Appliance'),
('AISpeaker', 'AI Proposed Speaker');

-- ============================================================================
-- Create Sequence for Device ID (if not using identity)
-- ============================================================================
-- CREATE SEQUENCE IF NOT EXISTS device_id_seq START WITH 100000;

-- ============================================================================
-- End of Schema
-- ============================================================================
