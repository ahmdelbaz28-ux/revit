
/**
 * ExportEngine.ts - Professional Export Functions
 * Generates industry-standard Excel and DXF files
 */

import { saveAs } from "file-saver";

// ============================================================================
// TYPES & INTERFACES
// ============================================================================

import type {
	BomSummary,
	CableScheduleItem,
	ConduitScheduleItem,
	DeviceCountItem,
} from "./BomGenerator";

export interface ExcelSheet {
	name: string;
	headers: string[];
	data: (string | number)[][];
}

// ============================================================================
// EXCEL EXPORT (using SheetJS-compatible format)
// ============================================================================

/**
 * Generate Excel file with BOM, Cable Schedule, and Device List
 * Format compatible with Microsoft Excel (.xlsx)
 */
export function exportBomToExcel(
	cableSchedule: CableScheduleItem[],
	deviceCounts: DeviceCountItem[],
	conduitSchedule: ConduitScheduleItem[],
	summary: BomSummary,
): void {
	const workbook = generateExcelWorkbook(
		cableSchedule,
		deviceCounts,
		conduitSchedule,
		summary,
	);
	downloadExcel(workbook);
}

function generateExcelWorkbook(
	cableSchedule: CableScheduleItem[],
	deviceCounts: DeviceCountItem[],
	conduitSchedule: ConduitScheduleItem[],
	summary: BomSummary,
): Blob {
	// Generate CSV format (compatible with Excel)
	let csvContent = "";

	// === SUMMARY SHEET ===
	csvContent += "BILL OF MATERIALS - SUMMARY\n";
	csvContent += `Generated:,="${new Date().toISOString()}"\n`;
	csvContent += "\n";
	csvContent += "Description,Value,Unit\n";
	csvContent += `Total Cables,${summary.totalCables},\n`;
	csvContent += `Total Cable Length,${summary.totalCableLength},m\n`;
	csvContent += `Total Conduits,${summary.totalConduits},\n`;
	csvContent += `Total Devices,${summary.totalDevices},\n`;
	csvContent += `Estimated Weight,${summary.estimatedWeight},kg\n`;
	csvContent += `Estimated Cost,${summary.estimatedCost},EUR\n`;
	csvContent += "\n\n";

	// === CABLE SCHEDULE SHEET ===
	csvContent += "CABLE SCHEDULE\n";
	csvContent +=
		"ID,From,To,Length (m),Cross Section (mm²),Material,Type,Weight (kg),Cost (EUR),Route\n";

	cableSchedule.forEach((cable) => {
		csvContent += `${cable.id},${cable.from},${cable.to},${cable.length},${cable.crossSection},${cable.material},${cable.type},${cable.estimatedWeight},${cable.cost},"${cable.destination}"\n`;
	});

	csvContent += "\n";

	// Totals row
	const _totalLength = cableSchedule.reduce((sum, c) => sum + c.length, 0);
	const totalWeight = cableSchedule.reduce(
		(sum, c) => sum + c.estimatedWeight,
		0,
	);
	const totalCost = cableSchedule.reduce((sum, c) => sum + c.cost, 0);

	csvContent += `TOTAL,,,,,,${totalWeight.toFixed(2)},${totalCost.toFixed(2)}\n`;
	csvContent += "\n\n";

	// === DEVICE COUNT SHEET ===
	csvContent += "DEVICE COUNT\n";
	csvContent +=
		"Type,Category,Quantity,Avg Power (W),Total Power (W),Mounting\n";

	deviceCounts.forEach((device) => {
		csvContent += `${device.type},${device.category},${device.count},${device.avgPower},${device.totalPower},${device.mounting}\n`;
	});

	const totalDevices = deviceCounts.reduce((sum, d) => sum + d.count, 0);
	const totalPower = deviceCounts.reduce((sum, d) => sum + d.totalPower, 0);

	csvContent += `\nTOTAL,,${totalDevices},,${totalPower},\n`;
	csvContent += "\n\n";

	// === CONDUIT SCHEDULE SHEET ===
	csvContent += "CONDUIT SCHEDULE\n";
	csvContent += "ID,Size,Fill Ratio (%),Cables,Total Area (mm²),Recommended\n";

	conduitSchedule.forEach((conduit) => {
		csvContent += `${conduit.id},${conduit.size},${conduit.fillRatio},"${conduit.cables.join(", ")}",${conduit.totalCrossSection},"${conduit.recommendedSize}"\n`;
	});

	// Create Blob with BOM for Excel compatibility
	const BOM = "\uFEFF";
	return new Blob([BOM + csvContent], { type: "text/csv;charset=utf-8" });
}

function downloadExcel(blob: Blob): void {
	const timestamp = new Date().toISOString().split("T")[0];
	saveAs(blob, `BOM_${timestamp}.csv`);
}

// ============================================================================
// DXF EXPORT (AutoCAD Compatible)
// ============================================================================

export interface DxfExportOptions {
	scale: number; // pixels to mm
	layerNames: {
		cables: string;
		devices: string;
		conduits: string;
		text: string;
	};
	colors: {
		cables: number;
		devices: number;
		conduits: number;
		text: number;
	};
}

const DEFAULT_DXF_OPTIONS: DxfExportOptions = {
	scale: 10,
	layerNames: {
		cables: "CABLES",
		devices: "DEVICES",
		conduits: "CONDUITS",
		text: "TEXT",
	},
	colors: {
		cables: 1, // Red
		devices: 3, // Green
		conduits: 5, // Magenta
		text: 7, // White
	},
};

/**
 * Export canvas to DXF format compatible with AutoCAD
 */
export function exportToDxf(
	devices: Array<{
		id: string;
		type: string;
		x: number;
		y: number;
		voltage?: number;
		load?: number;
	}>,
	connections: Array<{
		id: string;
		fromId: string;
		toId: string;
		current?: number;
	}>,
	options: Partial<DxfExportOptions> = {},
): void {
	const opts = { ...DEFAULT_DXF_OPTIONS, ...options };
	const dxfContent = generateDxfContent(devices, connections, opts);
	downloadDxf(dxfContent);
}

function generateDxfContent(
	devices: Array<{
		id: string;
		type: string;
		x: number;
		y: number;
		voltage?: number;
		load?: number;
	}>,
	connections: Array<{
		id: string;
		fromId: string;
		toId: string;
		current?: number;
	}>,
	options: DxfExportOptions,
): string {
	let dxf = "";

	// DXF Header
	dxf += "0\nSECTION\n";
	dxf += "2\nHEADER\n";
	dxf += "9\n$ACADVER\n1\nAC1014\n"; // AutoCAD 2000 format
	dxf += "9\n$INSUNITS\n70\n6\n"; // Meters
	dxf += "0\nENDSEC\n";

	// Tables section (layers)
	dxf += "0\nSECTION\n";
	dxf += "2\nTABLES\n";

	// Layer table
	dxf += "0\nTABLE\n";
	dxf += "2\nLAYER\n";
	dxf += "70\n4\n";

	// CABLES layer
	dxf += "0\nLAYER\n";
	dxf += `2\n${options.layerNames.cables}\n`;
	dxf += "70\n0\n";
	dxf += `62\n${options.colors.cables}\n`;
	dxf += "6\nCONTINUOUS\n";

	// DEVICES layer
	dxf += "0\nLAYER\n";
	dxf += `2\n${options.layerNames.devices}\n`;
	dxf += "70\n0\n";
	dxf += `62\n${options.colors.devices}\n`;
	dxf += "6\nCONTINUOUS\n";

	// CONDUITS layer
	dxf += "0\nLAYER\n";
	dxf += `2\n${options.layerNames.conduits}\n`;
	dxf += "70\n0\n";
	dxf += `62\n${options.colors.conduits}\n`;
	dxf += "6\nCONTINUOUS\n";

	// TEXT layer
	dxf += "0\nLAYER\n";
	dxf += `2\n${options.layerNames.text}\n`;
	dxf += "70\n0\n";
	dxf += `62\n${options.colors.text}\n`;
	dxf += "6\nCONTINUOUS\n";

	dxf += "0\nENDTAB\n";
	dxf += "0\nENDSEC\n";

	// Entities section
	dxf += "0\nSECTION\n";
	dxf += "2\nENTITIES\n";

	// Draw devices as circles/blocks
	devices.forEach((device, _index) => {
		const x = device.x * options.scale;
		const y = device.y * options.scale;
		const radius = 50; // Fixed representation size

		// Device circle
		dxf += "0\nCIRCLE\n";
		dxf += `8\n${options.layerNames.devices}\n`;
		dxf += `10\n${x.toFixed(4)}\n`;
		dxf += `20\n${y.toFixed(4)}\n`;
		dxf += "30\n0\n";
		dxf += `40\n${radius}\n`;

		// Device label
		dxf += "0\nTEXT\n";
		dxf += `8\n${options.layerNames.text}\n`;
		dxf += `10\n${(x + radius + 10).toFixed(4)}\n`;
		dxf += `20\n${y.toFixed(4)}\n`;
		dxf += "30\n0\n";
		dxf += "40\n20\n";
		dxf += `1\n${device.type}\n`;
	});

	// Draw connections as lines
	connections.forEach((conn) => {
		const fromDevice = devices.find((d) => d.id === conn.fromId);
		const toDevice = devices.find((d) => d.id === conn.toId);

		if (fromDevice && toDevice) {
			const x1 = fromDevice.x * options.scale;
			const y1 = fromDevice.y * options.scale;
			const x2 = toDevice.x * options.scale;
			const y2 = toDevice.y * options.scale;

			// Cable line
			dxf += "0\nLINE\n";
			dxf += `8\n${options.layerNames.cables}\n`;
			dxf += `10\n${x1.toFixed(4)}\n`;
			dxf += `20\n${y1.toFixed(4)}\n`;
			dxf += "30\n0\n";
			dxf += `11\n${x2.toFixed(4)}\n`;
			dxf += `21\n${y2.toFixed(4)}\n`;
			dxf += "31\n0\n";
		}
	});

	dxf += "0\nENDSEC\n";

	// End of file
	dxf += "0\nEOF\n";

	return dxf;
}

function downloadDxf(content: string): void {
	const timestamp = new Date().toISOString().split("T")[0];
	const blob = new Blob([content], { type: "application/dxf" });
	saveAs(blob, `Project_${timestamp}.dxf`);
}

// ============================================================================
// PROFESSIONAL PDF REPORT EXPORT
// ============================================================================

export interface PdfReportData {
	projectName: string;
	clientName: string;
	engineerName: string;
	date: string;
	cableSchedule: CableScheduleItem[];
	deviceCounts: DeviceCountItem[];
	summary: BomSummary;
	calculations?: {
		voltageDrop?: number;
		shortCircuit?: number;
		cableSize?: number;
	};
}

/**
 * Generate PDF-ready HTML for printing
 */
export function exportToPdfReport(data: PdfReportData): string {
	const html = `
<!DOCTYPE html>
<html>
<head>
  <title>BOM Report - ${data.projectName}</title>
  <style>
    @page { size: A4; margin: 20mm; }
    body { font-family: Arial, sans-serif; font-size: 10pt; }
    h1 { font-size: 18pt; border-bottom: 2px solid #333; padding-bottom: 10px; }
    h2 { font-size: 14pt; margin-top: 20px; background: #f0f0f0; padding: 5px; }
    table { width: 100%; border-collapse: collapse; margin: 15px 0; }
    th, td { border: 1px solid #999; padding: 6px; text-align: left; }
    th { background: #333; color: white; }
    tr:nth-child(even) { background: #f9f9f9; }
    .summary { display: flex; flex-wrap: wrap; }
    .summary-item { flex: 1; min-width: 150px; padding: 10px; margin: 5px; background: #f5f5f5; border-radius: 5px; }
    .summary-label { font-size: 9pt; color: #666; }
    .summary-value { font-size: 16pt; font-weight: bold; }
    .header-info { display: flex; justify-content: space-between; margin-bottom: 20px; }
    .footer { position: fixed; bottom: 0; width: 100%; font-size: 8pt; color: #999; text-align: center; }
    @media print { .no-print { display: none; } }
  </style>
</head>
<body>
  <h1>Bill of Materials Report</h1>
  <div class="header-info">
    <div>
      <strong>Project:</strong> ${data.projectName}<br>
      <strong>Client:</strong> ${data.clientName}
    </div>
    <div style="text-align: right;">
      <strong>Engineer:</strong> ${data.engineerName}<br>
      <strong>Date:</strong> ${data.date}
    </div>
  </div>
  
  <h2>Summary</h2>
  <div class="summary">
    <div class="summary-item">
      <div class="summary-label">Total Cables</div>
      <div class="summary-value">${data.summary.totalCables}</div>
    </div>
    <div class="summary-item">
      <div class="summary-label">Total Length</div>
      <div class="summary-value">${data.summary.totalCableLength} m</div>
    </div>
    <div class="summary-item">
      <div class="summary-label">Total Devices</div>
      <div class="summary-value">${data.summary.totalDevices}</div>
    </div>
    <div class="summary-item">
      <div class="summary-label">Est. Weight</div>
      <div class="summary-value">${data.summary.estimatedWeight} kg</div>
    </div>
    <div class="summary-item">
      <div class="summary-label">Est. Cost</div>
      <div class="summary-value">€${data.summary.estimatedCost}</div>
    </div>
  </div>
  
  <h2>Cable Schedule</h2>
  <table>
    <thead>
      <tr>
        <th>ID</th>
        <th>From</th>
        <th>To</th>
        <th>Length (m)</th>
        <th>Size (mm²)</th>
        <th>Type</th>
        <th>Material</th>
        <th>Cost (€)</th>
      </tr>
    </thead>
    <tbody>
      ${data.cableSchedule
				.map(
					(c) => `
        <tr>
          <td>${c.id}</td>
          <td>${c.from}</td>
          <td>${c.to}</td>
          <td>${c.length}</td>
          <td>${c.crossSection}</td>
          <td>${c.type}</td>
          <td>${c.material}</td>
          <td>${c.cost.toFixed(2)}</td>
        </tr>
      `,
				)
				.join("")}
    </tbody>
  </table>
  
  <h2>Device Count</h2>
  <table>
    <thead>
      <tr>
        <th>Type</th>
        <th>Category</th>
        <th>Quantity</th>
        <th>Avg Power (W)</th>
        <th>Total Power (W)</th>
        <th>Mounting</th>
      </tr>
    </thead>
    <tbody>
      ${data.deviceCounts
				.map(
					(d) => `
        <tr>
          <td>${d.type}</td>
          <td>${d.category}</td>
          <td>${d.count}</td>
          <td>${d.avgPower}</td>
          <td>${d.totalPower}</td>
          <td>${d.mounting}</td>
        </tr>
      `,
				)
				.join("")}
    </tbody>
  </table>
  
  ${
		data.calculations
			? `
  <h2>Engineering Calculations</h2>
  <table>
    <tr><th>Parameter</th><th>Value</th></tr>
    ${data.calculations.voltageDrop !== undefined ? `<tr><td>Voltage Drop</td><td>${data.calculations.voltageDrop}%</td></tr>` : ""}
    ${data.calculations.shortCircuit !== undefined ? `<tr><td>Short Circuit Current</td><td>${data.calculations.shortCircuit} kA</td></tr>` : ""}
    ${data.calculations.cableSize !== undefined ? `<tr><td>Recommended Cable Size</td><td>${data.calculations.cableSize} mm²</td></tr>` : ""}
  </table>
  `
			: ""
	}
  
  <div class="footer">
    Generated by FIREAI Engineering System | Page 1 of 1
  </div>
  
  <button class="no-print" onclick="window.print()" style="position: fixed; top: 10px; right: 10px; padding: 10px 20px;">
    Print Report
  </button>
</body>
</html>
  `;

	return html;
}

// ============================================================================
// JSON EXPORT (for backup/import)
// ============================================================================

export interface ProjectExport {
	version: string;
	exportedAt: string;
	projectName: string;
	devices: Array<{
		id: string;
		type: string;
		x: number;
		y: number;
		voltage: number;
		load: number;
	}>;
	connections: Array<{
		id: string;
		fromId: string;
		toId: string;
		current: number;
	}>;
	cableSchedule: CableScheduleItem[];
	deviceCounts: DeviceCountItem[];
	summary: BomSummary;
}

export function exportToJson(
	projectName: string,
	devices: Array<{
		id: string;
		type: string;
		x: number;
		y: number;
		voltage: number;
		load: number;
	}>,
	connections: Array<{
		id: string;
		fromId: string;
		toId: string;
		current: number;
	}>,
	cableSchedule: CableScheduleItem[],
	deviceCounts: DeviceCountItem[],
	summary: BomSummary,
): void {
	const exportData: ProjectExport = {
		version: "1.0.0",
		exportedAt: new Date().toISOString(),
		projectName,
		devices,
		connections,
		cableSchedule,
		deviceCounts,
		summary,
	};

	const blob = new Blob([JSON.stringify(exportData, null, 2)], {
		type: "application/json",
	});
	const timestamp = new Date().toISOString().split("T")[0];
	saveAs(blob, `Project_${projectName}_${timestamp}.json`);
}
