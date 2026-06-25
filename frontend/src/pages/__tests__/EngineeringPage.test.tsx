import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

// Mock react-i18next to return keys as display text
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}));

// Mock the CalculationEngine
vi.mock('@/engine/CalculationEngine', () => ({
  calculateVoltageDrop: vi.fn().mockReturnValue({ percentage: 2.5, voltageDrop: 5.75, isCompliant: true }),
  calculateShortCircuit: vi.fn().mockReturnValue({ prospectiveCurrent: 5000, breakingCapacity: 6000, isCompliant: true }),
  calculateCableSizing: vi.fn().mockReturnValue({ recommendedSize: '2.5mm²', deratingFactor: 0.87, isCompliant: true }),
  calculateLoadFlow: vi.fn().mockReturnValue({ totalLoad: 50, voltageAtEnd: 218, isCompliant: true }),
  checkBreakerCoordination: vi.fn(),
  calculateEarthFaultLoop: vi.fn(),
  calculatePowerFactorCorrection: vi.fn(),
  generateCompleteReport: vi.fn(),
}));

import { EngineeringPage } from '../EngineeringPage';

describe('EngineeringPage', () => {
  it('renders engineering calculation tabs', () => {
    render(<EngineeringPage />);
    expect(screen.getByText('Voltage Drop')).toBeInTheDocument();
    expect(screen.getByText('Short Circuit')).toBeInTheDocument();
    expect(screen.getByText('Cable Sizing')).toBeInTheDocument();
    expect(screen.getByText('Load Flow')).toBeInTheDocument();
  });

  it('renders calculate buttons', () => {
    render(<EngineeringPage />);
    expect(screen.getByText('Calculate Voltage Drop')).toBeInTheDocument();
  });

  it('displays the engineering page heading', () => {
    render(<EngineeringPage />);
    expect(screen.getByText('engineering.title')).toBeInTheDocument();
  });

  it('shows validation-compliant default inputs', () => {
    render(<EngineeringPage />);
    // The default values should produce valid inputs, so the calculate button
    // should NOT be disabled
    const calcButton = screen.getByText('Calculate Voltage Drop');
    expect(calcButton).not.toBeDisabled();
  });
});
