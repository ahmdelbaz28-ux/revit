import React, { useEffect, useRef, useState } from "react";
import { 
  Zap, Cpu, Globe, Share2, Play, Settings, Layers, Box, Maximize2, Terminal, Shield
} from "lucide-react";

export function AdvancedCADWorkspace() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [workerResult, setWorkerResult] = useState<string | null>(null);
  const [isCalculating, setIsCalculating] = useState(false);
  const workerRef = useRef<Worker | null>(null);

  useEffect(() => {
    // Initialize WebGL
    const canvas = canvasRef.current;
    if (canvas) {
      const gl = canvas.getContext("webgl");
      if (gl) {
        // Set clear color to dark blue/grey
        gl.clearColor(0.05, 0.05, 0.08, 1.0);
        gl.clear(gl.COLOR_BUFFER_BIT);
        
        // Draw a simple grid or something to show it's active
        // (Skipping complex geometry to avoid bloating code, but setting the background is a good indicator)
      }
    }

    // Initialize Worker
    // Note: In Vite, we use new Worker(new URL(..., import.meta.url))
    try {
      workerRef.current = new Worker(
        new URL("../../../lib/cadCalculator.worker.ts", import.meta.url),
        { type: "module" }
      );

      workerRef.current.onmessage = (e) => {
        if (e.data.type === "result") {
          setWorkerResult(`Calculation Complete: ${Math.round(e.data.data.result)} operations simulated.`);
          setIsCalculating(false);
        }
      };
    } catch (e) {
      console.error("Failed to initialize worker", e);
    }

    return () => {
      workerRef.current?.terminate();
    };
  }, []);

  const runHeavyCalculation = () => {
    setIsCalculating(true);
    setWorkerResult(null);
    workerRef.current?.postMessage({
      type: "calculate_load_flow",
      data: { gridId: "MDB-001", nodes: 1500 }
    });
  };

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-[#05050a] text-slate-100 font-sans">
      {/* Premium Header */}
      <div className="h-14 flex items-center justify-between px-6 border-b border-slate-800 bg-[#0a0a14]/90 backdrop-blur-md shrink-0">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Cpu className="h-5 w-5 text-blue-500" />
            <span className="font-bold text-sm uppercase tracking-widest">NexusCAD Pro</span>
          </div>
          <div className="h-5 w-px bg-slate-700" />
          <div className="text-xs text-slate-400 font-medium">Enterprise Workspace</div>
          <div className="flex bg-slate-800/50 p-0.5 rounded-lg text-xs">
            <button className="px-3 py-1 rounded-md bg-blue-600 text-white font-medium">Model</button>
            <button className="px-3 py-1 rounded-md text-slate-400 hover:text-white">Analysis</button>
            <button className="px-3 py-1 rounded-md text-slate-400 hover:text-white">Simulation</button>
          </div>
        </div>
        
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-500/10 rounded-full border border-emerald-500/20">
            <Shield className="h-3.5 w-3.5 text-emerald-500" />
            <span className="text-xs text-emerald-400 font-medium">WebGPU Acceleration Active</span>
          </div>
          <button className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 transition-colors">
            <Share2 className="h-4 w-4" />
          </button>
          <button className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 transition-colors">
            <Settings className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left Sidebar - Tools */}
        <div className="w-16 flex flex-col items-center py-4 gap-4 border-r border-slate-800 bg-[#0a0a14]/90">
          <button className="p-3 rounded-xl bg-blue-600 text-white shadow-lg shadow-blue-600/20">
            <Box className="h-5 w-5" />
          </button>
          <button className="p-3 rounded-xl text-slate-400 hover:bg-slate-800 hover:text-white transition-colors">
            <Layers className="h-5 w-5" />
          </button>
          <button className="p-3 rounded-xl text-slate-400 hover:bg-slate-800 hover:text-white transition-colors">
            <Globe className="h-5 w-5" />
          </button>
          <button className="p-3 rounded-xl text-slate-400 hover:bg-slate-800 hover:text-white transition-colors">
            <Terminal className="h-5 w-5" />
          </button>
        </div>

        {/* Main Area */}
        <div className="flex-1 flex flex-col relative">
          {/* WebGL Canvas */}
          <div className="flex-1 bg-[#0b0b12] relative">
            <canvas ref={canvasRef} className="w-full h-full" width={1200} height={800} />
            
            {/* Overlay Glassmorphic Panel */}
            <div className="absolute top-6 left-6 w-80 bg-[#0a0a14]/80 backdrop-blur-xl border border-slate-800 rounded-xl p-5 shadow-2xl">
              <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">System Architecture</div>
              
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Zap className="h-4 w-4 text-amber-500" />
                    <span className="text-sm font-medium">WebAssembly Engine</span>
                  </div>
                  <span className="text-xs text-emerald-400 font-mono">Standby</span>
                </div>
                
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Cpu className="h-4 w-4 text-blue-500" />
                    <span className="text-sm font-medium">Worker Threads</span>
                  </div>
                  <span className="text-xs text-emerald-400 font-mono">1 Active</span>
                </div>

                <div className="border-t border-slate-800 pt-3 mt-3">
                  <button 
                    onClick={runHeavyCalculation}
                    disabled={isCalculating}
                    className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                      isCalculating 
                        ? "bg-slate-700 text-slate-400 cursor-not-allowed" 
                        : "bg-blue-600 hover:bg-blue-500 text-white"
                    }`}
                  >
                    <Play className="h-3.5 w-3.5" />
                    {isCalculating ? "Calculating..." : "Run Heavy Simulation"}
                  </button>
                </div>

                {workerResult && (
                  <div className="mt-3 p-2.5 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
                    <div className="text-xs text-emerald-400 font-mono">{workerResult}</div>
                  </div>
                )}
              </div>
            </div>

            {/* Bottom Floating Stats */}
            <div className="absolute bottom-6 left-6 right-6 flex justify-between items-center text-xs text-slate-500">
              <div className="flex items-center gap-4 bg-[#0a0a14]/80 backdrop-blur-md px-4 py-2 rounded-lg border border-slate-800">
                <div>FPS: <span className="text-emerald-400 font-mono font-bold">60.0</span></div>
                <div>Memory: <span className="text-blue-400 font-mono">42.4 MB</span></div>
                <div>Objects: <span className="text-slate-200 font-mono">1,500</span></div>
              </div>
              
              <div className="flex items-center gap-2 bg-[#0a0a14]/80 backdrop-blur-md px-4 py-2 rounded-lg border border-slate-800">
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-slate-300">Live Sync with Central Database</span>
              </div>
            </div>

            {/* Top Right Controls */}
            <div className="absolute top-6 right-6 flex gap-2">
              <button className="p-2.5 bg-[#0a0a14]/80 backdrop-blur-md border border-slate-800 rounded-lg hover:bg-slate-800 transition-colors">
                <Maximize2 className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default AdvancedCADWorkspace;
