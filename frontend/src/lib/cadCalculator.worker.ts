/**
 * @file cadCalculator.worker.ts
 * @description Web Worker for heavy engineering calculations (Load Flow, Voltage Drop).
 *
 * V194 (TD-4) FIX: Implemented real Newton-Raphson power-flow algorithm for
 * a 2-bus radial system (slack bus + PQ load bus). The previous code was a
 * placeholder that iterated 5 times with a fixed formula — it did NOT solve
 * the power-flow equations and was explicitly marked "NOT for engineering
 * decisions".
 *
 * The Newton-Raphson method iteratively solves the nonlinear power-flow
 * equations:
 *   P = V * I*  (complex power)
 *   I = Y * V   (Ohm's law in admittance form)
 *
 * For a 2-bus system with slack bus (bus 1, V=1.0∠0°) and PQ load bus
 * (bus 2, P and Q specified), the Jacobian reduces to a 2×2 matrix:
 *
 *   [ΔP]   [∂P/∂θ   ∂P/∂V] [Δθ]
 *   [ΔQ] = [∂Q/∂θ   ∂Q/∂V] [ΔV]
 *
 * We solve J · [Δθ, ΔV]ᵀ = [ΔP, ΔQ]ᵀ and update [θ, V] until mismatch < ε.
 *
 * Reference: J. Duncan Glover, Mulukutla S. Sarma, "Power System Analysis
 * and Design", Chapter 6 (Newton-Raphson Power Flow).
 *
 * SAFETY NOTE: This is still a 2-bus simplified model. For real power-system
 * analysis with N buses, use a dedicated library (e.g., pandapower on the
 * backend). This worker is for quick UI feedback only.
 */

interface LoadFlowInput {
  voltage: number;      // Nominal line voltage (V)
  current: number;      // Load current magnitude (A)
  frequency: number;    // System frequency (Hz) — used for reactance calc
}

interface LoadFlowResult {
  voltageDropPercent: number;
  lineLosses: number;        // kW
  powerFactor: number;
  calculatedVoltage: number; // V at load bus
  isCritical: boolean;
  iterations: number;
  converged: boolean;
  timestamp: string;
}

/**
 * Solve a 2×2 linear system: J · x = b
 * Returns null if the matrix is singular (non-invertible).
 */
function solve2x2(
  j: [number, number, number, number],  // [a, b, c, d] row-major
  b: [number, number],
): [number, number] | null {
  const [a, bb, c, d] = j;
  const det = a * d - bb * c;
  if (Math.abs(det) < 1e-12) {
    return null;  // Singular — Newton-Raphson fails
  }
  const x1 = (d * b[0] - bb * b[1]) / det;
  const x2 = (-c * b[0] + a * b[1]) / det;
  return [x1, x2];
}

/**
 * Newton-Raphson power-flow for a 2-bus radial system.
 *
 * Bus 1 (slack): V1 = 1.0 pu (per-unit), θ1 = 0°
 * Bus 2 (PQ):   P2, Q2 specified; V2, θ2 unknown
 *
 * Line: series impedance Z = R + jX (per-unit)
 *
 * Power-flow equations (pu):
 *   P2 = V2² · G22 - V1·V2·(G21·cos(θ2-θ1) + B21·sin(θ2-θ1))
 *   Q2 = -V2² · B22 - V1·V2·(G21·sin(θ2-θ1) - B21·cos(θ2-θ1))
 *
 * where Y21 = G21 + jB21 = 1/Z (admittance), Y22 = 1/Z.
 */
function newtonRaphson2Bus(
  P2_pu: number,   // Specified real power at bus 2 (pu)
  Q2_pu: number,   // Specified reactive power at bus 2 (pu)
  R_pu: number,    // Line resistance (pu)
  X_pu: number,    // Line reactance (pu)
  V1_pu: number,   // Slack bus voltage magnitude (pu, typically 1.0)
  maxIter: number, // Max iterations
  tolerance: number, // Convergence tolerance (pu)
): { V2: number; theta2: number; iterations: number; converged: boolean } {
  // Admittance Y = 1/Z = 1/(R+jX) = (R-jX)/(R²+X²)
  const denom = R_pu * R_pu + X_pu * X_pu;
  const G21 = R_pu / denom;   // Real part of Y21
  const B21 = -X_pu / denom;  // Imaginary part of Y21
  const G22 = G21;            // Y22 = Y21 for a single line
  const B22 = B21;

  // Initial guess: V2 = 1.0 pu, θ2 = 0
  let V2 = 1.0;
  let theta2 = 0.0;

  for (let iter = 0; iter < maxIter; iter++) {
    const cosT = Math.cos(theta2);
    const sinT = Math.sin(theta2);

    // Power mismatch (calculated - specified)
    const P2_calc =
      V2 * V2 * G22 - V1_pu * V2 * (G21 * cosT + B21 * sinT);
    const Q2_calc =
      -V2 * V2 * B22 - V1_pu * V2 * (G21 * sinT - B21 * cosT);
    const dP = P2_calc - P2_pu;
    const dQ = Q2_calc - Q2_pu;

    // Convergence check
    if (Math.abs(dP) < tolerance && Math.abs(dQ) < tolerance) {
      return { V2, theta2, iterations: iter + 1, converged: true };
    }

    // Jacobian elements (2×2) for a 2-bus system
    // Reference: Glover & Sarma, Eq. 6.4.4–6.4.7
    const J11 = V1_pu * V2 * (G21 * sinT - B21 * cosT);           // ∂P2/∂θ2
    const J12 = -V1_pu * V2 * (G21 * cosT + B21 * sinT) + 2 * V2 * G22;  // ∂P2/∂V2 (note: V2 scaling omitted in simplified form)
    const J21 = -V1_pu * V2 * (G21 * cosT + B21 * sinT);          // ∂Q2/∂θ2
    const J22 = V1_pu * V2 * (G21 * sinT - B21 * cosT) + 2 * V2 * (-B22);  // ∂Q2/∂V2

    // Solve J · [Δθ2, ΔV2]ᵀ = -[dP, dQ]ᵀ  (Newton correction)
    const correction = solve2x2(
      [J11, J12, J21, J22],
      [-dP, -dQ],
    );
    if (!correction) {
      // Singular Jacobian — fall back to current values
      return { V2, theta2, iterations: iter + 1, converged: false };
    }

    theta2 += correction[0];
    V2 += correction[1];

    // Keep V2 in a sane range (avoid divergence)
    if (V2 < 0.5 || V2 > 1.5 || !isFinite(V2)) {
      return { V2: Math.max(0.5, Math.min(1.5, V2 || 1.0)), theta2, iterations: iter + 1, converged: false };
    }
  }

  return { V2, theta2, iterations: maxIter, converged: false };
}

self.onmessage = (e: MessageEvent) => {
  const { type, data } = e.data;

  if (type === "calculate_load_flow") {
    const { voltage, current, frequency } = data as LoadFlowInput;

    // Line parameters (per-unit on a 100 MVA base, scaled to the load)
    // R = 0.5 Ω, X = 2π·f·L with L≈0.637 mH → X ≈ 0.2 Ω at 50 Hz
    const R_ohms = 0.5;
    const X_ohms = 2 * Math.PI * frequency * 0.000637;
    const PF = 0.85;

    // Base values for per-unit conversion
    const baseVoltage = voltage;       // Nominal voltage (V)
    const baseImpedance = baseVoltage / Math.max(current, 0.001);  // Z_base = V/I
    const R_pu = R_ohms / baseImpedance;
    const X_pu = X_ohms / baseImpedance;

    // Load power (SI → per-unit)
    // S = V·I*, P = S·PF, Q = S·sin(acos(PF))
    const S_va = voltage * current;
    const P2_pu = (S_va * PF) / (voltage * current);  // = PF (since base MVA = V·I)
    const Q2_pu = (S_va * Math.sin(Math.acos(PF))) / (voltage * current);

    // Run Newton-Raphson power flow
    const result = newtonRaphson2Bus(
      P2_pu,
      Q2_pu,
      R_pu,
      X_pu,
      1.0,        // V1 (slack) = 1.0 pu
      20,         // max iterations
      1e-6,       // tolerance (pu)
    );

    // Convert back to SI units
    const calculatedVoltage = result.V2 * baseVoltage;
    const voltageDrop = voltage - calculatedVoltage;
    const voltageDropPercent = (voltageDrop / baseVoltage) * 100;
    const lineLosses = (current * current * R_ohms) / 1000;  // I²R in kW

    // Critical if voltage drops below 90% of nominal
    const isCritical = calculatedVoltage < 0.9 * baseVoltage;

    const output: LoadFlowResult = {
      voltageDropPercent,
      lineLosses,
      powerFactor: PF,
      calculatedVoltage,
      isCritical,
      iterations: result.iterations,
      converged: result.converged,
      timestamp: new Date().toLocaleTimeString(),
    };

    self.postMessage({ type: "result", data: output });
  }
};
