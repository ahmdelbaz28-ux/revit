# 🔥 Fire Alarm Database - Recommended Enhancements
# Version 2.0 | 2026-05-09
# Expert Recommendations for Fire Alarm System Design Database

---

## Part 1: Building Types (Missing - CRITICAL)

### Currently: Only 1 file (occupancy-classification.json)
### Needed: Complete classification by project type

```json
{
  "building_types": [
    {
      "id": "RESIDENTIAL_L1",
      "name_ar": "سكني فاخر (فيلات)",
      "name_en": "Residential L1 (Villas)",
      "occupancy_group": "R1",
      "risk_level": "LOW",
      "detector_required": true,
      "smoke_heat_combined": "SMOKE_PRIMARY",
      "sprinkler_override": false,
      "manual_stations": "CORRIDOR_ONLY",
      "notification": "SELECTABLE",
      "code_ref": "NFPA 101 30.1.2"
    },
    {
      "id": "RESIDENTIAL_R2",
      "name_ar": "سكني (شقق)",
      "name_en": "Residential R2 (Apartments)",
      "occupancy_group": "R2",
      "risk_level": "LOW", 
      "detector_required": true,
      "smoke_heat_combined": "SMOKE_PRIMARY",
      "sprinkler_override": false,
      "manual_stations": "ENTRANCE_ONLY",
      "notification": "SELECTABLE",
      "code_ref": "NFPA 101 30.3.2"
    },
    {
      "id": "HOTEL",
      "name_ar": "فندق",
      "name_en": "Hotel/Motel",
      "occupancy_group": "R1",
      "risk_level": "MEDIUM",
      "detector_required": true,
      "smoke_heat_combined": "SMOKE_PRIMARY",
      "sprinkler_override": true,
      "manual_stations": "EVERY_FLOOR",
      "notification": "MANDATORY_STROBE",
      "code_ref": "NFPA 101 28.3.4"
    },
    {
      "id": "OFFICE_B",
      "name_ar": "مبنى مكاتب",
      "name_en": "Office Building (B)",
      "occupancy_group": "B",
      "risk_level": "MEDIUM",
      "detector_required": true,
      "smoke_heat_combined": "SMOKE_PRIMARY",
      "sprinkler_override": false,
      "manual_stations": "EVERY_FLOOR",
      "notification": "MANDATORY_STROBE",
      "code_ref": "NFPA 101 36.2.2"
    },
    {
      "id": "MALL_A2",
      "name_ar": "مول تجاري",
      "name_en": "Mall (A2)",
      "occupancy_group": "A2",
      "risk_level": "HIGH",
      "detector_required": true,
      "smoke_heat_combined": "SMOKE_HIGH_SENSITIVITY",
      "sprinkler_override": true,
      "manual_stations": "100FT_SPACING",
      "notification": "VOICE_PREFERRED",
      "code_ref": "NFPA 101 38.2.2"
    },
    {
      "id": "INDUSTRIAL_F1",
      "name_ar": "مصنع (F1)",
      "name_en": "Factory F1",
      "occupancy_group": "F1",
      "risk_level": "HIGH",
      "detector_required": true,
      "smoke_heat_combined": "HEAT_OR_SMOKE",
      "sprinkler_override": true,
      "manual_stations": "5000_SQFT",
      "notification": "HORN_STROBE",
      "code_ref": "NFPA 101 40.2.2"
    },
    {
      "id": "WAREHOUSE_S1",
      "name_ar": "مستودع",
      "name_en": "Warehouse S1",
      "occupancy_group": "S1",
      "risk_level": "MEDIUM",
      "detector_required": true,
      "smoke_heat_combined": "HEAT_UL_RATE",
      "sprinkler_override": true,
      "manual_stations": "EVERY_BAY",
      "notification": "SELECTABLE",
      "code_ref": "NFPA 101 42.2.2"
    },
    {
      "id": "HOSPITAL_I1",
      "name_ar": "مستشفى",
      "name_en": "Hospital I1",
      "occupancy_group": "I1",
      "risk_level": "CRITICAL",
      "detector_required": true,
      "smoke_heat_combined": "SMOKE_HIGH_SENSITIVITY",
      "sprinkler_override": true,
      "manual_stations": "NURSE_STATION",
      "notification": "VOICE_MANDATORY",
      "code_ref": "NFPA 101 18.3.4"
    },
    {
      "id": "SCHOOL_E",
      "name_ar": "مدرسة/جامعة",
      "name_en": "Educational E",
      "occupancy_group": "E",
      "risk_level": "MEDIUM",
      "detector_required": true,
      "smoke_heat_combined": "SMOKE_PRIMARY",
      "sprinkler_override": true,
      "manual_stations": "EVERY_FLOOR",
      "notification": "SELECTABLE",
      "code_ref": "NFPA 101 16.2.2"
    },
    {
      "id": "PARKING_OPEN",
      "name_ar": "جراج (مفتوح)",
      "name_en": "Parking Open",
      "occupancy_group": "S2",
      "risk_level": "MEDIUM",
      "detector_required": false,
      "smoke_heat_combined": "HEAT_UL_RATE",
      "sprinkler_override": true,
      "manual_stations": "LEVELS",
      "notification": "HORN_ONLY",
      "code_ref": "NFPA 101 42.8.2"
    },
    {
      "id": "HIGH_RISE",
      "name_ar": "ناطحة سحاب",
      "name_en": "High-Rise Building",
      "occupancy_group": "R1",
      "risk_level": "HIGH",
      "detector_required": true,
      "smoke_heat_combined": "SMOKE_PRIMARY",
      "sprinkler_override": true,
      "manual_stations": "EVAC_STAIR",
      "notification": "VOICE_MANDATORY",
      "code_ref": "NFPA 101 11.8.10"
    }
  ]
}
```

---

## Part 2: Special Hazard Systems (Missing - CRITICAL)

```json
{
  "special_systems": [
    {
      "id": "CLEAN_AGENT_FM200",
      "name_ar": "نظام FM-200",
      "name_en": "FM-200 Clean Agent",
      "application": "DATA_CENTER_SERVER",
      "agent_type": "FM-200",
      "design_concentration": "7.8%",
      "hold_time": 10,
      "detection": "PRESSURE_RATE",
      "discharge": "AUTOMATIC",
      "code_ref": "NFPA 2001 4.3"
    },
    {
      "id": "CO2_SYSTEM", 
      "name_ar": "ثاني أكسيد الكربون",
      "name_en": "CO2 Suppression",
      "application": "INDUSTRIAL_KITCHEN",
      "agent_type": "CO2",
      "design_concentration": "34%",
      "hold_time": 30,
      "detection": "HEAT",
      "discharge": "AUTOMATIC",
      "code_ref": "NFPA 12 4.5"
    },
    {
      "id": "KITCHEN_SUPPRESSION",
      "name_ar": "نظام إطفاء مطابخ",
      "name_en": "Kitchen Suppression",
      "application": "COMMERCIAL_KITCHEN",
      "agent_type": "WET_CHEMICAL",
      "design": "BLOWN_UP",
      "temperature": "155F",
      "detection": "FIXED_TEMP",
      "code_ref": "NFPA 17A 6.2"
    },
    {
      "id": "AEROSOL_GENERATOR",
      "name_ar": "مولد ضباب",
      "name_en": "Aerosol Generator",
      "application": "LARGE_SPACE",
      "agent_type": "AEROSOL",
      "design_concentration": ">85%",
      "detection": "SMOKE",
      "discharge": "AUTOMATIC",
      "code_ref": "NFPA 201 6.3"
    }
  ]
}
```

---

## Part 3: Evacuation Systems (Missing - HIGH PRIORITY)

```json
{
  "evacuation_systems": {
    "emergency_lighting": {
      "required_by": ["R1", "R2", "R3", "A", "I", "H"],
      "illuminance": "1_FC_MIN",
      "battery_duration": "90_MIN",
      "code_ref": "NFPA 101 7.9.2"
    },
    "emergency_voice": {
      "types": ["STANDARD_VOICE", "DIGITAL_MESSAGE", "LIVE_PAGING"],
      "zones": "FLOOR_REQUIRED",
      "backuperve": "BATTERY_90MIN",
      "code_ref": "NFPA 72 24.4"
    },
    "directional_signage": {
      "types": ["FLOOR_EGRESS", "EXIT_PATH", "ARROW"],
      "photoluminescent": "YES",
      "battery_backup": "90_MIN",
      "code_ref": "NFPA 101 7.10"
    }
  }
}
```

---

## Part 4: Advanced Detector Types (Missing)

```json
{
  "advanced_detectors": [
    {
      "id": "ASPIRATING_SMOKE_VESDA",
      "name_ar": "كاشف دخان شغال",
      "name_en": "Aspirating Smoke Detector",
      "type": "VESDA_AIR_SAMPLING",
      "sensitivity": "0.005_to_0.1%_OBSC",
      "application": ["DATA_CENTER", "TELCO", "CLEAN_ROOM", "HIGH_CEILING"],
      "coverage_area": "50000_SQFT_MAX",
      "sampling_points": "64_MAX",
      "code_ref": "NFPA 72 21.2.4"
    },
    {
      "id": "BEAM_DETECTOR",
      "name_ar": "كاشف حزمة",
      "name_en": "Beam Smoke Detector",
      "type": "BEAM_LINE",
      "range": "16_TO_230_FT",
      "application": ["WAREHOUSE", "ATRIUM", "CATHEDRAL"],
      "reflector": "REQUIRED",
      "code_ref": "NFPA 72 21.2.3"
    },
    {
      "id": "DUCT_SMOKE_DETECTOR",
      "name_ar": "كاشف دخان مجاري هواء",
      "name_en": "Duct Smoke Detector",
      "type": "DUCT_MOUNTED",
      "application": ["HVAC_RETURN", "AIR_HANDLER"],
      "sampling_tube": "REQUIRED",
      "shut_down": "REQUIRED",
      "code_ref": "NFPA 72 21.2.5"
    },
    {
      "id": "WIRELESS_SYSTEM",
      "name_ar": "نظام لاسلكي",
      "name_en": "Wireless Fire Alarm",
      "type": "RADIO_FREQ",
      "frequency": "900MHZ_2_4GHZ",
      "application": ["HISTORIC_BUILDING", "HERITAGE", "RESTRICTED_WIRING"],
      "battery_life": "5_YEARS",
      "code_ref": "NFPA 72 23.6"
    },
    {
      "id": "MULTI_SENSOR",
      "name_ar": "كاشف متعدد الحساسات",
      "name_en": "Multi-Criteria Detector",
      "type": "COMBINATION",
      "sensors": ["SMOKE_PHOTOELECTRIC", "HEAT_ROR", "CO"],
      "application": ["VARYING_ENVIRONMENT"],
      "intelligence": "ALGORITHMIC",
      "code_ref": "NFPA 72 21.2.6"
    }
  ]
}
```

---

## Part 5: Cost Data (Missing - BUSINESS CRITICAL)

```json
{
  "cost_database": {
    "equipment_prices_egp": {
      "control_panel_conventional_4zone": {"base": 15000, "installed": 22000},
      "control_panel_conventional_8zone": {"base": 22000, "installed": 32000},
      "panel_addressable_250_amp": {"base": 80000, "installed": 120000},
      "panel_addressable_500_amp": {"base": 150000, "installed": 220000},
      "panel_intelligent_2000": {"base": 350000, "installed": 450000},
      "smoke_detector_base": {"base": 450, "installed": 800},
      "smoke_detector_intelligent": {"base": 1200, "installed": 2000},
      "heat_detector_fixed": {"base": 350, "installed": 700},
      "heat_detector_ror": {"base": 550, "installed": 900},
      "manual_pull_station": {"base": 800, "installed": 1500},
      "horn_strobe": {"base": 1200, "installed": 2200},
      "speaker_strobe": {"base": 2500, "installed": 4000},
      "bell_6_inch": {"base": 900, "installed": 1500},
      "module_monitor": {"base": 1500, "installed": 2500},
      "module_control": {"base": 1800, "installed": 3000},
      "isolator": {"base": 1200, "installed": 2000},
      "battery_12v18ah": {"base": 1200, "installed": 1500},
      "battery_12v26ah": {"base": 1800, "installed": 2200}
    },
    "labor_rates_egp": {
      "engineer_design": 2500,
      "senior_engineer_review": 4000,
      "technician_installation": 350,
      "electrician": 400,
      "engineer_commissioning": 5000,
      "draftsman_cad": 500
    },
    "wire_costs_per_meter": {
      "2c_14awg_fplr": 45,
      "2c_16awg_fplr": 35,
      "4c_14awg_fplr": 80,
      "1c_18awg": 15,
      "1c_16awg": 20,
      "1c_14awg": 25
    },
    "typical_markup": {
      "material": 1.25,
      "labor": 1.35,
      "engineering": 1.40,
      "contingency": 0.10
    }
  }
}
```

---

## Part 6: Installation Standards (Missing - REFERENCE)

```json
{
  "installation_standards": {
    " conduit_routes": ["CEILING", "WALL", "SURFACE"],
    "box_requirements": {
      "junction_box_min": "4_SQUARE",
      "device_box": "STANDARD_OCTAGON",
      "pull_box": "EVERY_100FT"
    },
    "wire_terminations": {
      "strip_length": "5_8_INCH",
      "twist_3_TURNS_MIN",
      "wire_nut_SIZE_MATCH
    },
    "height_mounting": {
      "detector_ceiling": "6_INCH_MIN",
      "manual_station": "48_INCH_CENTER,
      "notification_80_INCH_ABOVE_FLOOR,
      "strobe_80_TO_96_INCH"
    },
    "accessibility": {
      "detector_3_FT_CLEAR,
      "panel_36_INCH_CLEAR,
      "manual_station_5_FT_CLEAR
    }
  }
}
```

---

## Part 7: Testing & Commissioning (Missing)

```json
{
  "commissioning_tests": {
    "smoke_detector": {
      "test": "CANNISTER_SMOKE", 
      "sensitivity": "1_TO_3%_OBSC_PER_FT",
      "acceptable_range": "0.5_to_4%_OBSC",
      "reference": "NFPA 72 17.7.4"
    },
    "heat_detector": {
      "test": "FIXED_TEMP_HEAT",
      "temperature_rise": "15F_PER_MIN_MIN",
      "reference": "NFPA 72 17.8.4"
    },
    "manual_station": {
      "test": "MANUAL_PULL",
      "verification": "ALARM_INITIATED",
      "reference": "NFPA 72 17.11.3"
    },
    "notification": {
      "test": "DB_MEASUREMENT",
      "minimum_85dB_AWEIGHTED",
      "reference": "NFPA 72 18.4.3"
    },
    "battery": {
      "test": "24HOUR_STANDBY + 15MIN_ALARM",
      "voltage_drop": "20%_MAX",
      "reference": "NFPA 72 10.6.4"
    }
  }
}
```

---

## Part 8: Project Checklist Template

```json
{
  "project_checklist": {
    "pre_design": [
      " building occupancy classification",
      " applicable codes identified",
      " client requirements meeting",
      " site survey completed",
      " existing fire protection noted"
    ],
    "design": [
      " floor plans received",
      " detector layout complete",
      " manual station placement",
      " notification device layout",
      " zone diagram",
      " riser diagram",
      " voltage drop calculations",
      " battery calculations",
      " equipment schedule",
      " single line diagram"
    ],
    "approval": [
      " Civil Defense submission",
      " client review",
      " AHJ approval",
      " equipment submittal",
      " shop drawing approval"
    ],
    "installation": [
      " conduit installation",
      " wire installation",
      " device installation",
      " panel installation",
      " testing"
    ],
    "commissioning": [
      " device sensitivity test",
      " manual station test",
      " notification test",
      " battery test",
      " system integration test",
      " AHJ final inspection"
    ]
  }
}
```

*Generated: 2026-05-09*
*Author: Fire Protection Engineering Consultant*
*License: Database v2.0 Enhancement Recommendations*