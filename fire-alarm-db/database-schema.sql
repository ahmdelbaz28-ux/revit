-- ============================================================================
-- FIRE ALARM DESIGN SYSTEM — DATABASE SCHEMA (PostgreSQL)
-- ============================================================================
-- Version: 1.0 | Date: 2026-05-09
-- Engine: PostgreSQL 15+
-- Charset: UTF-8
-- Description: Complete database schema for fire alarm design software
-- ============================================================================

-- ============================================================================
-- EXTENSIONS
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search / fuzzy matching

-- ============================================================================
-- ENUMS (Shared across tables)
-- ============================================================================
CREATE TYPE standard_enum AS ENUM ('NFPA72', 'BS5839', 'EN54', 'EGYPTIAN', 'ISO7240', 'IBC');
CREATE TYPE unit_system AS ENUM ('METRIC', 'IMPERIAL');
CREATE TYPE occupancy_group AS ENUM ('A', 'B', 'C', 'E', 'F', 'H', 'I', 'M', 'R', 'S', 'U');
CREATE TYPE risk_category AS ENUM ('L1', 'L2', 'L3', 'L4', 'L5', 'P1', 'P2', 'M');
CREATE TYPE device_category AS ENUM ('DETECTOR', 'NOTIFICATION', 'INITIATING', 'MODULE', 'PANEL', 'ACCESSORY', 'SPEAKER');
CREATE TYPE detector_type AS ENUM (
    'SMOKE_PHOTOELECTRIC', 'SMOKE_IONIZATION', 'SMOKE_BEAM', 'SMOKE_ASPRATING',
    'HEAT_FIXED', 'HEAT_RATE_OF_RISE', 'HEAT_COMBINED',
    'MULTI_CRITERIA', 'FLAME_IR', 'FLAME_UV', 'FLAME_UVIR', 'FLAME_VIDEO',
    'GAS_CO', 'GAS_COMBUSTIBLE', 'DUCT_SMOKE'
);
CREATE TYPE notification_type AS ENUM (
    'HORN', 'STROBE', 'HORN_STROBE', 'SPEAKER', 'SPEAKER_STROBE',
    'BELL', 'SOUNDER_OUTDOOR', 'STROBE_OUTDOOR'
);
CREATE TYPE module_type AS ENUM ('MONITOR_INPUT', 'CONTROL_RELAY', 'IO_DUAL', 'ISOLATOR', 'SIGNAL_TRACER');
CREATE TYPE panel_type AS ENUM ('CONVENTIONAL', 'ADDRESSABLE', 'INTELLIGENT_ANALOG', 'NETWORKED', 'VOICE_EVACUATION', 'WIRELESS_BASE');
CREATE TYPE circuit_class AS ENUM ('A', 'B', 'C', 'D', 'X', 'E');
CREATE TYPE wire_gauge AS ENUM ('18AWG', '16AWG', '14AWG', '12AWG', '10AWG', '22AWG', '20AWG');
CREATE TYPE project_status AS ENUM ('DRAFT', 'IN_PROGRESS', 'REVIEW', 'APPROVED', 'REVISION', 'ARCHIVED');

-- ============================================================================
-- TABLE: users
-- ============================================================================
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    company_name    VARCHAR(255),
    license_number  VARCHAR(100),             -- Engineering license
    role            VARCHAR(50) DEFAULT 'engineer',  -- admin, engineer, viewer
    default_standard standard_enum DEFAULT 'NFPA72',
    default_units   unit_system DEFAULT 'METRIC',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);

-- ============================================================================
-- TABLE: standards (code rules stored as data, not code)
-- ============================================================================
CREATE TABLE standards (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code            standard_enum NOT NULL,
    edition         VARCHAR(50) NOT NULL,          -- e.g., '2025', '2017+A1:2020'
    title           TEXT NOT NULL,
    publisher       VARCHAR(255) NOT NULL,
    country         VARCHAR(100),
    scope           TEXT,
    is_active       BOOLEAN DEFAULT TRUE
);

-- ============================================================================
-- TABLE: spacing_rules (core spacing data per standard)
-- ============================================================================
CREATE TABLE spacing_rules (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    standard        standard_enum NOT NULL,
    device_type     detector_type NOT NULL,
    ceiling_type    VARCHAR(50) DEFAULT 'SMOOTH',   -- SMOOTH, BEAMED, SLOPED, CORRIDOR
    nominal_spacing_m    DECIMAL(6,2),               -- meters
    nominal_spacing_ft   DECIMAL(6,2),               -- feet
    max_wall_distance_m  DECIMAL(6,2),
    max_wall_distance_ft DECIMAL(6,2),
    max_ceiling_height_m  DECIMAL(6,2),
    max_ceiling_height_ft DECIMAL(6,2),
    corridor_width_max_m  DECIMAL(6,2),
    corridor_spacing_bonus BOOLEAN DEFAULT FALSE,     -- BS 5839 corridor bonus
    beam_depth_percent   VARCHAR(50),                -- e.g., '<10%', '10-20%', '>20%'
    slope_range          VARCHAR(50),                -- e.g., '<20deg', '20-30deg'
    notes              TEXT,
    source_section      VARCHAR(50),                 -- e.g., '17.6.3.1', '22.3'
    UNIQUE(standard, device_type, ceiling_type)
);

-- ============================================================================
-- TABLE: ceiling_height_corrections
-- ============================================================================
CREATE TABLE ceiling_height_corrections (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    standard        standard_enum NOT NULL,
    device_type     detector_type NOT NULL,
    height_min_m    DECIMAL(6,2),
    height_max_m    DECIMAL(6,2),
    height_min_ft   DECIMAL(6,2),
    height_max_ft   DECIMAL(6,2),
    spacing_modifier DECIMAL(4,2) NOT NULL,           -- multiplier (e.g., 0.80)
    notes           TEXT,
    UNIQUE(standard, device_type, height_min_m)
);

-- ============================================================================
-- TABLE: manufacturers
-- ============================================================================
CREATE TABLE manufacturers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(255) NOT NULL,
    country         VARCHAR(100),
    website         VARCHAR(500),
    tier            INTEGER DEFAULT 2,                 -- 1=global, 2=regional, 3=budget
    is_active       BOOLEAN DEFAULT TRUE,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- TABLE: products (device catalog)
-- ============================================================================
CREATE TABLE products (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    manufacturer_id UUID REFERENCES manufacturers(id),
    category        device_category NOT NULL,
    subcategory     VARCHAR(100),                      -- e.g., detector_type, notification_type
    model_number    VARCHAR(100) NOT NULL,
    product_name    VARCHAR(255) NOT NULL,
    description     TEXT,

    -- Certification
    en54_parts      TEXT[],                            -- e.g., {'EN 54-7', 'EN 54-5'}
    en54_class      VARCHAR(50),                       -- e.g., 'A2', 'A1R'
    ul_standards    TEXT[],                            -- e.g., {'UL 268', 'UL 864'}
    ce_marked       BOOLEAN DEFAULT FALSE,
    other_certs     TEXT[],

    -- Electrical
    voltage_min     DECIMAL(6,2),                      -- VDC
    voltage_max     DECIMAL(6,2),
    standby_current_mA DECIMAL(6,3),
    alarm_current_mA   DECIMAL(6,3),

    -- Detection specific
    sensitivity     TEXT,                              -- e.g., '0.12-0.25 dB/m'
    heat_rating_C   INTEGER,                           -- For heat detectors
    heat_rating_F   INTEGER,

    -- Notification specific
    output_dBA_low  DECIMAL(5,1),
    output_dBA_high DECIMAL(5,1),
    candela_options DECIMAL(6,1)[],                    -- Array of candela ratings
    speaker_taps_W  DECIMAL(5,2)[],                    -- Array of power taps

    -- Addressing
    is_addressable  BOOLEAN DEFAULT FALSE,
    protocol        VARCHAR(100),                      -- e.g., 'FlashScan', 'XP95', 'ESP'
    address_min     INTEGER,
    address_max     INTEGER,

    -- Physical
    ip_rating       VARCHAR(20),                       -- e.g., 'IP42'
    color           VARCHAR(50),                       -- e.g., 'White RAL 9003'
    dimensions_mm   JSONB,                             -- {width, height, depth}
    weight_g        DECIMAL(8,1),

    -- Coverage
    nominal_spacing_ft DECIMAL(6,2),
    nominal_spacing_m  DECIMAL(6,2),
    max_ceiling_ft      DECIMAL(6,2),
    max_ceiling_m       DECIMAL(6,2),

    -- Metadata
    cad_block       VARCHAR(100),
    datasheet_url   VARCHAR(500),
    notes           TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(manufacturer_id, model_number)
);
CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_products_subcategory ON products(subcategory);
CREATE INDEX idx_products_manufacturer ON products(manufacturer_id);
CREATE INDEX idx_products_search ON products USING gin(product_name gin_trgm_ops, model_number gin_trgm_ops);

-- ============================================================================
-- TABLE: product_current_data (detailed current draw per setting)
-- ============================================================================
CREATE TABLE product_current_data (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id      UUID REFERENCES products(id) ON DELETE CASCADE,
    setting_name    VARCHAR(50) NOT NULL,              -- e.g., 'Low', 'Medium', 'High', '15cd', '30cd'
    current_mA      DECIMAL(6,3) NOT NULL,
    notes           VARCHAR(255),
    UNIQUE(product_id, setting_name)
);

-- ============================================================================
-- TABLE: wire_resistance (copper wire reference)
-- ============================================================================
CREATE TABLE wire_resistance (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    awg             wire_gauge PRIMARY KEY,
    area_mm2        DECIMAL(5,2),
    diameter_mm     DECIMAL(5,3),
    resistance_ohm_per_kft DECIMAL(8,3) NOT NULL,    -- at 20°C
    resistance_ohm_per_km  DECIMAL(8,3) NOT NULL,
    typical_use     TEXT,
    notes           TEXT
);

-- ============================================================================
-- TABLE: projects
-- ============================================================================
CREATE TABLE projects (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id),
    project_name    VARCHAR(255) NOT NULL,
    project_number  VARCHAR(100),
    client_name     VARCHAR(255),
    location        TEXT,
    country         VARCHAR(100) DEFAULT 'Egypt',
    standard        standard_enum DEFAULT 'NFPA72',
    units           unit_system DEFAULT 'METRIC',
    status          project_status DEFAULT 'DRAFT',
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- TABLE: buildings (a project can have multiple buildings — campus)
-- ============================================================================
CREATE TABLE buildings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id      UUID REFERENCES projects(id) ON DELETE CASCADE,
    building_name   VARCHAR(255) NOT NULL,
    building_type   occupancy_group,
    risk_category   risk_category,
    number_of_floors INTEGER DEFAULT 1,
    height_above_grade_m DECIMAL(6,2),
    height_above_grade_ft DECIMAL(6,2),
    is_highrise     BOOLEAN DEFAULT FALSE,            -- > 75 ft / 23m
    has_sprinkler   BOOLEAN DEFAULT FALSE,
    voice_evac_required BOOLEAN DEFAULT FALSE,
    address         TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- TABLE: floors
-- ============================================================================
CREATE TABLE floors (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    building_id     UUID REFERENCES buildings(id) ON DELETE CASCADE,
    floor_number    INTEGER NOT NULL,                  -- -2, -1, 0, 1, 2...
    floor_name      VARCHAR(100),                      -- e.g., 'Ground Floor', 'Roof'
    ceiling_height_m  DECIMAL(6,2),
    ceiling_height_ft DECIMAL(6,2),
    ceiling_type    VARCHAR(50) DEFAULT 'SMOOTH',      -- SMOOTH, BEAMED, SLOPED, COMPOSITE
    beam_depth_m    DECIMAL(6,2),                      -- If beamed
    beam_depth_percent DECIMAL(5,2),
    slope_degrees   DECIMAL(5,2),                      -- If sloped
    floor_area_m2   DECIMAL(10,2),
    floor_area_sqft DECIMAL(10,2),
    occupancy_type  occupancy_group,
    notes           TEXT,
    UNIQUE(building_id, floor_number)
);

-- ============================================================================
-- TABLE: rooms (optional — for detailed room-level design)
-- ============================================================================
CREATE TABLE rooms (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    floor_id        UUID REFERENCES floors(id) ON DELETE CASCADE,
    room_name       VARCHAR(255),
    room_number     VARCHAR(50),
    room_type       VARCHAR(100),                      -- e.g., 'office', 'corridor', 'stairwell', 'lobby'
    occupancy_type  occupancy_group,
    area_m2         DECIMAL(10,2),
    area_sqft       DECIMAL(10,2),
    width_m         DECIMAL(6,2),
    length_m        DECIMAL(6,2),
    ceiling_height_m DECIMAL(6,2),
    is_corridor     BOOLEAN DEFAULT FALSE,
    corridor_width_m DECIMAL(6,2),
    polygon         JSONB,                              -- Room boundary polygon [{x, y}, ...]
    notes           TEXT
);

-- ============================================================================
-- TABLE: zones
-- ============================================================================
CREATE TABLE zones (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    floor_id        UUID REFERENCES floors(id) ON DELETE CASCADE,
    zone_number     INTEGER NOT NULL,
    zone_label      VARCHAR(255) NOT NULL,             -- e.g., 'Ground Floor — Lobby'
    zone_type       VARCHAR(50) DEFAULT 'DETECTION',   -- DETECTION, STAIRWELL, SHAFT, PLANT, OUTDOOR
    notes           TEXT,
    UNIQUE(floor_id, zone_number)
);

-- ============================================================================
-- TABLE: devices (placed devices on a floor plan)
-- ============================================================================
CREATE TABLE devices (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    zone_id         UUID REFERENCES zones(id),
    floor_id        UUID REFERENCES floors(id) ON DELETE CASCADE,
    room_id         UUID REFERENCES rooms(id) ON DELETE SET NULL,
    product_id      UUID REFERENCES products(id),

    -- Device info
    device_category device_category NOT NULL,
    device_type     VARCHAR(100) NOT NULL,              -- detector_type, notification_type, module_type etc.
    device_tag      VARCHAR(50),                        -- e.g., 'SD-001', 'HS-001', 'PS-001'

    -- Location on floor plan
    position_x      DECIMAL(10,4),                      -- Coordinate on plan (mm or inches)
    position_y      DECIMAL(10,4),
    mounting_type   VARCHAR(20) DEFAULT 'CEILING',      -- CEILING, WALL, DUCT, SURFACE, FLUSH

    -- Addressable info
    is_addressable  BOOLEAN DEFAULT FALSE,
    device_address  INTEGER,
    slc_loop_id     INTEGER,                            -- Which SLC loop

    -- Circuit assignment
    circuit_id      VARCHAR(50),                        -- e.g., 'NAC-1', 'SLC-1', 'IDC-Z03'
    circuit_class   circuit_class DEFAULT 'B',

    -- Settings
    setting_value   VARCHAR(50),                        -- e.g., 'High', '95cd', '1/2W'
    sensitivity     VARCHAR(50),                        -- e.g., 'High', 'Medium', 'Low'
    is_disabled     BOOLEAN DEFAULT FALSE,
    is_isolated     BOOLEAN DEFAULT FALSE,

    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_devices_zone ON devices(zone_id);
CREATE INDEX idx_devices_floor ON devices(floor_id);
CREATE INDEX idx_devices_circuit ON devices(circuit_id);
CREATE INDEX idx_devices_category ON devices(device_category);
CREATE INDEX idx_devices_type ON devices(device_type);

-- ============================================================================
-- TABLE: circuits (NAC, IDC, SLC)
-- ============================================================================
CREATE TABLE circuits (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    floor_id        UUID REFERENCES floors(id) ON DELETE CASCADE,
    circuit_label   VARCHAR(50) NOT NULL,               -- e.g., 'NAC-1', 'SLC-1', 'IDC-Z03'
    circuit_type    VARCHAR(20) NOT NULL,               -- NAC, IDC, SLC, SPEAKER
    circuit_class   circuit_class DEFAULT 'B',
    panel_id        UUID,                                -- Which panel this circuit belongs to
    wire_gauge      wire_gauge DEFAULT '18AWG',
    one_way_length_m  DECIMAL(8,2),
    one_way_length_ft DECIMAL(8,2),
    max_current_mA  DECIMAL(8,3),                       -- Panel limit for this circuit
    total_load_mA   DECIMAL(8,3) DEFAULT 0,             -- Calculated: sum of all device currents
    voltage_drop_V  DECIMAL(6,3),                       -- Calculated: voltage at farthest device
    voltage_ok      BOOLEAN DEFAULT TRUE,               -- Calculated: Vdevice >= 16VDC
    notes           TEXT,
    UNIQUE(floor_id, circuit_label)
);
CREATE INDEX idx_circuits_floor ON circuits(floor_id);

-- ============================================================================
-- TABLE: control_panels (installed panels in the project)
-- ============================================================================
CREATE TABLE control_panels (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    building_id     UUID REFERENCES buildings(id) ON DELETE CASCADE,
    floor_id        UUID REFERENCES floors(id),
    product_id      UUID REFERENCES products(id),
    panel_label     VARCHAR(100) NOT NULL,              -- e.g., 'FACP-1 Main'
    panel_type      panel_type NOT NULL,
    location        TEXT,                               -- e.g., 'Ground Floor — Electrical Room'
    position_x      DECIMAL(10,4),
    position_y      DECIMAL(10,4),
    slc_loop_count  INTEGER,
    nac_circuit_count INTEGER,
    idc_zone_count  INTEGER,
    max_devices_per_loop INTEGER,
    battery_ah      DECIMAL(6,2),                       -- Calculated required battery
    notes           TEXT
);

-- ============================================================================
-- TABLE: integration_points (building system interfaces)
-- ============================================================================
CREATE TABLE integration_points (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id      UUID REFERENCES projects(id) ON DELETE CASCADE,
    integration_type VARCHAR(100) NOT NULL,             -- e.g., 'ELEVATOR_RECALL', 'HVAC_SHUTDOWN'
    trigger_devices TEXT[],                              -- Device IDs that trigger this integration
    output_modules  TEXT[],                              -- Module IDs that send the output signal
    destination     VARCHAR(255),                        -- e.g., 'Elevator Controller Group A'
    description     TEXT,
    sequence_number INTEGER,
    notes           TEXT
);

-- ============================================================================
-- TABLE: calculations (stored calculation results)
-- ============================================================================
CREATE TABLE calculations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id      UUID REFERENCES projects(id) ON DELETE CASCADE,
    circuit_id      UUID REFERENCES circuits(id) ON DELETE SET NULL,
    calc_type       VARCHAR(50) NOT NULL,               -- VOLTAGE_DROP, BATTERY, NAC_LOADING, ZONE_AREA, STROBE_COVERAGE
    standard_used   standard_enum,
    formula_used    TEXT NOT NULL,
    inputs          JSONB NOT NULL,                      -- All input values
    result          JSONB NOT NULL,                      -- Calculation result(s)
    passed          BOOLEAN,                             -- PASS/FAIL
    code_reference  VARCHAR(100),                        -- e.g., 'NFPA 72 Section 10.6.7'
    notes           TEXT,
    calculated_at   TIMESTAMPTZ DEFAULT NOW(),
    calculated_by   UUID REFERENCES users(id)
);
CREATE INDEX idx_calculations_project ON calculations(project_id);
CREATE INDEX idx_calculations_circuit ON calculations(circuit_id);
CREATE INDEX idx_calculations_type ON calculations(calc_type);

-- ============================================================================
-- TABLE: validation_results (design compliance checks)
-- ============================================================================
CREATE TABLE validation_results (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id      UUID REFERENCES projects(id) ON DELETE CASCADE,
    device_id       UUID REFERENCES devices(id) ON DELETE SET NULL,
    check_type      VARCHAR(100) NOT NULL,              -- e.g., 'SPACING_WALL', 'SPACING_ADJACENT', 'VOLTAGE_DROP', 'ZONE_AREA'
    standard        standard_enum,
    rule_id         VARCHAR(100),                        -- Reference to rule in standards DB
    severity        VARCHAR(20) NOT NULL,                -- ERROR, WARNING, INFO
    message         TEXT NOT NULL,
    passed          BOOLEAN NOT NULL,
    details         JSONB,                               -- Additional context {expected: X, actual: Y, limit: Z}
    resolved        BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_validation_project ON validation_results(project_id);
CREATE INDEX idx_validation_severity ON validation_results(severity);
CREATE INDEX idx_validation_passed ON validation_results(passed);

-- ============================================================================
-- TABLE: floor_plan_files (uploaded floor plans)
-- ============================================================================
CREATE TABLE floor_plan_files (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    floor_id        UUID REFERENCES floors(id) ON DELETE CASCADE,
    file_name       VARCHAR(255) NOT NULL,
    file_type       VARCHAR(20) NOT NULL,                -- DWG, DXF, PDF, PNG, JPG
    file_size_bytes BIGINT,
    file_path       TEXT NOT NULL,                        -- Storage path (S3/local)
    scale_factor    DECIMAL(10,6),                       -- pixels-per-meter or similar
    uploaded_at     TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- TABLE: reports (generated reports)
-- ============================================================================
CREATE TABLE reports (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id      UUID REFERENCES projects(id) ON DELETE CASCADE,
    report_type     VARCHAR(50) NOT NULL,                -- CALCULATION, SHOP_DRAWING, BOM, COMPLIANCE
    report_format   VARCHAR(20) NOT NULL,                -- PDF, DWG, XLSX
    file_path       TEXT NOT NULL,
    file_size_bytes BIGINT,
    generated_at    TIMESTAMPTZ DEFAULT NOW(),
    generated_by    UUID REFERENCES users(id)
);

-- ============================================================================
-- TABLE: activity_log (audit trail)
-- ============================================================================
CREATE TABLE activity_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id      UUID REFERENCES projects(id) ON DELETE SET NULL,
    user_id         UUID REFERENCES users(id),
    action          VARCHAR(100) NOT NULL,               -- DEVICE_PLACED, DEVICE_MOVED, DEVICE_DELETED, CALC_RUN, etc.
    entity_type     VARCHAR(50),                         -- device, zone, circuit, etc.
    entity_id       UUID,
    details         JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_activity_project ON activity_log(project_id);
CREATE INDEX idx_activity_user ON activity_log(user_id);
CREATE INDEX idx_activity_created ON activity_log(created_at);

-- ============================================================================
-- SEED DATA: Wire Resistance Table
-- ============================================================================
INSERT INTO wire_resistance (awg, area_mm2, diameter_mm, resistance_ohm_per_kft, resistance_ohm_per_km, typical_use, notes) VALUES
('22AWG', 0.32, 0.640, 16.46, 53.27, 'Not recommended', 'Too thin for fire alarm circuits'),
('20AWG', 0.52, 0.810, 10.35, 33.31, 'Short signal runs', 'Marginal — not preferred'),
('18AWG', 0.82, 1.020, 6.51, 20.95, 'SLC, IDC, short NAC', 'MINIMUM acceptable gauge'),
('16AWG', 1.31, 1.290, 4.10, 13.17, 'NAC, longer SLC', 'Good balance'),
('14AWG', 2.08, 1.630, 2.58, 8.28, 'Long NAC, high device count', 'Recommended for loaded circuits'),
('12AWG', 3.31, 2.050, 1.62, 5.21, 'Very long runs, battery cables', 'Use when 14AWG insufficient'),
('10AWG', 5.26, 2.590, 1.02, 3.28, 'Battery cables, outdoor', 'Rarely needed for signal');

-- ============================================================================
-- SEED DATA: Sample Standards
-- ============================================================================
INSERT INTO standards (code, edition, title, publisher, country, scope) VALUES
('NFPA72', '2025', 'National Fire Alarm and Signaling Code', 'NFPA', 'USA', 'Comprehensive fire alarm design, installation, testing, maintenance'),
('BS5839', '2017+A1:2020', 'Fire detection and fire alarm systems for buildings — Part 1: Code of practice', 'BSI', 'UK', 'Non-domestic premises design and installation'),
('EN54', 'Series', 'Fire detection and fire alarm systems — Product certification', 'CEN', 'EU', 'Product certification and testing requirements'),
('EGYPTIAN', 'Current', 'Egyptian Code for Fire Protection', 'EOS', 'Egypt', 'Fire protection requirements for buildings in Egypt'),
('ISO7240', '2013', 'Fire detection and fire alarm systems', 'ISO', 'International', 'International design and installation standard'),
('IBC', '2024', 'International Building Code', 'ICC', 'USA', 'Building occupancy and fire protection requirements');

-- ============================================================================
-- VIEWS (Useful queries)
-- ============================================================================

-- Device count summary per project
CREATE OR REPLACE VIEW v_project_device_summary AS
SELECT
    p.id AS project_id,
    p.project_name,
    COUNT(DISTINCT d.id) AS total_devices,
    COUNT(DISTINCT CASE WHEN d.device_category = 'DETECTOR' THEN d.id END) AS detectors,
    COUNT(DISTINCT CASE WHEN d.device_category = 'NOTIFICATION' THEN d.id END) AS notification_devices,
    COUNT(DISTINCT CASE WHEN d.device_category = 'INITIATING' THEN d.id END) AS initiating_devices,
    COUNT(DISTINCT CASE WHEN d.device_category = 'MODULE' THEN d.id END) AS modules,
    COUNT(DISTINCT z.id) AS total_zones,
    COUNT(DISTINCT c.id) AS total_circuits
FROM projects p
JOIN buildings b ON b.project_id = p.id
JOIN floors f ON f.building_id = b.id
LEFT JOIN devices d ON d.floor_id = f.id
LEFT JOIN zones z ON z.floor_id = f.id
LEFT JOIN circuits c ON c.floor_id = f.id
GROUP BY p.id, p.project_name;

-- Circuit loading summary
CREATE OR REPLACE VIEW v_circuit_loading AS
SELECT
    c.id AS circuit_id,
    c.circuit_label,
    c.circuit_type,
    c.circuit_class,
    c.wire_gauge,
    c.one_way_length_ft,
    c.total_load_mA,
    c.max_current_mA,
    c.voltage_drop_V,
    c.voltage_ok,
    CASE
        WHEN c.total_load_mA > c.max_current_mA THEN 'OVERLOADED'
        WHEN c.voltage_drop_V > 2.4 THEN 'VOLTAGE_DROP_EXCEEDED'
        WHEN c.voltage_ok IS FALSE THEN 'VOLTAGE_LOW'
        ELSE 'OK'
    END AS status,
    COUNT(d.id) AS device_count,
    f.floor_number,
    b.building_name
FROM circuits c
JOIN floors f ON f.id = c.floor_id
JOIN buildings b ON b.id = f.building_id
LEFT JOIN devices d ON d.circuit_id = c.circuit_label AND d.floor_id = c.floor_id
GROUP BY c.id, c.circuit_label, c.circuit_type, c.circuit_class, c.wire_gauge,
         c.one_way_length_ft, c.total_load_mA, c.max_current_mA, c.voltage_drop_V,
         c.voltage_ok, f.floor_number, b.building_name;

-- Validation summary per project
CREATE OR REPLACE VIEW v_validation_summary AS
SELECT
    project_id,
    COUNT(*) AS total_checks,
    COUNT(*) FILTER (WHERE passed = TRUE) AS passed,
    COUNT(*) FILTER (WHERE passed = FALSE) AS failed,
    COUNT(*) FILTER (WHERE severity = 'ERROR' AND passed = FALSE) AS errors,
    COUNT(*) FILTER (WHERE severity = 'WARNING' AND passed = FALSE) AS warnings,
    CASE
        WHEN COUNT(*) FILTER (WHERE severity = 'ERROR' AND passed = FALSE) = 0 THEN 'PASS'
        ELSE 'FAIL'
    END AS overall_status
FROM validation_results
GROUP BY project_id;

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
