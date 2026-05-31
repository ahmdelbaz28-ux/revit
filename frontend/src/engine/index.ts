/**
 * Engineering Engine Module
 * Complete engineering calculation, BOM generation, and code validation system
 */

// Export calculation engine
export {
  calculateVoltageDrop,
  calculateShortCircuit,
  calculateCableSizing,
  calculateLoadFlow,
  checkBreakerCoordination,
  calculateEarthFaultLoop,
  calculatePowerFactorCorrection,
  generateCompleteReport,
  type VoltageDropResult,
  type ShortCircuitResult,
  type CableSizingResult,
  type LoadFlowResult,
  type BreakerCoordinationResult,
  type EarthFaultResult,
  type PowerFactorCorrectionResult,
  type EngineeringReport,
  type CableMaterial,
  type InstallationMethod,
  type CircuitType
} from './CalculationEngine';

// Export BOM generator
export {
  generateCableSchedule,
  calculateConduitSize,
  generateDeviceCount,
  generateBomSummary,
  groupCablesByType,
  generateExcelData,
  generateDxfCableEntities,
  generateDxfDeviceEntities,
  calculateCableLength,
  type CableScheduleItem,
  type ConduitScheduleItem,
  type DeviceCountItem,
  type BomSummary,
  type GroupedCableSchedule,
  type ExcelRow,
  type DxfEntity
} from './BomGenerator';

// Export code validator
export {
  validateSmokeDetectorPlacement,
  validateEmergencyLighting,
  validateCableProtection,
  validateMotorCircuit,
  validatePanelSizing,
  validateAllDevices,
  generateComplianceReport,
  generateAutoFix,
  type CodeViolation,
  type SpacingResult,
  type ProtectionResult,
  type MotorCircuitValidation,
  type PanelSizingValidation,
  type ComplianceReport,
  type AutoFixRecommendation,
  type Standard,
  type Severity
} from './CodeValidator';

// Export export engine
export {
  exportBomToExcel,
  exportToDxf,
  exportToPdfReport,
  exportToJson,
  type DxfExportOptions,
  type PdfReportData,
  type ProjectExport
} from './ExportEngine';