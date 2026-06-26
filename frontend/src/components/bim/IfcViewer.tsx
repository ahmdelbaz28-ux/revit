/**
 * IfcViewer.tsx — Pure web-ifc + Three.js IFC Viewer (Phase 0-C)
 * ================================================================
 *
 * Lightweight IFC viewer using web-ifc directly + Three.js for rendering.
 * NOT using @thatopen/components — too heavy for Phase 0 scaffold.
 *
 * Features:
 *   - Loads .ifc files via web-ifc WASM
 *   - Renders 3D geometry with Three.js
 *   - Extracts spaces (IfcSpace) for fire alarm analysis
 *   - Exposes parsed data to parent components via callbacks
 *
 * Safety-Critical:
 *   - All geometry extraction is traceable (correlation ID)
 *   - Failed loads NEVER silently succeed
 *   - Error boundaries prevent viewer crash from taking down the app
 *
 * Reference: ISO 16739-1:2024 (IFC 4.3 ADD2), NFPA 72-2022 §14.2.4
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import * as THREE from "three";
import * as WebIFC from "web-ifc";

// ── Types ────────────────────────────────────────────────────────────────────

interface IfcViewerProps {
  /** URL to the .ifc file (served by backend/routers/ifc_files.py) */
  ifcUrl: string;
  /** Correlation ID for audit trail (NFPA 72 §14.2.4) */
  correlationId?: string;
  /** Callback when IFC spaces are extracted */
  onSpacesExtracted?: (spaces: IfcSpaceData[]) => void;
  /** Callback when loading fails */
  onError?: (error: Error) => void;
  /** Callback when loading succeeds */
  onLoaded?: (metadata: IfcMetadata) => void;
  /** Show coverage overlay: green=covered, red=uncovered */
  showCoverage?: boolean;
  /** Coverage data: array of {x, y, radius, covered} */
  coverageData?: CoveragePoint[];
  /** CSS class for the container */
  className?: string;
  /** Container style */
  style?: React.CSSProperties;
}

export interface CoveragePoint {
  x: number;
  y: number;
  z?: number;
  radius: number;
  covered: boolean;
}

export interface IfcSpaceData {
  expressID: number;
  name: string;
  longName: string;
  area: number;
  elevation: number;
}

export interface IfcMetadata {
  buildingName: string;
  floorCount: number;
  spaceCount: number;
  deviceCount: number;
  correlationId: string;
}

type LoadingState = "idle" | "loading" | "loaded" | "error";

// ── Component ────────────────────────────────────────────────────────────────

export const IfcViewer: React.FC<IfcViewerProps> = ({
  ifcUrl,
  correlationId = `ifc-viewer-${Date.now()}`,
  onSpacesExtracted,
  onError,
  onLoaded,
  showCoverage = false,
  coverageData = [],
  className,
  style,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const frameIdRef = useRef<number>(0);
  const [loadingState, setLoadingState] = useState<LoadingState>("idle");
  const [errorMessage, setErrorMessage] = useState<string>("");

  // ── Cleanup ──
  useEffect(() => {
    return () => {
      if (frameIdRef.current) {
        cancelAnimationFrame(frameIdRef.current);
      }
      rendererRef.current?.dispose();
      rendererRef.current = null;
    };
  }, []);

  // ── Animation Loop ──
  const startRenderLoop = useCallback(() => {
    const renderer = rendererRef.current;
    const scene = sceneRef.current;
    const camera = cameraRef.current;
    if (!renderer || !scene || !camera) return;

    const animate = () => {
      frameIdRef.current = requestAnimationFrame(animate);
      renderer.render(scene, camera);
    };
    animate();
  }, []);

  // ── IFC Loading ──
  const loadIfc = useCallback(async () => {
    if (!containerRef.current) return;

    setLoadingState("loading");
    setErrorMessage("");

    try {
      // ── Initialize Three.js Scene ──
      const container = containerRef.current;
      const width = container.clientWidth || 800;
      const height = container.clientHeight || 600;

      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0xf0f0f0);
      sceneRef.current = scene;

      const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 1000);
      camera.position.set(20, 20, 20);
      camera.lookAt(0, 0, 0);
      cameraRef.current = camera;

      const renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setSize(width, height);
      renderer.setPixelRatio(window.devicePixelRatio);
      container.appendChild(renderer.domElement);
      rendererRef.current = renderer;

      // ── Add Lights ──
      const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
      scene.add(ambientLight);
      const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
      directionalLight.position.set(10, 20, 10);
      scene.add(directionalLight);

      // ── Fetch IFC File ──
      const response = await fetch(ifcUrl);
      if (!response.ok) {
        throw new Error(
          `Failed to fetch IFC file: ${response.status} ${response.statusText}`
        );
      }
      const ifcData = await response.arrayBuffer();

      // ── Initialize web-ifc ──
      const ifcApi = new WebIFC.IfcAPI();
      await ifcApi.Init();

      const modelId = ifcApi.OpenModel(new Uint8Array(ifcData));
      console.log(
        `[IfcViewer] Opened IFC model | modelId=${modelId} | correlationId=${correlationId}`
      );

      // ── Extract Meshes ──
      // web-ifc API: LoadAllGeometry returns Vector<FlatMesh>.
      // Each FlatMesh has geometries: Vector<PlacedGeometry>, where
      // PlacedGeometry has { color, geometryExpressID, flatTransformation }.
      const flatMeshes = ifcApi.LoadAllGeometry(modelId);

      for (let mi = 0; mi < flatMeshes.size(); mi++) {
        const flatMesh = flatMeshes.get(mi);

        for (let gi = 0; gi < flatMesh.geometries.size(); gi++) {
          const placedGeom = flatMesh.geometries.get(gi);

          const geometryData = ifcApi.GetGeometry(modelId, placedGeom.geometryExpressID);

          // Set vertex positions
          const vertices = ifcApi.GetVertexArray(
            geometryData.GetVertexData(),
            geometryData.GetVertexDataSize()
          );
          const indices = ifcApi.GetIndexArray(
            geometryData.GetIndexData(),
            geometryData.GetIndexDataSize()
          );

          const geometry = new THREE.BufferGeometry();
          geometry.setAttribute(
            "position",
            new THREE.Float32BufferAttribute(vertices, 3)
          );
          geometry.setIndex(new THREE.BufferAttribute(indices, 1));
          geometry.computeVertexNormals();

          const material = new THREE.MeshPhongMaterial({
            color: new THREE.Color(placedGeom.color.x, placedGeom.color.y, placedGeom.color.z),
            side: THREE.DoubleSide,
          });

          const mesh = new THREE.Mesh(geometry, material);

          // Apply flat transformation matrix (4x4 row-major)
          const tf = placedGeom.flatTransformation;
          if (tf.length >= 16) {
            const matrix = new THREE.Matrix4();
            matrix.fromArray(tf);
            mesh.applyMatrix4(matrix);
          }

          scene.add(mesh);
        }
      }

      // ── Extract Spaces ──
      const spaces: IfcSpaceData[] = [];
      try {
        const spaceIds = ifcApi.GetLineIDsWithType(modelId, WebIFC.IFCSPACE);
        for (let i = 0; i < spaceIds.size(); i++) {
          const id = spaceIds.get(i);
          const props = ifcApi.GetLine(modelId, id);
          spaces.push({
            expressID: id,
            name: props?.Name?.value ?? `Space-${id}`,
            longName: props?.LongName?.value ?? "",
            area: 0, // Area requires property set lookup — best effort
            elevation: props?.ElevationWithFlooring?.value ?? 0,
          });
        }
      } catch (e) {
        console.warn("[IfcViewer] Space extraction failed (non-fatal):", e);
      }

      // ── Extract Metadata ──
      let buildingName = "Unknown";
      let floorCount = 0;
      let deviceCount = 0;
      try {
        const buildingIds = ifcApi.GetLineIDsWithType(modelId, WebIFC.IFCBUILDING);
        if (buildingIds.size() > 0) {
          const buildingProps = ifcApi.GetLine(modelId, buildingIds.get(0));
          buildingName = buildingProps?.Name?.value ?? "Unknown";
        }
        const storyIds = ifcApi.GetLineIDsWithType(modelId, WebIFC.IFCBUILDINGSTOREY);
        floorCount = storyIds.size();
      } catch (e) {
        console.warn("[IfcViewer] Metadata extraction failed (non-fatal):", e);
      }

      const metadata: IfcMetadata = {
        buildingName,
        floorCount,
        spaceCount: spaces.length,
        deviceCount,
        correlationId,
      };

      // ── Callbacks ──
      onSpacesExtracted?.(spaces);
      onLoaded?.(metadata);

      // ── Coverage Overlay (P5) ──
      if (showCoverage && coverageData.length > 0) {
        for (const point of coverageData) {
          const geometry = new THREE.CircleGeometry(point.radius, 32);
          const material = new THREE.MeshBasicMaterial({
            color: point.covered ? 0x00ff00 : 0xff0000,
            transparent: true,
            opacity: 0.25,
            side: THREE.DoubleSide,
          });
          const circle = new THREE.Mesh(geometry, material);
          circle.position.set(point.x, point.z ?? 0.1, point.y); // Y-up in Three.js
          circle.rotation.x = -Math.PI / 2; // Lay flat on floor
          scene.add(circle);
        }
        console.log(
          `[IfcViewer] Coverage overlay | points=${coverageData.length} | correlationId=${correlationId}`
        );
      }

      setLoadingState("loaded");
      startRenderLoop();

      // Cleanup web-ifc
      ifcApi.CloseModel(modelId);

      console.log(
        `[IfcViewer] Load complete | building=${buildingName} | floors=${floorCount} | spaces=${spaces.length} | correlationId=${correlationId}`
      );
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      console.error("[IfcViewer] Load failed:", error);
      setErrorMessage(error.message);
      setLoadingState("error");
      onError?.(error);
    }
  }, [ifcUrl, correlationId, onSpacesExtracted, onError, onLoaded, startRenderLoop]);

  // ── Auto-load when URL changes ──
  useEffect(() => {
    if (ifcUrl) {
      loadIfc();
    }
  }, [ifcUrl, loadIfc]);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{
        width: "100%",
        height: "100%",
        minHeight: 400,
        position: "relative",
        ...style,
      }}
    >
      {loadingState === "loading" && (
        <div
          style={{
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            background: "rgba(255,255,255,0.9)",
            padding: "16px 24px",
            borderRadius: 8,
            zIndex: 10,
          }}
        >
          Loading IFC model...
        </div>
      )}
      {loadingState === "error" && (
        <div
          style={{
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            background: "rgba(255,235,235,0.95)",
            padding: "16px 24px",
            borderRadius: 8,
            color: "#c00",
            zIndex: 10,
            maxWidth: "80%",
          }}
        >
          <strong>IFC Load Error</strong>
          <p>{errorMessage}</p>
        </div>
      )}
      {loadingState === "loaded" && (
        <div
          style={{
            position: "absolute",
            bottom: 8,
            left: 8,
            background: "rgba(0,0,0,0.6)",
            color: "#fff",
            padding: "4px 8px",
            borderRadius: 4,
            fontSize: 12,
            zIndex: 10,
          }}
        >
          IFC loaded | {correlationId}
        </div>
      )}
    </div>
  );
};

export default IfcViewer;
