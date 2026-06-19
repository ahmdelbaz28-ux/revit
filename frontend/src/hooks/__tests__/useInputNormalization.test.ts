/**
 * frontend/src/hooks/__tests__/useInputNormalization.test.ts
 * ==========================================================
 * Unit tests for the useInputNormalization hook.
 *
 * Tests the header detection, toast display, and per-session
 * deduplication logic.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

// Mock the toast function so we can assert it was called.
const mockToast = vi.fn();
vi.mock('@/hooks/use-toast', () => ({
  toast: mockToast,
}));

import { useInputNormalization } from '../useInputNormalization';

describe('useInputNormalization', () => {
  let originalFetch: typeof window.fetch;

  beforeEach(() => {
    // Save original fetch.
    originalFetch = window.fetch;
    // Clear sessionStorage.
    sessionStorage.clear();
    // Reset mock.
    mockToast.mockClear();
  });

  afterEach(() => {
    // Restore original fetch.
    window.fetch = originalFetch;
  });

  it('initializes with wasNormalized=false', () => {
    const { result } = renderHook(() => useInputNormalization());
    expect(result.current.wasNormalized).toBe(false);
  });

  it('does not show toast when no normalized response was received', () => {
    const { result } = renderHook(() => useInputNormalization());
    act(() => {
      result.current.showIfNormalized();
    });
    expect(mockToast).not.toHaveBeenCalled();
  });

  it('shows toast when header was detected', async () => {
    // Mock fetch to return a response with the normalization header.
    const mockResponse = new Response('{}', {
      headers: { 'x-input-normalization': 'enabled' },
    });
    window.fetch = vi.fn().mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useInputNormalization());

    // Trigger a fetch so the interceptor sees the header.
    await act(async () => {
      await fetch('https://test.local/api');
    });

    // Wait for state to update.
    await waitFor(() => {
      expect(result.current.wasNormalized).toBe(true);
    });

    // Now showIfNormalized should trigger the toast.
    act(() => {
      result.current.showIfNormalized();
    });
    expect(mockToast).toHaveBeenCalledTimes(1);
    expect(mockToast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: expect.any(String),
        description: expect.any(String),
        duration: expect.any(Number),
      })
    );
  });

  it('does not show toast twice in the same session by default', async () => {
    const mockResponse = new Response('{}', {
      headers: { 'x-input-normalization': 'enabled' },
    });
    window.fetch = vi.fn().mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useInputNormalization());

    // First call: trigger fetch + show toast.
    await act(async () => {
      await fetch('https://test.local/api');
    });
    await waitFor(() => expect(result.current.wasNormalized).toBe(true));
    act(() => {
      result.current.showIfNormalized();
    });
    expect(mockToast).toHaveBeenCalledTimes(1);

    // Second call: trigger another fetch + try to show toast again.
    await act(async () => {
      await fetch('https://test.local/api');
    });
    await waitFor(() => expect(result.current.wasNormalized).toBe(true));
    act(() => {
      result.current.showIfNormalized();
    });
    // Should NOT have been called again (once-per-session).
    expect(mockToast).toHaveBeenCalledTimes(1);
  });

  it('shows toast twice when oncePerSession=false', async () => {
    const mockResponse = new Response('{}', {
      headers: { 'x-input-normalization': 'enabled' },
    });
    window.fetch = vi.fn().mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useInputNormalization());

    // First call.
    await act(async () => {
      await fetch('https://test.local/api');
    });
    await waitFor(() => expect(result.current.wasNormalized).toBe(true));
    act(() => {
      result.current.showIfNormalized({ oncePerSession: false });
    });

    // Second call.
    await act(async () => {
      await fetch('https://test.local/api');
    });
    await waitFor(() => expect(result.current.wasNormalized).toBe(true));
    act(() => {
      result.current.showIfNormalized({ oncePerSession: false });
    });

    expect(mockToast).toHaveBeenCalledTimes(2);
  });

  it('resetSession clears the per-session flag', async () => {
    const mockResponse = new Response('{}', {
      headers: { 'x-input-normalization': 'enabled' },
    });
    window.fetch = vi.fn().mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useInputNormalization());

    // Show toast once.
    await act(async () => {
      await fetch('https://test.local/api');
    });
    await waitFor(() => expect(result.current.wasNormalized).toBe(true));
    act(() => {
      result.current.showIfNormalized();
    });
    expect(mockToast).toHaveBeenCalledTimes(1);

    // Reset.
    act(() => {
      result.current.resetSession();
    });

    // Trigger again — toast should appear now.
    await act(async () => {
      await fetch('https://test.local/api');
    });
    await waitFor(() => expect(result.current.wasNormalized).toBe(true));
    act(() => {
      result.current.showIfNormalized();
    });
    expect(mockToast).toHaveBeenCalledTimes(2);
  });

  it('does not set wasNormalized when header is absent', async () => {
    // Mock fetch to return a response WITHOUT the header.
    const mockResponse = new Response('{}', { headers: {} });
    window.fetch = vi.fn().mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useInputNormalization());

    await act(async () => {
      await fetch('https://test.local/api');
    });

    // State should remain false.
    expect(result.current.wasNormalized).toBe(false);
  });

  it('does not set wasNormalized when header has wrong value', async () => {
    const mockResponse = new Response('{}', {
      headers: { 'x-input-normalization': 'disabled' },
    });
    window.fetch = vi.fn().mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useInputNormalization());

    await act(async () => {
      await fetch('https://test.local/api');
    });

    expect(result.current.wasNormalized).toBe(false);
  });

  it('preserves the original fetch behavior (returns Response)', async () => {
    const mockResponse = new Response('{"hello":"world"}', {
      headers: { 'content-type': 'application/json' },
    });
    window.fetch = vi.fn().mockResolvedValue(mockResponse);

    renderHook(() => useInputNormalization());

    const response = await fetch('https://test.local/api');
    expect(response).toBeInstanceOf(Response);
    const body = await response.json();
    expect(body).toEqual({ hello: 'world' });
  });
});
