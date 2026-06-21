/**
 * frontend/src/hooks/useInputNormalization.ts
 * ===========================================
 * Detects when the backend has normalized user input (Arabic-mistype →
 * English QWERTY recovery) by inspecting the `X-Input-Normalization`
 * response header, and surfaces a "Did you mean?" toast to the user.
 *
 * Phase 3 of the input-normalization feature.
 *
 * USAGE:
 *   // In any component that calls the API:
 *   import { useInputNormalization } from '@/hooks/useInputNormalization';
 *   const { showIfNormalized } = useInputNormalization();
 *
 *   // After an API call:
 *   const project = await api.createProject({...});
 *   showIfNormalized();  // shows toast if X-Input-Normalization: enabled was in response
 *
 * ARCHITECTURE:
 *   - The backend (backend/security_middleware.py) adds the header
 *     `X-Input-Normalization: enabled` to every response when the
 *     feature is active.
 *   - This hook intercepts fetch() responses, checks for the header,
 *     and stores a flag.
 *   - The toast is shown ONCE per session (or until user dismisses)
 *     to avoid spamming.
 *
 * BROWSER HEADER ACCESS:
 *   Headers are case-insensitive per HTTP spec, but fetch() exposes
 *   them via response.headers.get() which normalizes to lowercase.
 *   We use 'x-input-normalization' (lowercase) for the lookup.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { toast } from '@/hooks/use-toast';

const HEADER_NAME = 'x-input-normalization';
const HEADER_VALUE = 'enabled';
const SESSION_STORAGE_KEY = 'fireai_input_norm_toast_shown';

export interface InputNormalizationToastOptions {
  /** Title of the toast. Defaults to "Input normalized". */
  title?: string;
  /** Body description. Defaults to a brief explanation. */
  description?: string;
  /** If true, the toast is shown only once per session (default true). */
  oncePerSession?: boolean;
  /** Duration in ms. Default 6000 (6 seconds). */
  duration?: number;
}

export interface InputNormalizationInfo {
  /** True if the backend normalized at least one input on the last response. */
  wasNormalized: boolean;
  /** Show the "Did you mean?" toast if normalization was detected. */
  showIfNormalized: (options?: InputNormalizationToastOptions) => void;
  /** Reset the per-session shown flag (useful for testing). */
  resetSession: () => void;
}

/**
 * Hook: detects input-normalization header on responses and surfaces
 * a "Did you mean?" toast.
 *
 * Implementation note: because the existing ApiClient in services/api.ts
 * uses `fetch()` internally and returns the parsed JSON (not the raw
 * Response), we install a global fetch interceptor on mount that
 * inspects every response's headers. This is the cleanest way to add
 * observability without rewriting every API method.
 */
export function useInputNormalization(): InputNormalizationInfo {
  const [wasNormalized, setWasNormalized] = useState(false);
  const sessionShownRef = useRef(false);

  // Initialize session-shown flag from sessionStorage.
  useEffect(() => {
    try {
      if (sessionStorage.getItem(SESSION_STORAGE_KEY) === '1') {
        sessionShownRef.current = true;
      }
    } catch {
      // sessionStorage might be unavailable (private browsing) — ignore.
    }
  }, []);

  // Install a global fetch interceptor that watches for the header.
  useEffect(() => {
    const originalFetch = window.fetch;
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const response = await originalFetch(input, init);
      try {
        const headerValue = response.headers.get(HEADER_NAME);
        if (headerValue === HEADER_VALUE) {
          setWasNormalized(true);
        }
      } catch {
        // Headers may not be accessible (CORS restriction) — ignore.
      }
      return response;
    };
    return () => {
      window.fetch = originalFetch;
    };
  }, []);

  const showIfNormalized = useCallback(
    (options?: InputNormalizationToastOptions) => {
      if (!wasNormalized) return;

      // Respect once-per-session flag.
      const oncePerSession = options?.oncePerSession ?? true;
      if (oncePerSession && sessionShownRef.current) return;

      const title = options?.title ?? 'Input normalized';
      const description =
        options?.description ??
        'Your input was automatically converted from Arabic keyboard to English. Check the saved value to confirm it matches what you meant.';
      const duration = options?.duration ?? 6000;

      toast({
        title,
        description,
        duration,
        variant: 'default',
      });

      if (oncePerSession) {
        sessionShownRef.current = true;
        try {
          sessionStorage.setItem(SESSION_STORAGE_KEY, '1');
        } catch {
          // Ignore — non-blocking.
        }
      }

      // Reset the per-response flag so we don't show the toast again
      // unless a NEW normalized response comes in.
      setWasNormalized(false);
    },
    [wasNormalized]
  );

  const resetSession = useCallback(() => {
    sessionShownRef.current = false;
    setWasNormalized(false);
    try {
      sessionStorage.removeItem(SESSION_STORAGE_KEY);
    } catch {
      // Ignore.
    }
  }, []);

  return { wasNormalized, showIfNormalized, resetSession };
}

/**
 * Standalone helper (no React context required) for components that
 * only need to check the header on a specific Response object.
 *
 * Useful in API hooks that already have access to the raw Response
 * (e.g. for file downloads where the JSON wrapper is not used).
 */
export function isInputNormalizationHeaderPresent(response: Response): boolean {
  try {
    return response.headers.get(HEADER_NAME) === HEADER_VALUE;
  } catch {
    return false;
  }
}

export default useInputNormalization;
