import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useTelemetryStream } from "../useTelemetryStream";
import { dataService } from "@/services/dataService";
import { setState } from "@/store/simpleStore";

describe("useTelemetryStream", () => {
  beforeEach(() => {
    setState({
      dataMode: 'mock',
      connectionStatus: 'connected',
    });
    vi.clearAllMocks();
  });

  it("should cleanup resources correctly after 100 mount/unmount cycles", () => {
    const disconnectSpy = vi.spyOn(dataService, "disconnect");
    
    // Set to live to trigger connect/disconnect
    setState({ dataMode: 'live' });

    for (let i = 0; i < 100; i++) {
      const { unmount } = renderHook(() => useTelemetryStream());
      unmount();
    }

    // Each unmount should call disconnect.
    expect(disconnectSpy).toHaveBeenCalledTimes(100);
  });

  it("should update connectionStatus on disconnect", () => {
    const { result } = renderHook(() => useTelemetryStream());
    
    act(() => {
      setState({ connectionStatus: 'disconnected' });
    });

    expect(result.current.connectionStatus).toBe('disconnected');
  });
});
