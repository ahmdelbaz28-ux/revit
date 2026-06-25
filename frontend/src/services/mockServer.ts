/**
 * @file mockServer.ts
 * @description Simulates a backend server sending live telemetry data with a load curve.
 */

let intervalId: number | null = null;
let time = 0; // Represents time of day (0 to 24 hours mapped to 0-60 seconds)

export const startMockServer = () => {
  if (intervalId) return;

  intervalId = window.setInterval(() => {
    time = (time + 1) % 60; // Loop every 60 seconds
    const hour = (time / 60) * 24;

    // Load Curve Simulation: Peak at noon (12:00)
    // Using a sine wave mapped to the day
    const loadFactor = Math.sin((hour / 24) * Math.PI); // 0 at start/end, 1 at noon
    
    const baseCurrent = 10;
    const peakCurrent = 30;
    const current = baseCurrent + peakCurrent * loadFactor + (Math.random() - 0.5);
    
    // Voltage drops slightly with high current (simulation)
    const baseVoltage = 225;
    const voltage = baseVoltage - (current - baseCurrent) * 0.5 + (Math.random() - 0.5);
    
    // Frequency stays around 50Hz
    const frequency = 50.0 + (Math.random() - 0.5) * 0.1;

    // Check for simulated faults at peak load
    let fault = null;
    if (hour > 11 && hour < 13 && Math.random() > 0.95) {
      fault = "gen-01"; // Overload fault at peak
    }

    // Dispatch custom event to simulate WebSocket message
    const event = new CustomEvent("mock-server-data", {
      detail: {
        voltage,
        current,
        frequency,
        hour,
        fault
      }
    });
    
    window.dispatchEvent(event);
  }, 1000); // Send data every second
};

export const stopMockServer = () => {
  if (intervalId) {
    clearInterval(intervalId);
    intervalId = null;
  }
};
