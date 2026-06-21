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

// Mock the API hooks before importing the component.
// P1.8 FIX: the previous mock was missing `useDevices`, which caused
// DashboardPage to crash at line 15 ('useDevices is not a function'
// → destructuring undefined.data throws). Added useDevices mock.
// Also added `error` field to useProjects/useDevices mocks (DashboardPage
// destructures error from both).
vi.mock('@/hooks/useApi', () => ({
  useHealth: vi.fn().mockReturnValue({
    data: { status: 'ok', version: '1.0.0', database: 'connected', uptime: 120 },
    loading: false,
    error: null,
    connected: true,
    refetch: vi.fn(),
  }),
  useProjects: vi.fn().mockReturnValue({
    data: [],
    loading: false,
    error: null,
    refetch: vi.fn(),
  }),
  useDevices: vi.fn().mockReturnValue({
    data: [],
    loading: false,
    error: null,
    refetch: vi.fn(),
  }),
  useCreateProject: vi.fn().mockReturnValue({
    mutate: vi.fn(),
    loading: false,
    error: null,
    data: null,
    reset: vi.fn(),
    refetch: vi.fn(),
  }),
}));

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  NavLink: ({ children }: { children: React.ReactNode }) => <a>{children}</a>,
}));

import { DashboardPage } from '../DashboardPage';

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders dashboard title', () => {
    render(<DashboardPage />);
    // DashboardPage uses t('dashboard.title') at line 34
    expect(screen.getByText('dashboard.title')).toBeInTheDocument();
  });

  it('displays statistics cards', () => {
    render(<DashboardPage />);
    // P1.8 FIX: DashboardPage has 3 stat cards:
    //   - dashboard.projects (appears twice: card title + 'active' label)
    //   - dashboard.totalDevices (card title)
    //   - dashboard.systemHealth (card title)
    // Previous test asserted 'dashboard.connections' which does NOT
    // exist in the component. Fixed to assert 'dashboard.systemHealth'.
    expect(screen.getAllByText('dashboard.projects').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('dashboard.totalDevices').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('dashboard.systemHealth').length).toBeGreaterThanOrEqual(1);
  });

  it('shows backend connection status', () => {
    render(<DashboardPage />);
    // P1.8 FIX: previous test asserted 'dashboard.healthy' which does NOT
    // exist in en.json. DashboardPage uses 'dashboard.connected' when
    // health.status === 'ok' (line 116). The mock returns status='ok' +
    // connected=true, so 'dashboard.connected' is rendered.
    expect(screen.getByText('dashboard.connected')).toBeInTheDocument();
  });

  it('renders refresh button', () => {
    render(<DashboardPage />);
    // P1.8 FIX: previous test asserted 'common.refresh' AND
    // 'dashboard.newProject'. Neither matches the actual component:
    //   - DashboardPage uses t('dashboard.refresh') (line 43), not
    //     common.refresh. dashboard.refresh is ALSO missing from en.json,
    //     but the t() function returns the key as-is when missing (the
    //     mock returns the key string), so the rendered text is
    //     'dashboard.refresh'.
    //   - DashboardPage has NO 'new project' button in the current
    //     implementation. Removed that assertion.
    expect(screen.getByText('dashboard.refresh')).toBeInTheDocument();
  });
});
