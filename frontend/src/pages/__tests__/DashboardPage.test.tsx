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

// Mock the API hooks before importing the component
vi.mock('@/hooks/useApi', () => ({
  useHealth: vi.fn().mockReturnValue({
    data: { status: 'ok', version: '1.0.0', database: 'connected', uptime: 120 },
    loading: false,
    connected: true,
    refetch: vi.fn(),
  }),
  useProjects: vi.fn().mockReturnValue({
    data: [],
    loading: false,
    error: null,
    refetch: vi.fn(),
  }),
  useCreateProject: vi.fn().mockReturnValue({
    mutate: vi.fn(),
    loading: false,
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
    expect(screen.getByText('dashboard.title')).toBeInTheDocument();
  });

  it('displays statistics cards', () => {
    render(<DashboardPage />);
    // Stat card titles (i18n keys)
    expect(screen.getByText('dashboard.projects')).toBeInTheDocument();
    expect(screen.getByText('dashboard.totalDevices')).toBeInTheDocument();
    expect(screen.getByText('dashboard.connections')).toBeInTheDocument();
  });

  it('shows backend connection status', () => {
    render(<DashboardPage />);
    // With mocked health returning connected: true
    expect(screen.getByText('dashboard.healthy')).toBeInTheDocument();
  });

  it('renders refresh and new project buttons', () => {
    render(<DashboardPage />);
    expect(screen.getByText('common.refresh')).toBeInTheDocument();
    expect(screen.getByText('dashboard.newProject')).toBeInTheDocument();
  });
});
