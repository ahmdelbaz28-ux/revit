import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { PageErrorBoundary } from '../PageErrorBoundary';

describe('PageErrorBoundary', () => {
  it('renders children when no error', () => {
    render(
      <PageErrorBoundary>
        <div>Test content</div>
      </PageErrorBoundary>
    );
    expect(screen.getByText('Test content')).toBeInTheDocument();
  });

  it('renders error UI when child throws', () => {
    const ThrowError = () => { throw new Error('Test error'); };

    // Suppress console.error for expected errors
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <PageErrorBoundary pageName="TestPage">
        <ThrowError />
      </PageErrorBoundary>
    );

    expect(screen.getByText(/retry/i)).toBeInTheDocument();
    expect(screen.getByText(/TestPage Error/i)).toBeInTheDocument();
    spy.mockRestore();
  });

  it('shows page name in error message when provided', () => {
    const ThrowError = () => { throw new Error('Oops'); };
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <PageErrorBoundary pageName="Dashboard">
        <ThrowError />
      </PageErrorBoundary>
    );

    expect(screen.getByText('Dashboard Error')).toBeInTheDocument();
    spy.mockRestore();
  });

  it('shows generic error message when no page name', () => {
    const ThrowError = () => { throw new Error('Oops'); };
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <PageErrorBoundary>
        <ThrowError />
      </PageErrorBoundary>
    );

    // Should show "This page Error" (default fallback)
    expect(screen.getByText(/This page Error/i)).toBeInTheDocument();
    spy.mockRestore();
  });
});
