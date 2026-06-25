import React, { useRef } from 'react';
import { Upload, Download, FileCode, AlertCircle } from 'lucide-react';
import { saveAs } from 'file-saver';
import DxfParser from 'dxf-parser';
import { actions } from '@/store/simpleStore';

export function ImportExportManager() {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleExportJSON = () => {
    // Retrieve current state logic would go here (simplified for demo)
    // In real app, access store directly or via prop
    const projectData = localStorage.getItem('nexus_project_state') || '{}';
    const blob = new Blob([projectData], { type: 'application/json;charset=utf-8' });
    saveAs(blob, `NexusCAD_Project_${new Date().toISOString().split('T')[0]}.json`);
  };

  const handleImportDXF = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const parser = new DxfParser();
        const result = event.target?.result;
        if (typeof result !== 'string') {
          throw new Error('Invalid file content');
        }
        const dxfData = parser.parseSync(result);
        
        // TODO: Convert DXF Entities (Lines, Circles) to Nexus Devices/Connections
        // This is a placeholder for the complex conversion logic
        if (import.meta.env.DEV) console.log('DXF Parsed:', dxfData);
        if (dxfData && dxfData.entities) {
          alert(`DXF Imported Successfully!\nFound ${dxfData.entities.length} entities.\n(Conversion to smart objects pending implementation)`);
        }
        
        // Example: Trigger an action to add parsed data to store
        // actions.importEntities(convertedEntities); 
      } catch (err) {
        if (import.meta.env.DEV) console.error(err);
        alert('Failed to parse DXF file. Ensure it is a valid ASCII DXF.');
      }
    };
    reader.readAsText(file);
    // Reset input
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="flex items-center gap-2">
      <button 
        onClick={handleExportJSON}
        className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20 rounded-md transition-colors border border-emerald-500/20"
      >
        <Download size={14} /> Export JSON
      </button>
      
      <button 
        onClick={() => fileInputRef.current?.click()}
        className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium bg-blue-500/10 text-blue-500 hover:bg-blue-500/20 rounded-md transition-colors border border-blue-500/20"
      >
        <Upload size={14} /> Import DXF
      </button>
      <input 
        type="file" 
        ref={fileInputRef} 
        onChange={handleImportDXF} 
        accept=".dxf" 
        className="hidden" 
      />

      <div className="h-4 w-px bg-border mx-1" />
      
      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground bg-muted px-2 py-1 rounded">
        <AlertCircle size={10} />
        <span>Revit IFC Support: Coming in v1.1</span>
      </div>
    </div>
  );
}
