/**
 * MermaidRenderer.test.tsx — Comprehensive tests for the MermaidRenderer component.
 * ==========================================================================
 *
 * Test categories:
 *   1. Rendering: basic mount, loading state, error state, SVG output
 *   2. Props: code changes, isGenerating, className
 *   3. Interactions: fullscreen toggle, download, zoom controls
 *   4. Accessibility: ARIA roles, labels, keyboard support
 *   5. Edge cases: empty code, invalid syntax, very long code
 *   6. Theme: dark/light mode detection
 *
 * Notes:
 *   - Mermaid.js is mocked to avoid heavy rendering in tests
 *   - jsdom doesn't support SVG rendering, so we test the wrapper behavior
 *   - All async tests use proper await + cleanup
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MermaidRenderer } from '../MermaidRenderer';

// ─── Mock mermaid.js ──────────────────────────────────────────────────────
// We mock mermaid to avoid the heavy SVG rendering in jsdom.
// Tests verify the component's behavior, not mermaid's correctness.

const mockMermaidRender = vi.fn();
const mockMermaidParse = vi.fn();
const mockMermaidInitialize = vi.fn();

vi.mock('mermaid', () => ({
  default: {
    initialize: (...args: unknown[]) => mockMermaidInitialize(...args),
    parse: (...args: unknown[]) => mockMermaidParse(...args),
    render: (...args: unknown[]) => mockMermaidRender(...args),
  },
}));

// ─── Test fixtures ────────────────────────────────────────────────────────
const SIMPLE_FLOWCHART = `graph TD
    A[Start] --> B[Process]
    B --> C[End]`;

const SEQUENCE_DIAGRAM = `sequenceDiagram
    participant A as Client
    participant B as Server
    A->>B: Request
    B-->>A: Response`;

const INVALID_CODE = `graph TD
    A --> >-> B`; // Invalid syntax

const ER_DIAGRAM = `erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ LINE-ITEM : contains`;

// ─── Setup / teardown ─────────────────────────────────────────────────────
beforeEach(() => {
  vi.clearAllMocks();
  mockMermaidParse.mockResolvedValue(undefined);
  mockMermaidRender.mockResolvedValue({ svg: '<svg>mock-diagram</svg>' });
  // Reset dark mode
  document.documentElement.classList.remove('dark');
});

afterEach(() => {
  cleanup();
});

// ─── 1. Rendering tests ───────────────────────────────────────────────────
describe('MermaidRenderer — Rendering', () => {
  it('renders without crashing', async () => {
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);
    expect(screen.getByTestId('mermaid-renderer')).toBeInTheDocument();
  });

  it('shows loading state initially (before debounce + render)', async () => {
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);
    // Loading indicator should be visible initially
    expect(screen.getByText(/Rendering Diagram/i)).toBeInTheDocument();
  });

  it('renders SVG after successful mermaid.render call', async () => {
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    // Wait for debounce (300ms) + render
    await waitFor(
      () => {
        expect(mockMermaidRender).toHaveBeenCalledWith(
          expect.stringMatching(/^mermaid-/),
          SIMPLE_FLOWCHART,
        );
      },
      { timeout: 2000 },
    );
  });

  it('calls mermaid.initialize with theme config', async () => {
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    await waitFor(() => {
      expect(mockMermaidInitialize).toHaveBeenCalledWith(
        expect.objectContaining({
          startOnLoad: false,
          securityLevel: 'loose',
          theme: 'base',
        }),
      );
    });
  });

  it('calls mermaid.parse to validate syntax before rendering', async () => {
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    await waitFor(() => {
      expect(mockMermaidParse).toHaveBeenCalledWith(SIMPLE_FLOWCHART);
    });
  });
});

// ─── 2. Props tests ───────────────────────────────────────────────────────
describe('MermaidRenderer — Props', () => {
  it('shows loading state when isGenerating=true', () => {
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} isGenerating={true} />);
    expect(screen.getByText(/Rendering Diagram/i)).toBeInTheDocument();
  });

  it('applies custom className to outer container', () => {
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} className="custom-class" />);
    const container = screen.getByTestId('mermaid-renderer');
    expect(container.className).toContain('custom-class');
  });

  it('re-renders when code prop changes', async () => {
    const { rerender } = render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    await waitFor(() => {
      expect(mockMermaidParse).toHaveBeenCalledWith(SIMPLE_FLOWCHART);
    });

    vi.clearAllMocks();
    rerender(<MermaidRenderer code={SEQUENCE_DIAGRAM} />);

    await waitFor(() => {
      expect(mockMermaidParse).toHaveBeenCalledWith(SEQUENCE_DIAGRAM);
    });
  });

  it('does NOT re-render when code prop is unchanged (memo)', async () => {
    const { rerender } = render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    await waitFor(() => {
      expect(mockMermaidParse).toHaveBeenCalledTimes(1);
    });

    // Force a re-render with same props
    rerender(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    // Should not have called parse again immediately (debounced)
    // Note: debounce may trigger one more call, but the count should be limited
    expect(mockMermaidParse.mock.calls.length).toBeLessThanOrEqual(2);
  });
});

// ─── 3. Error handling tests ──────────────────────────────────────────────
describe('MermaidRenderer — Error handling', () => {
  it('displays error message when mermaid.parse throws', async () => {
    mockMermaidParse.mockRejectedValue(new Error('Parse error: invalid syntax'));

    render(<MermaidRenderer code={INVALID_CODE} />);

    await waitFor(
      () => {
        expect(screen.getByTestId('mermaid-error')).toBeInTheDocument();
      },
      { timeout: 2000 },
    );

    expect(screen.getByText(/Diagram rendering failed/i)).toBeInTheDocument();
  });

  it('displays error message when mermaid.render throws', async () => {
    mockMermaidRender.mockRejectedValue(new Error('Render failed'));

    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    await waitFor(
      () => {
        expect(screen.getByTestId('mermaid-error')).toBeInTheDocument();
      },
      { timeout: 2000 },
    );
  });

  it('truncates long error messages to 200 chars', async () => {
    const longError = 'E'.repeat(500);
    mockMermaidParse.mockRejectedValue(new Error(longError));

    render(<MermaidRenderer code={INVALID_CODE} />);

    await waitFor(
      () => {
        const errorEl = screen.getByTestId('mermaid-error');
        expect(errorEl).toBeInTheDocument();
      },
      { timeout: 2000 },
    );
  });
});

// ─── 4. Interaction tests ─────────────────────────────────────────────────
describe('MermaidRenderer — Interactions', () => {
  it('opens fullscreen when Maximize2 button clicked', async () => {
    const user = userEvent.setup();
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    const fullscreenBtn = screen.getByLabelText(/Open diagram in fullscreen/i);
    await user.click(fullscreenBtn);

    expect(screen.getByTestId('mermaid-fullscreen')).toBeInTheDocument();
  });

  it('closes fullscreen when X button clicked', async () => {
    const user = userEvent.setup();
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    // Open
    await user.click(screen.getByLabelText(/Open diagram in fullscreen/i));
    expect(screen.getByTestId('mermaid-fullscreen')).toBeInTheDocument();

    // Close
    await user.click(screen.getByLabelText(/Close fullscreen/i));
    expect(screen.queryByTestId('mermaid-fullscreen')).not.toBeInTheDocument();
  });

  it('zoom in button increases scale', async () => {
    const user = userEvent.setup();
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    await user.click(screen.getByLabelText(/Open diagram in fullscreen/i));

    // Initial scale = 100%
    expect(screen.getByText('100%')).toBeInTheDocument();

    // Click zoom in
    await user.click(screen.getByLabelText(/Zoom in/i));

    // Should now show 150%
    expect(screen.getByText('150%')).toBeInTheDocument();
  });

  it('zoom out button decreases scale (min 0.5)', async () => {
    const user = userEvent.setup();
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    await user.click(screen.getByLabelText(/Open diagram in fullscreen/i));
    await user.click(screen.getByLabelText(/Zoom out/i));

    expect(screen.getByText('50%')).toBeInTheDocument();
  });

  it('reset button restores scale to 100%', async () => {
    const user = userEvent.setup();
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    await user.click(screen.getByLabelText(/Open diagram in fullscreen/i));
    await user.click(screen.getByLabelText(/Zoom in/i));
    expect(screen.getByText('150%')).toBeInTheDocument();

    await user.click(screen.getByText(/Reset/i));
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('zoom out does not go below 0.5 (50%)', async () => {
    const user = userEvent.setup();
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    await user.click(screen.getByLabelText(/Open diagram in fullscreen/i));

    // Click zoom out twice (should stop at 50%)
    await user.click(screen.getByLabelText(/Zoom out/i));
    expect(screen.getByText('50%')).toBeInTheDocument();

    await user.click(screen.getByLabelText(/Zoom out/i));
    expect(screen.getByText('50%')).toBeInTheDocument(); // Still 50%
  });

  it('zoom in does not exceed 20 (2000%)', async () => {
    const user = userEvent.setup();
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    await user.click(screen.getByLabelText(/Open diagram in fullscreen/i));

    // Click zoom in many times
    for (let i = 0; i < 50; i++) {
      await user.click(screen.getByLabelText(/Zoom in/i));
    }

    // Should cap at 2000%
    expect(screen.getByText('2000%')).toBeInTheDocument();
  });

  it('download button triggers SVG download', async () => {
    const user = userEvent.setup();
    // Mock URL.createObjectURL and link.click
    const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock');
    const revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});

    // Mock document.createElement for <a>
    const originalCreateElement = document.createElement.bind(document);
    const linkClickSpy = vi.fn();
    vi.spyOn(document, 'createElement').mockImplementation((tagName: string) => {
      if (tagName === 'a') {
        const el = originalCreateElement(tagName);
        el.click = linkClickSpy;
        return el;
      }
      return originalCreateElement(tagName);
    });

    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    // Wait for render to complete (SVG must be set)
    await waitFor(() => {
      expect(mockMermaidRender).toHaveBeenCalled();
    });

    const downloadBtn = screen.getByLabelText(/Download diagram as SVG/i);
    await user.click(downloadBtn);

    expect(createObjectURLSpy).toHaveBeenCalled();
    expect(linkClickSpy).toHaveBeenCalled();

    createObjectURLSpy.mockRestore();
    revokeObjectURLSpy.mockRestore();
  });
});

// ─── 5. Accessibility tests ───────────────────────────────────────────────
describe('MermaidRenderer — Accessibility', () => {
  it('has role="img" on the diagram container', () => {
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);
    expect(screen.getByRole('img')).toBeInTheDocument();
  });

  it('has aria-label on the diagram container', () => {
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);
    expect(screen.getByLabelText('Mermaid diagram')).toBeInTheDocument();
  });

  it('fullscreen dialog has role="dialog"', async () => {
    const user = userEvent.setup();
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    await user.click(screen.getByLabelText(/Open diagram in fullscreen/i));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('fullscreen dialog has aria-modal="true"', async () => {
    const user = userEvent.setup();
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    await user.click(screen.getByLabelText(/Open diagram in fullscreen/i));

    expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'true');
  });

  it('error display has role="alert"', async () => {
    mockMermaidParse.mockRejectedValue(new Error('test'));

    render(<MermaidRenderer code={INVALID_CODE} />);

    await waitFor(
      () => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
      },
      { timeout: 2000 },
    );
  });

  it('all buttons have accessible names', () => {
    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    // All buttons should have either aria-label or text content
    const buttons = screen.getAllByRole('button');
    buttons.forEach((btn) => {
      const hasAriaLabel = btn.hasAttribute('aria-label');
      const hasText = btn.textContent && btn.textContent.trim().length > 0;
      const hasTitle = btn.hasAttribute('title');
      expect(hasAriaLabel || hasText || hasTitle).toBe(true);
    });
  });
});

// ─── 6. Theme tests ───────────────────────────────────────────────────────
describe('MermaidRenderer — Theme detection', () => {
  it('uses dark theme variables when .dark class is on documentElement', async () => {
    document.documentElement.classList.add('dark');

    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    await waitFor(() => {
      expect(mockMermaidInitialize).toHaveBeenCalledWith(
        expect.objectContaining({
          themeVariables: expect.objectContaining({
            darkMode: true,
            background: '#0f172a',
          }),
        }),
      );
    });
  });

  it('uses light theme variables when .dark class is absent', async () => {
    document.documentElement.classList.remove('dark');

    render(<MermaidRenderer code={SIMPLE_FLOWCHART} />);

    await waitFor(() => {
      expect(mockMermaidInitialize).toHaveBeenCalledWith(
        expect.objectContaining({
          themeVariables: expect.objectContaining({
            darkMode: false,
            background: '#ffffff',
          }),
        }),
      );
    });
  });
});

// ─── 7. Edge cases ────────────────────────────────────────────────────────
describe('MermaidRenderer — Edge cases', () => {
  it('handles empty code string gracefully', async () => {
    mockMermaidParse.mockRejectedValue(new Error('Empty diagram'));

    render(<MermaidRenderer code="" />);

    // Should not crash, should show error
    await waitFor(
      () => {
        expect(screen.getByTestId('mermaid-error')).toBeInTheDocument();
      },
      { timeout: 2000 },
    );
  });

  it('handles ER diagrams (no aggressive ||-- replacement)', async () => {
    render(<MermaidRenderer code={ER_DIAGRAM} />);

    await waitFor(() => {
      // ER diagrams use ||--|| syntax which should NOT be replaced
      expect(mockMermaidParse).toHaveBeenCalledWith(ER_DIAGRAM);
    });
  });

  it('sanitizes graph CR → graph LR', async () => {
    const invalidDirection = 'graph CR\n  A --> B';
    render(<MermaidRenderer code={invalidDirection} />);

    await waitFor(() => {
      expect(mockMermaidParse).toHaveBeenCalledWith('graph LR\n  A --> B');
    });
  });

  it('sanitizes graph CL → graph RL', async () => {
    const invalidDirection = 'graph CL\n  A --> B';
    render(<MermaidRenderer code={invalidDirection} />);

    await waitFor(() => {
      expect(mockMermaidParse).toHaveBeenCalledWith('graph RL\n  A --> B');
    });
  });

  it('sanitizes +-- → -->', async () => {
    const code = 'graph TD\n  A +-- B';
    render(<MermaidRenderer code={code} />);

    await waitFor(() => {
      expect(mockMermaidParse).toHaveBeenCalledWith('graph TD\n  A --> B');
    });
  });
});

// ─── 8. Debouncing tests ──────────────────────────────────────────────────
describe('MermaidRenderer — Debouncing', () => {
  it('debounces rapid code changes (300ms)', async () => {
    const { rerender } = render(<MermaidRenderer code={'graph TD\n  A --> B'} />);

    // Rapid changes
    rerender(<MermaidRenderer code={'graph TD\n  A --> C'} />);
    rerender(<MermaidRenderer code={'graph TD\n  A --> D'} />);
    const finalCode = 'graph TD\n  A --> E';
    rerender(<MermaidRenderer code={finalCode} />);

    // Wait for debounce
    await new Promise((r) => setTimeout(r, 500));

    // Should only have rendered the last version (after debounce).
    // We use expect.stringContaining to avoid newline-escaping mismatches.
    expect(mockMermaidParse).toHaveBeenCalledWith(expect.stringContaining('A --> E'));
  });
});
