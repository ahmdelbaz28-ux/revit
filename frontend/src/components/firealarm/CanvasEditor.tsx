import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

// Define detector types
export type DetectorType = 'smoke' | 'heat' | 'pull' | 'horns' | 'speaker' | 'facp';

// Define detector interface
export interface Detector {
  id: string;
  x: number;
  y: number;
  type: DetectorType;
  zone?: string;
  address?: string;
  status: 'normal' | 'warning' | 'fault';
  coverageRadius: number;
  location?: string;
  heightAFF?: number;
  manufacturer?: string;
  model?: string;
  sensitivity?: 'high' | 'standard' | 'low';
  lastTestDate?: string;
}

interface CanvasEditorProps {
  floorPlanImage?: string;
  detectors: Detector[];
  onDetectorsChange: (detectors: Detector[]) => void;
}

export const CanvasEditor: React.FC<CanvasEditorProps> = ({
  floorPlanImage,
  detectors,
  onDetectorsChange
}) => {
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLDivElement>(null);
  const [draggingDetector, setDraggingDetector] = useState<string | null>(null);
  const [selectedDetector, setSelectedDetector] = useState<string | null>(null);
  const [newDetectorType, setNewDetectorType] = useState<DetectorType>('smoke');
  
  // Handle click on canvas to add new detector.
  // P0.7 FIX: Three bugs fixed here:
  //   (a) Double-fire: previously this handler ran on EVERY click inside
  //       the canvas div, including clicks on detector <g> elements (which
  //       also trigger handleMouseDown for dragging). Clicking a detector
  //       to drag it would ALSO spawn a new detector at the same point.
  //       Fix: ignore the click if the click target is not the canvas
  //       div itself (i.e., the click bubbled up from a child element
  //       like a detector <g> or the floor-plan <img>).
  //   (b) ID collision: Date.now() has millisecond resolution and is
  //       predictable — two rapid clicks in the same ms produce the
  //       same id, and a hostile script could predict future ids.
  //       Fix: use crypto.randomUUID() (Web Crypto API, available in
  //       all modern browsers and Node 19+). Falls back to Date.now() +
  //       Math.random() only if crypto is unavailable (very old runtime).
  //   (c) Coverage radius was correctly using 6.37m for smoke and 4.27m
  //       for heat (matches NFPA 72 §17.7.4.2.3.1 R = 0.7 × S with
  //       S = 9.1m / 6.1m respectively). Left as-is.
  const handleCanvasClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!canvasRef.current) return;
    // P0.7 FIX (a): only treat clicks that land on the canvas div ITSELF
    // as "add new detector". Clicks on detector <g> elements, the
    // floor-plan <img>, or any other child should NOT spawn a detector.
    if (e.target !== canvasRef.current) return;

    const rect = canvasRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // Define coverage radius based on detector type
    let coverageRadius = 6.37; // Default for smoke detector (NFPA 72 §17.7.4.2.3.1)
    if (newDetectorType === 'heat') {
      coverageRadius = 4.27; // Smaller for heat detector (NFPA 72 Table 17.6.3.1.1)
    }

    // P0.7 FIX (b): cryptographically-strong unique ID. Date.now() can
    // collide on rapid clicks and is predictable.
    const newId = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? `detector-${crypto.randomUUID()}`
      : `detector-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

    const newDetector: Detector = {
      id: newId,
      x,
      y,
      type: newDetectorType,
      status: 'normal',
      coverageRadius,
      location: 'Not Set',
      heightAFF: 2.7,
      manufacturer: 'Default',
      model: 'Generic',
      sensitivity: 'standard',
      lastTestDate: new Date().toISOString().split('T')[0]
    };

    onDetectorsChange([...detectors, newDetector]);
  };

  // Handle mouse down on a detector to start dragging
  const handleMouseDown = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setDraggingDetector(id);
    setSelectedDetector(id);
  };

  // Handle mouse move to update detector position
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (draggingDetector && canvasRef.current) {
        const rect = canvasRef.current.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        const updatedDetectors = detectors.map(detector => {
          if (detector.id === draggingDetector) {
            return { ...detector, x, y };
          }
          return detector;
        });
        
        onDetectorsChange(updatedDetectors);
      }
    };

    const handleMouseUp = () => {
      setDraggingDetector(null);
    };

    if (draggingDetector) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [draggingDetector, detectors, onDetectorsChange]);

  // Get status color based on detector status
  const getStatusColor = (status: 'normal' | 'warning' | 'fault') => {
    switch (status) {
      case 'normal':
        return '#10B981'; // Green
      case 'warning':
        return '#F59E0B'; // Amber
      case 'fault':
        return '#EF4444'; // Red
      default:
        return '#10B981'; // Green
    }
  };

  // Render detector based on its type
  const renderDetector = (detector: Detector) => {
    const isSelected = selectedDetector === detector.id;
    const statusColor = getStatusColor(detector.status);
    
    // Different shapes for different detector types
    let detectorShape;
    switch (detector.type) {
      case 'smoke':
        detectorShape = (
          <circle
            cx="12"
            cy="12"
            r="8"
            fill={statusColor}
            stroke="#FFFFFF"
            strokeWidth="2"
          />
        );
        break;
      case 'heat':
        detectorShape = (
          <polygon
            points="12,4 20,20 4,20"
            fill={statusColor}
            stroke="#FFFFFF"
            strokeWidth="2"
          />
        );
        break;
      case 'pull':
        detectorShape = (
          <rect
            x="6"
            y="6"
            width="12"
            height="12"
            rx="2"
            fill={statusColor}
            stroke="#FFFFFF"
            strokeWidth="2"
          />
        );
        break;
      case 'horns':
        detectorShape = (
          <rect
            x="4"
            y="8"
            width="16"
            height="8"
            rx="2"
            fill={statusColor}
            stroke="#FFFFFF"
            strokeWidth="2"
          />
        );
        break;
      case 'speaker':
        detectorShape = (
          <circle
            cx="12"
            cy="12"
            r="8"
            fill={statusColor}
            stroke="#FFFFFF"
            strokeWidth="2"
          />
        );
        break;
      case 'facp':
        detectorShape = (
          <rect
            x="2"
            y="4"
            width="20"
            height="16"
            rx="3"
            fill={statusColor}
            stroke="#FFFFFF"
            strokeWidth="2"
          />
        );
        break;
      default:
        detectorShape = (
          <circle
            cx="12"
            cy="12"
            r="8"
            fill={statusColor}
            stroke="#FFFFFF"
            strokeWidth="2"
          />
        );
    }

    return (
      <g
        key={detector.id}
        transform={`translate(${detector.x - 12}, ${detector.y - 12})`}
        onMouseDown={(e) => handleMouseDown(detector.id, e)}
        style={{ cursor: draggingDetector ? 'grabbing' : 'grab' }}
      >
        {detectorShape}
        {isSelected && (
          <rect
            x="-2"
            y="-2"
            width="28"
            height="28"
            rx="4"
            fill="none"
            stroke="#3B82F6"
            strokeWidth="2"
            strokeDasharray="4 2"
          />
        )}
      </g>
    );
  };

  return (
    <div className="flex flex-col h-full">
      <div className="mb-4 flex gap-2">
        <label className="text-sm font-medium text-slate-300">{t('fireAlarm.addDetector')}</label>
        <select
          value={newDetectorType}
          onChange={(e) => setNewDetectorType(e.target.value as DetectorType)}
          className="bg-slate-900 border border-slate-600 rounded px-2 py-1 text-sm text-slate-100"
        >
          <option value="smoke">{t('fireAlarm.smokeDet')}</option>
          <option value="heat">{t('fireAlarm.heatDet')}</option>
          <option value="pull">{t('fireAlarm.pullStation')}</option>
          <option value="horns">{t('fireAlarm.hornStrobe')}</option>
          <option value="speaker">{t('fireAlarm.speaker')}</option>
          <option value="facp">{t('fireAlarm.facp')}</option>
        </select>
      </div>
      
      <div
        ref={canvasRef}
        className="flex-1 bg-slate-900 border border-slate-700 rounded-lg relative overflow-hidden"
        onClick={handleCanvasClick}
        style={{ minHeight: '400px' }}
      >
        {floorPlanImage ? (
          <img 
            src={floorPlanImage} 
            alt="Floor Plan" 
            className="absolute inset-0 w-full h-full object-contain"
          />
        ) : (
          <div className="absolute inset-0 bg-slate-800 flex items-center justify-center">
            <p className="text-slate-500">{t('fireAlarm.floorPlanPlaceholder')}</p>
          </div>
        )}
        
        {/* P0.7 FIX: Coverage circles + detectors both rendered inside ONE
            <svg> element. Previously, the coverage <circle>s were direct
            children of the canvas <div>, which means the browser did NOT
            render them — SVG primitives only render inside an <svg>
            container. This silently dropped all coverage visualization
            (the engineer could not see whether detectors covered the
            entire floor area, which is the primary safety function of
            the canvas). */}

        {/* Single SVG container holds both coverage circles and detector
            icons. The SVG itself catches NO pointer events (pointer-events:
            none) so clicks pass through to the canvas div below for the
            "add new detector" flow. Detector <g> elements re-enable
            pointer events via onMouseDown handlers. */}
        <svg
          className="absolute inset-0 w-full h-full"
          style={{ pointerEvents: 'none' }}
          aria-label={t('fireAlarm.detectorCanvas', 'Detector canvas')}
        >
          {/* Coverage circles — drawn first so detector icons appear on top */}
          {detectors.map(detector => (
            <circle
              key={`coverage-${detector.id}`}
              cx={detector.x}
              cy={detector.y}
              r={detector.coverageRadius * 10} // Scale factor for visualization
              fill="rgba(167, 139, 250, 0.2)"
              stroke="rgba(167, 139, 250, 0.5)"
              strokeWidth="1"
            />
          ))}

          {/* Detectors — rendered after coverage circles so they appear on top */}
          {detectors.map(renderDetector)}
        </svg>
      </div>
    </div>
  );
};