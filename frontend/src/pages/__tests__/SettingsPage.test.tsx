import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock react-i18next to return keys as display text
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}));

// Mock sessionStorage
const mockSessionStorage = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
    removeItem: vi.fn((key: string) => { delete store[key]; }),
    clear: vi.fn(() => { store = {}; }),
  };
})();
Object.defineProperty(window, 'sessionStorage', { value: mockSessionStorage });

// Mock fetch for test connection
global.fetch = vi.fn().mockResolvedValue({
  ok: true,
  json: () => Promise.resolve({ success: true, data: { status: 'ok' } }),
});

import { SettingsPage } from '../SettingsPage';

describe('SettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSessionStorage.clear();
  });

  it('renders settings form', () => {
    render(<SettingsPage />);
    expect(screen.getByText('settings.title')).toBeInTheDocument();
    expect(screen.getByText('settings.subtitle')).toBeInTheDocument();
  });

  it('has API key input field', () => {
    render(<SettingsPage />);
    const apiKeyInput = screen.getByPlaceholderText('Enter your API key');
    expect(apiKeyInput).toBeInTheDocument();
  });

  it('has API base URL input field', () => {
    render(<SettingsPage />);
    const apiUrlInput = screen.getByDisplayValue('/api/v1');
    expect(apiUrlInput).toBeInTheDocument();
  });

  it('renders configuration sections', () => {
    render(<SettingsPage />);
    expect(screen.getByText('settings.apiConfiguration')).toBeInTheDocument();
    // settings.apiKey appears twice (card title + label), use getAllByText
    expect(screen.getAllByText('settings.apiKey').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('settings.engineeringStandard')).toBeInTheDocument();
    expect(screen.getByText('settings.systemInfo')).toBeInTheDocument();
  });

  it('has test connection button', () => {
    render(<SettingsPage />);
    expect(screen.getByText('common.testConnection')).toBeInTheDocument();
  });

  it('shows default API URL as /api/v1', () => {
    render(<SettingsPage />);
    expect(screen.getByDisplayValue('/api/v1')).toBeInTheDocument();
  });
});
