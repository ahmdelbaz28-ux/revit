import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { useFaultLogic } from "../useFaultLogic";
import { setState } from "@/store/simpleStore";

describe("useFaultLogic", () => {
  beforeEach(() => {
    // Reset store state before each test
    setState({
      theme: 'dark',
      faults: [],
      helpOpen: false,
      liveData: {
        voltage: 220.5,
        current: 15.2,
        frequency: 50.0,
      },
      eventLogs: [],
      dataMode: 'mock',
      connectionStatus: 'connected',
    });
  });

  it("should add a fault when toggled", () => {
    const { result } = renderHook(() => useFaultLogic());
    
    act(() => {
      result.current.toggleFault("test-fault");
    });

    expect(result.current.isFaulty("test-fault")).toBe(true);
  });

  it("should remove a fault when toggled again", () => {
    const { result } = renderHook(() => useFaultLogic());
    
    // Add first
    act(() => {
      result.current.toggleFault("test-fault");
    });
    expect(result.current.isFaulty("test-fault")).toBe(true);

    // Remove
    act(() => {
      result.current.toggleFault("test-fault");
    });
    expect(result.current.isFaulty("test-fault")).toBe(false);
  });

  it("should check if a component is faulty", () => {
    const { result } = renderHook(() => useFaultLogic());
    
    expect(result.current.isFaulty("non-existent")).toBe(false);
    
    act(() => {
      result.current.toggleFault("non-existent");
    });
    
    expect(result.current.isFaulty("non-existent")).toBe(true);
  });
});
