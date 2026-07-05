/**
 * Engineering Engine Module
 * Complete engineering calculation, BOM generation, and code validation system
 */

// Export BOM generator
export {
	type BomSummary,
	type CableScheduleItem,
	type ConduitScheduleItem,
	calculateCableLength,
	calculateConduitSize,
	type DeviceCountItem,
	type DxfEntity,
	type ExcelRow,
	type GroupedCableSchedule,
	generateBomSummary,
	generateCableSchedule,
	generateDeviceCount,
	generateDxfCableEntities,
	generateDxfDeviceEntities,
	generateExcelData,
	groupCablesByType,
} from "./BomGenerator";
// Export calculation engine
export {
	type BreakerCoordinationResult,
	type CableMaterial,
	type CableSizingResult,
	type CircuitType,
	calculateCableSizing,
	calculateEarthFaultLoop,
	calculateLoadFlow,
	calculatePowerFactorCorrection,
	calculateShortCircuit,
	calculateVoltageDrop,
	checkBreakerCoordination,
	type EarthFaultResult,
	type EngineeringReport,
	generateCompleteReport,
	type InstallationMethod,
	type LoadFlowResult,
	type PowerFactorCorrectionResult,
	type ShortCircuitResult,
	type VoltageDropResult,
} from "./CalculationEngine";

// Export code validator
export {
	type AutoFixRecommendation,
	type CodeViolation,
	type ComplianceReport,
	generateAutoFix,
	generateComplianceReport,
	type MotorCircuitValidation,
	type PanelSizingValidation,
	type ProtectionResult,
	type Severity,
	type SpacingResult,
	type Standard,
	validateAllDevices,
	validateCableProtection,
	validateEmergencyLighting,
	validateMotorCircuit,
	validatePanelSizing,
	validateSmokeDetectorPlacement,
} from "./CodeValidator";

// Export export engine
export {
	type DxfExportOptions,
	exportBomToExcel,
	exportToDxf,
	exportToJson,
	exportToPdfReport,
	type PdfReportData,
	type ProjectExport,
} from "./ExportEngine";
