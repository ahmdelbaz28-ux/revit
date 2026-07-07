// NOSONAR
/**
 * @file mockWorker.ts
 * @description Web Worker that simulates the backend server sending live telemetry data.
 */

let intervalId: number | null = null;
let time = 0; // Represents time of day (0 to 24 hours mapped to 0-60 seconds)

self.onmessage = (e) => {
	const { type } = e.data;

	if (type === "start") {
		if (intervalId) return;

		intervalId = self.setInterval(() => {
			time = (time + 1) % 60; // Loop every 60 seconds
			const hour = (time / 60) * 24;

			// Load Curve Simulation: Peak at noon (12:00)
			const loadFactor = Math.sin((hour / 24) * Math.PI); // 0 at start/end, 1 at noon

			const baseCurrent = 10;
			const peakCurrent = 30;
			const current =
				baseCurrent + peakCurrent * loadFactor + (crypto.getRandomValues(new Uint32Array(1))[0] / 0xFFFFFFFF - 0.5);

			// Voltage drops slightly with high current (simulation)
			const baseVoltage = 225;
			const voltage =
				baseVoltage - (current - baseCurrent) * 0.5 + (crypto.getRandomValues(new Uint32Array(1))[0] / 0xFFFFFFFF - 0.5);

			// Frequency stays around 50Hz
			const frequency = 50.0 + (crypto.getRandomValues(new Uint32Array(1))[0] / 0xFFFFFFFF - 0.5) * 0.1;

			// Check for simulated faults at peak load
			let fault = null;
			if (hour > 11 && hour < 13 && crypto.getRandomValues(new Uint32Array(1))[0] / 0xFFFFFFFF > 0.95) {
				fault = "gen-01"; // Overload fault at peak
			}

			// Send data back to the main thread
			self.postMessage({
				type: "data",
				data: {
					voltage,
					current,
					frequency,
					hour,
					fault,
				},
			});
		}, 1000) as unknown as number;
	} else if (type === "stop") {
		if (intervalId) {
			clearInterval(intervalId);
			intervalId = null;
		}
	}
};
