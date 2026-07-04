import React, { useState } from "react";
import { Download, FileJson, File, Archive } from "lucide-react";

export const ExportManagerPage: React.FC = () => {
  const [selectedFormat, setSelectedFormat] = useState("dxf");

  const formats = [
    {
      id: "dxf",
      name: "DXF (AutoCAD)",
      icon: File,
      description: "AutoCAD Drawing Exchange Format",
    },
    {
      id: "revit",
      name: "Revit (RVT)",
      icon: File,
      description: "Autodesk Revit Project File",
    },
    {
      id: "ifc",
      name: "IFC (Industry Foundation Classes)",
      icon: File,
      description: "Open BIM format - IFC4 / IFC2x3",
    },
    {
      id: "json",
      name: "JSON",
      icon: FileJson,
      description: "Structured data export",
    },
  ];

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-slate-100 flex items-center gap-2">
          <Download className="h-8 w-8 text-blue-500" />
          Export Manager
        </h1>
        <p className="text-slate-400 mt-2">Export projects in multiple formats</p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {formats.map((format) => {
          const Icon = format.icon;
          return (
            <button
              key={format.id}
              onClick={() => setSelectedFormat(format.id)}
              className={`p-4 rounded-lg border-2 transition-all ${
                selectedFormat === format.id
                  ? "border-blue-500 bg-blue-500/10"
                  : "border-slate-700 bg-slate-800/50 hover:border-slate-600"
              }`}
            >
              <Icon className="h-6 w-6 mx-auto mb-2" />
              <h3 className="font-semibold text-slate-100 text-sm">{format.name}</h3>
              <p className="text-xs text-slate-400 mt-1">{format.description}</p>
            </button>
          );
        })}
      </div>

      <button className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg transition-colors">
        Export Project
      </button>
    </div>
  );
};

export default ExportManagerPage;
