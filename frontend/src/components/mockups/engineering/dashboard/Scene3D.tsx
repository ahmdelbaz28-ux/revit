import { useEffect, useRef, useMemo } from "react";
import * as THREE from "three";
import { OrbitControls as OrbitControlsClass } from "three/examples/jsm/controls/OrbitControls.js";
type OrbitControlsType = InstanceType<typeof OrbitControlsClass>;

export function Scene3D() {
  const containerRef = useRef<HTMLDivElement>(null);
  const resourcesRef = useRef<{
    renderer?: THREE.WebGLRenderer;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    controls?: any;
    animationId?: number;
  }>({});

  // Use useMemo for geometries and materials to prevent recreation on re-renders
  // as strictly requested by the consultant.
  const geometry = useMemo(() => new THREE.BoxGeometry(1, 1, 1), []);
  const genMaterial = useMemo(() => new THREE.MeshStandardMaterial({ color: "#f59e0b" }), []);
  const batMaterial = useMemo(() => new THREE.MeshStandardMaterial({ color: "#10b981" }), []);
  const loadMaterial = useMemo(() => new THREE.MeshStandardMaterial({ color: "#3b82f6" }), []);
  
  const planeGeo = useMemo(() => new THREE.PlaneGeometry(10, 10), []);
  const planeMat = useMemo(() => new THREE.MeshStandardMaterial({ color: "#1e293b" }), []);

  useEffect(() => {
    if (!containerRef.current) return;

    // Performance monitoring
    performance.mark('Scene3D-Mount');

    const width = containerRef.current.clientWidth;
    const height = containerRef.current.clientHeight;

    // Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#0f172a"); // Slate 900

    // Camera
    const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000);
    camera.position.set(5, 5, 5);

    // Renderer - Performance Tuning
    const useAntialias = navigator.hardwareConcurrency > 4;
    const renderer = new THREE.WebGLRenderer({ antialias: useAntialias });
    renderer.setSize(width, height);
    renderer.shadowMap.enabled = true;
    containerRef.current.appendChild(renderer.domElement);
    resourcesRef.current.renderer = renderer;

    // Controls
    const controls = new OrbitControlsClass(camera, renderer.domElement);
    controls.enableDamping = true;
    resourcesRef.current.controls = controls;

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(10, 10, 10);
    dirLight.castShadow = true;
    scene.add(dirLight);

    // Objects (Generator, Battery, Load)
    const generator = new THREE.Mesh(geometry, genMaterial);
    generator.position.set(-2, 0, 0);
    generator.castShadow = true;
    scene.add(generator);

    const battery = new THREE.Mesh(geometry, batMaterial);
    battery.position.set(0, 0, 0);
    battery.castShadow = true;
    scene.add(battery);

    const load = new THREE.Mesh(geometry, loadMaterial);
    load.position.set(2, 0, 0);
    load.castShadow = true;
    scene.add(load);

    // Ground plane
    const plane = new THREE.Mesh(planeGeo, planeMat);
    plane.rotation.x = -Math.PI / 2;
    plane.position.y = -0.6;
    plane.receiveShadow = true;
    scene.add(plane);

    // Animation loop
    const animate = () => {
      resourcesRef.current.animationId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };

    animate();

    // Measure performance
    performance.measure('Scene3D-Init', 'Scene3D-Mount');
    const measure = performance.getEntriesByName('Scene3D-Init')[0];
    if (import.meta.env.DEV) console.log(`[Scene3D] Mounted and initialized in ${measure.duration.toFixed(2)}ms`);
    performance.clearMarks('Scene3D-Mount');
    performance.clearMeasures('Scene3D-Init');

    // Handle resize
    const handleResize = () => {
      if (!containerRef.current) return;
      const w = containerRef.current.clientWidth;
      const h = containerRef.current.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };

    window.addEventListener("resize", handleResize);

    return () => {
      // Cleanup
      const resources = resourcesRef.current;
      
      if (resources.animationId) {
        cancelAnimationFrame(resources.animationId);
      }
      
      if (resources.controls) {
        resources.controls.dispose();
      }
      
      // Dispose geometries and materials passed from useMemo
      geometry.dispose();
      genMaterial.dispose();
      batMaterial.dispose();
      loadMaterial.dispose();
      planeGeo.dispose();
      planeMat.dispose();
      
      if (resources.renderer) {
        if (resources.renderer.domElement) {
          resources.renderer.domElement.remove();
        }
        resources.renderer.dispose();
      }
      
      window.removeEventListener("resize", handleResize);
    };
  }, [geometry, genMaterial, batMaterial, loadMaterial, planeGeo, planeMat]);

  return <div ref={containerRef} className="w-full h-full" />;
}

export default Scene3D;
