/**
 * @file cadCalculator.worker.ts
 * @description Web Worker for heavy engineering calculations (Load Flow, Voltage Drop).
 */

self.onmessage = (e) => {
  const { type, data } = e.data;

  if (type === "calculate_load_flow") {
    const { voltage, current, frequency } = data;
    
    // Parameters for the simulation
    const R = 0.5; // Line Resistance in Ohms
    const X = 0.2; // Line Reactance in Ohms
    const PF = 0.85; // Power Factor
    
    const baseVoltage = 220; // Nominal Voltage
    
    // Calculate active and reactive current
    const theta = Math.acos(PF);
    const I_active = current * PF;
    const I_reactive = current * Math.sin(theta);

    // ===================================================================
    // TODO: IMPLEMENT REAL NEWTON-RAPHSON POWER FLOW ALGORITHM.
    // The following is a PLACEHOLDER simulation and NOT for engineering decisions.
    // ===================================================================
    let calculatedVoltage = voltage;
    let voltageDrop = 0;
    let lineLosses = 0;
    const iterations = 5;

    for (let i = 0; i < iterations; i++) {
      // Complex power calculation simulation
      voltageDrop = (I_active * R + I_reactive * X) / (calculatedVoltage / baseVoltage);
      calculatedVoltage = voltage - voltageDrop;
      
      // Calculate line losses: I^2 * R
      lineLosses = Math.pow(current, 2) * R / 1000; // in kW
    }

    const voltageDropPercent = (voltageDrop / baseVoltage) * 100;
    
    // Check for critical warning (Voltage drops below 90% of nominal, which is 198V)
    const isCritical = calculatedVoltage < 198;

    // Simulate some work time to justify the worker
    const start = Date.now();
    while (Date.now() - start < 50) {
      // Busy wait 50ms
    }

    self.postMessage({
      type: "result",
      data: {
        voltageDropPercent,
        lineLosses,
        powerFactor: PF,
        calculatedVoltage,
        isCritical,
        timestamp: new Date().toLocaleTimeString()
      }
    });
  }
};
