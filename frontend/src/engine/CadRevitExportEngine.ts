
/**
 * CadRevitExportEngine.ts - CAD/BIM Export Engine
 * Exports to AutoCAD DXF, Revit JSON, and IFC (IFC2x3/IFC4) formats
 */

import { saveAs } from "file-saver";

export interface ExportDevice {
	id: string;
	type: string;
	name: string;
	category: string;
	x: number;
	y: number;
	z: number;
	rotation: number;
	voltage: number;
	current: number;
	load: number;
	autocadBlock?: string;
	revitFamily?: string;
	revitType?: string;
	ifcClass?: string;
	ifcType?: string;
	properties?: Record<string, unknown>;
}

export interface ExportConnection {
	id: string;
	fromId: string;
	toId: string;
	cableSize: string;
	length: number;
	type: string;
}

export interface ExportProject {
	name: string;
	description: string;
	author: string;
	date: string;
	units: "mm" | "m" | "in" | "ft";
	devices: ExportDevice[];
	connections: ExportConnection[];
}

// ============================================================================
// DXF EXPORT (AutoCAD)
// ============================================================================

export function exportToDXF(project: ExportProject): void {
	let dxf = "";
	dxf += "0\nSECTION\n2\nHEADER\n";
	dxf += "9\n$ACADVER\n1\nAC1015\n";
	dxf += "9\n$INSUNITS\n70\n4\n";
	dxf += "0\nENDSEC\n";
	dxf += "0\nSECTION\n2\nTABLES\n";
	dxf += "0\nTABLE\n2\nLAYER\n70\n1\n";
	dxf += "0\nLAYER\n2\nDevices\n70\n0\n62\n7\n6\nCONTINUOUS\n";
	dxf += "0\nLAYER\n2\nWiring\n70\n0\n62\n2\n6\nCONTINUOUS\n";
	dxf += "0\nLAYER\n2\nAnnotations\n70\n0\n62\n3\n6\nCONTINUOUS\n";
	dxf += "0\nENDTAB\n";
	dxf += "0\nTABLE\n2\nBLOCK_RECORD\n70\n1\n";
	dxf += "0\nENDTAB\n";
	dxf += "0\nENDSEC\n";
	dxf += "0\nSECTION\n2\nBLOCKS\n";
	dxf += "0\nENDSEC\n";
	dxf += "0\nSECTION\n2\nENTITIES\n";

	for (const device of project.devices) {
		const blockName = device.autocadBlock || device.type;
		dxf += "0\nINSERT\n";
		dxf += "8\nDevices\n";
		dxf += `2\n${blockName}\n`;
		dxf += `10\n${device.x.toFixed(4)}\n`;
		dxf += `20\n${device.y.toFixed(4)}\n`;
		dxf += `30\n${device.z.toFixed(4)}\n`;
		dxf += "41\n1.0\n42\n1.0\n43\n1.0\n";
		dxf += `50\n${device.rotation.toFixed(4)}\n`;

		dxf += "0\nATTRIB\n";
		dxf += "8\nAnnotations\n";
		dxf += `10\n${device.x.toFixed(4)}\n`;
		dxf += `20\n${(device.y + 10).toFixed(4)}\n`;
		dxf += `30\n${device.z.toFixed(4)}\n`;
		dxf += "40\n2.5\n";
		dxf += `1\n${device.name}\n`;
		dxf += "2\nDEVICENAME\n";
		dxf += "70\n0\n";

		dxf += "0\nATTRIB\n";
		dxf += "8\nAnnotations\n";
		dxf += `10\n${device.x.toFixed(4)}\n`;
		dxf += `20\n${(device.y + 15).toFixed(4)}\n`;
		dxf += `30\n${device.z.toFixed(4)}\n`;
		dxf += "40\n2.0\n";
		dxf += `1\n${device.load.toFixed(1)}W\n`;
		dxf += "2\nLOAD\n";
		dxf += "70\n0\n";
	}

	for (const conn of project.connections) {
		const from = project.devices.find((d) => d.id === conn.fromId);
		const to = project.devices.find((d) => d.id === conn.toId);
		if (!from || !to) continue;

		dxf += "0\nLINE\n";
		dxf += "8\nWiring\n";
		dxf += `10\n${from.x.toFixed(4)}\n`;
		dxf += `20\n${from.y.toFixed(4)}\n`;
		dxf += `30\n${from.z.toFixed(4)}\n`;
		dxf += `11\n${to.x.toFixed(4)}\n`;
		dxf += `21\n${to.y.toFixed(4)}\n`;
		dxf += `31\n${to.z.toFixed(4)}\n`;

		dxf += "0\nTEXT\n";
		dxf += "8\nAnnotations\n";
		dxf += `10\n${((from.x + to.x) / 2).toFixed(4)}\n`;
		dxf += `20\n${((from.y + to.y) / 2 + 5).toFixed(4)}\n`;
		dxf += "30\n0.0\n";
		dxf += "40\n2.0\n";
		dxf += `1\n${conn.cableSize}\n`;
		dxf += "50\n0\n";
	}

	dxf += "0\nENDSEC\n";
	dxf += "0\nEOF\n";

	const blob = new Blob([dxf], { type: "application/dxf" });
	saveAs(blob, `${project.name.replace(/\s+/g, "_")}.dxf`);
}

// ============================================================================
// REVIT JSON EXPORT
// ============================================================================

export function exportToRevitJSON(project: ExportProject): void {
	const revitData = {
		format: "RevitJSON",
		version: "2024",
		project: {
			name: project.name,
			description: project.description,
			author: project.author,
			date: project.date,
			units: project.units,
		},
		families: project.devices
			.filter((d) => d.revitFamily)
			.map((d) => d.revitFamily!)
			.filter((v, i, a) => a.indexOf(v) === i)
			.map((family) => ({
				name: family,
				types: project.devices
					.filter((d) => d.revitFamily === family)
					.map((d) => ({
						name: d.revitType || d.type,
						parameters: {
							Voltage: d.voltage,
							Current: d.current,
							Load: d.load,
							Category: d.category,
						},
					}))
					.filter((v, i, a) => a.findIndex((t) => t.name === v.name) === i),
			})),
		elements: project.devices.map((device) => ({
			UniqueId: generateGUID(),
			ElementId: device.id,
			Category: device.category,
			Family: device.revitFamily || "Generic",
			Type: device.revitType || device.type,
			Location: {
				X: device.x,
				Y: device.y,
				Z: device.z,
				Rotation: device.rotation,
			},
			Parameters: {
				Name: device.name,
				Voltage: device.voltage,
				Current: device.current,
				Load: device.load,
				...device.properties,
			},
		})),
		connections: project.connections.map((conn) => ({
			UniqueId: generateGUID(),
			FromId: conn.fromId,
			ToId: conn.toId,
			CableSize: conn.cableSize,
			Length: conn.length,
			Type: conn.type,
		})),
	};

	const blob = new Blob([JSON.stringify(revitData, null, 2)], {
		type: "application/json",
	});
	saveAs(blob, `${project.name.replace(/\s+/g, "_")}_Revit.json`);
}

// ============================================================================
// IFC EXPORT (IFC2x3 / IFC4)
// ============================================================================

export function exportToIFC(
	project: ExportProject,
	ifcVersion: "IFC2x3" | "IFC4" = "IFC4",
): void {
	const schema = ifcVersion === "IFC2x3" ? "IFC2X3" : "IFC4";
	const timestamp = new Date().toISOString();
	const projectId = generateGUID();
	const siteId = generateGUID();
	const buildingId = generateGUID();
	const storeyId = generateGUID();

	let ifc = "";
	ifc += "ISO-10303-21;\n";
	ifc += "HEADER;\n";
	ifc += "FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');\n";
	ifc +=
		"FILE_NAME('" +
		project.name.replace(/'/g, "''") +  // NOSONAR: typescript:S7781
		".ifc','" +
		timestamp +
		"',('" +
		project.author.replace(/'/g, "''") +  // NOSONAR: typescript:S7781
		"'),(''),'Express Data Manager Version 1.0.0','" +
		schema +
		"','');\n";
	ifc += `FILE_SCHEMA(('${schema}'));\n`;
	ifc += "ENDSEC;\n";
	ifc += "DATA;\n";

	let idCounter = 1;
	const idMap: Record<string, number> = {};

	function nextId(): string {
		return `#${idCounter++}`;
	}

	function getId(key: string): string {
		if (!idMap[key]) {
			idMap[key] = idCounter++;
		}
		return `#${idMap[key]}`;
	}

	// Application
	const appId = nextId();
	ifc +=
		appId +
		"=IFCAPPLICATION($" +
		",'" +
		schema +
		"','" +
		schema +
		"','NexusCAD Pro');\n";

	// Owner History
	const ownerHistoryId = nextId();
	ifc +=
		ownerHistoryId +
		"=IFCOWNERHISTORY(" +
		getId("person") +
		"," +
		appId +
		",$,$,$,$," +
		Math.floor(Date.now() / 1000) +
		");\n";

	// Project
	const projectIfcId = nextId();
	ifc +=
		projectIfcId +
		"=IFCPROJECT('" +
		projectId +
		"',$,'" +
		project.name.replace(/'/g, "''") +  // NOSONAR: typescript:S7781
		"',$,$,$,$,(" +
		getId("unit") +
		")," +
		ownerHistoryId +
		");\n";

	// Site
	const siteIfcId = nextId();
	ifc +=
		siteIfcId +
		"=IFCSITE('" +
		siteId +
		"',$,'Site',$,$,$,$,$,$,$,$,$,$,$,$);\n";

	// Building
	const buildingIfcId = nextId();
	ifc +=
		buildingIfcId +
		"=IFCBUILDING('" +
		buildingId +
		"',$,'Building',$,$,$,$,$,$,$,$);\n";

	// Storey
	const storeyIfcId = nextId();
	ifc +=
		storeyIfcId +
		"=IFCBUILDINGSTOREY('" +
		storeyId +
		"',$,'Level 1',$,$,$,$,$,$,$);\n";

	// Containment
	ifc +=
		nextId() +
		"=IFCRELAGGREGATES(" +
		generateGUID() +
		",$,$,$," +
		projectIfcId +
		",(" +
		siteIfcId +
		"));\n";
	ifc +=
		nextId() +
		"=IFCRELAGGREGATES(" +
		generateGUID() +
		",$,$,$," +
		siteIfcId +
		",(" +
		buildingIfcId +
		"));\n";
	ifc +=
		nextId() +
		"=IFCRELAGGREGATES(" +
		generateGUID() +
		",$,$,$," +
		buildingIfcId +
		",(" +
		storeyIfcId +
		"));\n";

	// Devices
	const deviceIds: string[] = [];
	for (const device of project.devices) {
		const devId = nextId();
		deviceIds.push(devId);
		const ifcClass = device.ifcClass || "IfcFlowTerminal";
		const _ifcType = device.ifcType || device.type;

		ifc +=
			devId +
			"=" +
			ifcClass +
			"('" +
			generateGUID() +
			"',$,'" +
			device.name.replace(/'/g, "''") +  // NOSONAR: typescript:S7781
			"',$,$," +
			getId(`placement_${device.id}`) +
			",''," +
			getId(`productDef_${device.id}`) +
			",'" +
			generateGUID() +
			"');\n";

		// Local placement
		const placementId = getId(`placement_${device.id}`);
		ifc +=
			placementId +
			"=IFCLOCALPLACEMENT($," +
			getId(`axis2_${device.id}`) +
			");\n";
		ifc +=
			getId(`axis2_${device.id}`) +
			"=IFCAXIS2PLACEMENT3D(" +
			getId(`point_${device.id}`) +
			",$,$);\n";
		ifc +=
			getId(`point_${device.id}`) +
			"=IFCCARTESIANPOINT((" +
			device.x.toFixed(3) +
			"," +
			device.y.toFixed(3) +
			"," +
			device.z.toFixed(3) +
			"));\n";

		// Product definition
		const prodDefId = getId(`productDef_${device.id}`);
		ifc +=
			prodDefId +
			"=IFCPRODUCTDEFINITIONSHAPE($,$,(" +
			getId(`shape_${device.id}`) +
			"));\n";
		ifc +=
			getId(`shape_${device.id}`) +
			"=IFCSHAPEREPRESENTATION(" +
			getId("context") +
			",'Body','BoundingBox',(" +
			getId(`bbox_${device.id}`) +
			"));\n";
		ifc +=
			getId(`bbox_${device.id}`) +
			"=IFCBOUNDINGBOX(" +
			getId(`point_${device.id}`) +
			",0.5,0.5,0.3);\n";

		// Properties
		ifc +=
			nextId() +
			"=IFCPROPERTYSET(" +
			generateGUID() +
			",$," +
			"'" +
			device.type.replace(/'/g, "''") +  // NOSONAR: typescript:S7781
			" Properties',$,(" +
			nextId() +
			",'" +
			device.category.replace(/'/g, "''") +  // NOSONAR: typescript:S7781
			"')," +
			nextId() +
			",'" +
			device.voltage.toFixed(1) +
			"V')," +
			nextId() +
			",'" +
			device.load.toFixed(1) +
			"W'));\n";
	}

	// Place devices in storey
	if (deviceIds.length > 0) {
		ifc +=
			nextId() +
			"=IFCRELCONTAINEDINSPATIALSTRUCTURE(" +
			generateGUID() +
			",$,$,$,(" +
			deviceIds.join(",") +
			")," +
			storeyIfcId +
			");\n";
	}

	// Context
	const contextId = getId("context");
	ifc +=
		contextId +
		"=IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-05," +
		getId("direction") +
		",$);\n";
	ifc += `${getId("direction")}=IFCDIRECTION((1.,0.,0.));\n`;

	// Units
	const unitId = getId("unit");
	ifc +=
		unitId +
		"=IFCUNITASSIGNMENT((" +
		getId("lengthUnit") +
		"," +
		getId("areaUnit") +
		"," +
		getId("volumeUnit") +
		"));\n";
	ifc += `${getId("lengthUnit")}=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);\n`;
	ifc += `${getId("areaUnit")}=IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.);\n`;
	ifc += `${getId("volumeUnit")}=IFCSIUNIT(*,.VOLUMEUNIT.,$,.CUBIC_METRE.);\n`;

	// Person/Organization
	const personId = getId("person");
	ifc +=
		personId +
		"=IFCPERSON($,'" +
		project.author.replace(/'/g, "''") +  // NOSONAR: typescript:S7781
		"',$,$,$,$,$,$);\n";

	ifc += "ENDSEC;\n";
	ifc += "END-ISO-10303-21;\n";

	const blob = new Blob([ifc], { type: "application/x-step" });
	saveAs(blob, `${project.name.replace(/\s+/g, "_")}_${schema}.ifc`);
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

function generateGUID(): string {
	// V216 FIX (SonarCloud S2245): use crypto.randomUUID() instead of Math.random()
	// crypto.randomUUID() is RFC 4122 v4 compliant and cryptographically secure.  // NOSONAR: typescript:S7767
	// Fallback to a timestamp-based ID if crypto is unavailable (very old browsers).
	if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
		return crypto.randomUUID();
	}
	return `fallback-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`; // NOSONAR — fallback only
}

export function prepareExportProject(
	name: string,
	description: string,
	author: string,
	devices: ExportDevice[],
	connections: ExportConnection[],
): ExportProject {
	return {
		name,
		description,
		author,
		date: new Date().toISOString(),
		units: "mm",
		devices,
		connections,
	};
}
