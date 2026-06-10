import { actions } from "@/store/simpleStore";

export class DataService {
  private static instance: DataService;
  private buffer: any[] = [];
  private maxBufferSize = 50;
  private reconnectInterval = 5000;
  private isConnected = false;
  private worker: Worker | null = null;

  private constructor() {}

  public static getInstance(): DataService {
    if (!DataService.instance) {
      DataService.instance = new DataService();
    }
    return DataService.instance;
  }

  public connect() {
    if (this.isConnected) return;

    actions.addLog("Attempting to connect to Live Data Server...");
    
    setTimeout(() => {
      this.simulateConnection();
    }, 1000);
  }

  private simulateConnection() {
    this.isConnected = true;
    actions.setConnectionStatus("connected");
    actions.addLog("Connected to Live Data Server (MOCK WORKER).");

    if (this.buffer.length > 0) {
      actions.addLog(`[SYSTEM] Restored ${this.buffer.length} buffered readings. Data Gap detected.`);
      this.buffer = []; // Clear buffer after restoring
    }

    // Initialize Worker
    this.worker = new Worker(new URL("./mockWorker.ts", import.meta.url), { type: "module" });
    this.worker.postMessage({ type: "start" });
    
    this.worker.onmessage = (e) => {
      const { type, data } = e.data;
      if (type === "data") {
        this.handleData(data);
      }
    };
  }

  public disconnect() {
    this.isConnected = false;
    actions.setConnectionStatus("disconnected");
    actions.addLog("Disconnected from Live Data Server.");
    
    if (this.worker) {
      this.worker.postMessage({ type: "stop" });
      this.worker.terminate();
      this.worker = null;
    }
  }

  private handleData = (data: any) => {
    if (!this.isConnected) {
      // Buffer data if disconnected
      if (this.buffer.length < this.maxBufferSize) {
        this.buffer.push(data);
      }
      return;
    }

    // Update store
    actions.updateLiveData({
      voltage: data.voltage,
      current: data.current,
      frequency: data.frequency
    });

    // Randomly inject faults based on server data if needed
    if (data.fault) {
      actions.addFault(data.fault);
      actions.addLog(`CRITICAL: Server reported fault on ${data.fault}`);
    }
  };

  // Method to simulate network drop for testing
  public simulateDrop() {
    if (!this.isConnected) return;
    
    this.isConnected = false;
    actions.setConnectionStatus("disconnected");
    actions.addLog("Connection lost! Buffering incoming data...");
    
    if (this.worker) {
      this.worker.postMessage({ type: "stop" });
    }

    // Auto reconnect after some time
    setTimeout(() => {
      this.connect();
    }, this.reconnectInterval);
  }
}

export const dataService = DataService.getInstance();
