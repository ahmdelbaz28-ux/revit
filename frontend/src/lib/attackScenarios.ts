/**
 * attackScenarios.ts — Adversarial attack scenarios for formal verification.
 *
 * Each scenario attempts to violate system invariants.
 * System is valid only if it rejects, isolates, or recovers from all attacks.
 */

import { AttackScenario } from './formalVerifier';

export const ATTACK_SCENARIOS: AttackScenario[] = [
  {
    name: 'SCENARIO-001: Malformed WebSocket Payload Injection',
    description: 'Inject invalid WebSocket messages to test schema validation',
    expected_outcome: 'REJECTED',
    actions: [
      { type: 'WS_CONNECT' },
      { type: 'WS_MESSAGE', message: 'not a valid object' },
      { type: 'WS_MESSAGE', message: { no_channel: true } },
      { type: 'WS_MESSAGE', message: { channel: 'test', data: { valid: true } } },
      { type: 'WS_HEARTBEAT' },
    ],
  },
  {
    name: 'SCENARIO-002: API Request Duplication Attack',
    description: 'Send duplicate API requests to test deduplication',
    expected_outcome: 'ISOLATED',
    actions: [
      { type: 'API_REQUEST', request_id: 'req-001' },
      { type: 'ATTACK_DUPLICATE_REQUEST', request_id: 'req-001' },
      { type: 'API_RESPONSE', request_id: 'req-001', response: { status: 'ok' } },
    ],
  },
  {
    name: 'SCENARIO-003: API Timeout Cascade',
    description: 'Trigger multiple API timeouts to test circuit breaker',
    expected_outcome: 'RECOVERED',
    actions: [
      { type: 'API_REQUEST', request_id: 'req-001' },
      { type: 'API_TIMEOUT', request_id: 'req-001' },
      { type: 'API_REQUEST', request_id: 'req-002' },
      { type: 'API_TIMEOUT', request_id: 'req-002' },
      { type: 'API_REQUEST', request_id: 'req-003' },
      { type: 'API_TIMEOUT', request_id: 'req-003' },
      { type: 'CIRCUIT_BREAK', service: 'api' },
      { type: 'CIRCUIT_RECOVER', service: 'api' },
    ],
  },
  {
    name: 'SCENARIO-004: Corrupted Store Update',
    description: 'Attempt to inject corrupted data into store',
    expected_outcome: 'REJECTED',
    actions: [
      { type: 'STORE_UPDATE', data: { valid: 'data' } },
      { type: 'ATTACK_CORRUPTED_STORE_UPDATE' },
      { type: 'STORE_UPDATE', data: { more: 'valid_data' } },
    ],
  },
  {
    name: 'SCENARIO-005: WebSocket Reconnect Storm',
    description: 'Simulate rapid reconnect attempts to trigger storm detection',
    expected_outcome: 'ISOLATED',
    actions: [
      { type: 'WS_CONNECT' },
      { type: 'WS_DISCONNECT' },
      { type: 'WS_CONNECT' },
      { type: 'WS_DISCONNECT' },
      { type: 'WS_CONNECT' },
      { type: 'WS_DISCONNECT' },
      { type: 'WS_CONNECT' },
      { type: 'WS_DISCONNECT' },
      { type: 'WS_CONNECT' },
      { type: 'WS_DISCONNECT' },
    ],
  },
  {
    name: 'SCENARIO-006: Delayed Response Replay Attack',
    description: 'Replay old API responses to test response validation',
    expected_outcome: 'REJECTED',
    actions: [
      { type: 'API_REQUEST', request_id: 'req-001' },
      { type: 'API_RESPONSE', request_id: 'req-001', response: { status: 'ok' } },
      { type: 'ATTACK_DELAYED_RESPONSE_REPLAY', request_id: 'req-001' },
    ],
  },
  {
    name: 'SCENARIO-007: Partial State Rollback Attempt',
    description: 'Attempt partial state rollback to test consistency',
    expected_outcome: 'REJECTED',
    actions: [
      { type: 'STORE_UPDATE', data: { version: 1 } },
      { type: 'STORE_UPDATE', data: { version: 2 } },
      { type: 'ATTACK_PARTIAL_STATE_ROLLBACK' },
      { type: 'STORE_UPDATE', data: { version: 3 } },
    ],
  },
  {
    name: 'SCENARIO-008: WebSocket Heartbeat Timeout',
    description: 'Simulate heartbeat timeout to test dead connection detection',
    expected_outcome: 'RECOVERED',
    actions: [
      { type: 'WS_CONNECT' },
      { type: 'WS_HEARTBEAT' },
      { type: 'WS_HEARTBEAT_TIMEOUT' },
      { type: 'WS_DISCONNECT' },
      { type: 'WS_CONNECT' },
    ],
  },
  {
    name: 'SCENARIO-009: Concurrent API Errors',
    description: 'Trigger concurrent API errors to test error isolation',
    expected_outcome: 'ISOLATED',
    actions: [
      { type: 'API_REQUEST', request_id: 'req-001' },
      { type: 'API_REQUEST', request_id: 'req-002' },
      { type: 'API_ERROR', request_id: 'req-001', error: 'Network error' },
      { type: 'API_ERROR', request_id: 'req-002', error: 'Timeout' },
      { type: 'API_REQUEST', request_id: 'req-003' },
      { type: 'API_ERROR', request_id: 'req-003', error: 'Server error' },
      { type: 'CIRCUIT_BREAK', service: 'api' },
    ],
  },
  {
    name: 'SCENARIO-010: Full System Stress Test',
    description: 'Combine multiple attack vectors simultaneously',
    expected_outcome: 'RECOVERED',
    actions: [
      { type: 'API_REQUEST', request_id: 'req-001' },
      { type: 'WS_CONNECT' },
      { type: 'WS_MESSAGE', message: 'invalid' },
      { type: 'API_TIMEOUT', request_id: 'req-001' },
      { type: 'WS_HEARTBEAT_TIMEOUT' },
      { type: 'CIRCUIT_BREAK', service: 'api' },
      { type: 'WS_DISCONNECT' },
      { type: 'CIRCUIT_RECOVER', service: 'api' },
      { type: 'WS_CONNECT' },
      { type: 'WS_HEARTBEAT' },
    ],
  },
];

export default ATTACK_SCENARIOS;
