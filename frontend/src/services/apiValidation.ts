/**
 * apiValidation.ts - Runtime validation helpers for API responses
 *
 * These type guards validate the shape of data coming from the backend
 * at runtime, preventing undefined field access when the API returns
 * unexpected shapes. Uses plain TypeScript — no Zod dependency.
 *
 * Two API systems are validated:
 *   System A (Digital Twin): camelCase fields from digital_twin.db
 *   System B (UDM Elements): snake_case fields from udm_elements.db
 */

import type { ApiResponse, Project, Device } from './digitalTwinApi';

// ============================================================================
// Result types
// ============================================================================

export type ValidationResult<T> =
  | { valid: true; data: T }
  | { valid: false; errors: string[] };

// ============================================================================
// validateApiResponse<T>
// ============================================================================

/**
 * Validates the shape of an ApiResponse envelope from the Digital Twin API.
 * Checks that `success` is a boolean and that `data` exists when success=true.
 */
export function validateApiResponse<T>(response: unknown): ValidationResult<ApiResponse<T>> {
  const errors: string[] = [];

  if (response === null || response === undefined || typeof response !== 'object') {
    return { valid: false, errors: ['Response is not an object'] };
  }

  const obj = response as Record<string, unknown>;

  if (typeof obj.success !== 'boolean') {
    errors.push('Missing or non-boolean "success" field');
  }

  if (obj.success === true && obj.data === undefined) {
    errors.push('Success response missing "data" field');
  }

  if (obj.error !== undefined && typeof obj.error !== 'string') {
    errors.push('"error" field must be a string when present');
  }

  if (obj.timestamp !== undefined && typeof obj.timestamp !== 'string') {
    errors.push('"timestamp" field must be a string when present');
  }

  if (errors.length > 0) {
    return { valid: false, errors };
  }

  return { valid: true, data: obj as unknown as ApiResponse<T> };
}

// ============================================================================
// safeParseProject - validates Digital Twin (System A) project data
// ============================================================================

/**
 * Validates that a value matches the Digital Twin API Project shape:
 * { id, name, description, author, createdAt, updatedAt, status, deviceCount, connectionCount }
 */
export function safeParseProject(value: unknown): ValidationResult<Project> {
  const errors: string[] = [];

  if (value === null || value === undefined || typeof value !== 'object') {
    return { valid: false, errors: ['Project is not an object'] };
  }

  const obj = value as Record<string, unknown>;

  if (typeof obj.id !== 'string' || obj.id.length === 0) {
    errors.push('Missing or invalid "id" (expected non-empty string)');
  }

  if (typeof obj.name !== 'string' || obj.name.length === 0) {
    errors.push('Missing or invalid "name" (expected non-empty string)');
  }

  if (obj.description !== undefined && typeof obj.description !== 'string') {
    errors.push('"description" must be a string when present');
  }

  if (typeof obj.status !== 'string') {
    errors.push('Missing or invalid "status" (expected string)');
  } else {
    const validStatuses = ['active', 'archived', 'draft'];
    if (!validStatuses.includes(obj.status)) {
      errors.push(`"status" must be one of: ${validStatuses.join(', ')} (got "${obj.status}")`);
    }
  }

  if (typeof obj.createdAt !== 'string') {
    errors.push('Missing or invalid "createdAt" (expected ISO date string)');
  }

  if (typeof obj.updatedAt !== 'string') {
    errors.push('Missing or invalid "updatedAt" (expected ISO date string)');
  }

  if (obj.deviceCount !== undefined && typeof obj.deviceCount !== 'number') {
    errors.push('"deviceCount" must be a number when present');
  }

  if (obj.connectionCount !== undefined && typeof obj.connectionCount !== 'number') {
    errors.push('"connectionCount" must be a number when present');
  }

  if (errors.length > 0) {
    return { valid: false, errors };
  }

  return { valid: true, data: obj as unknown as Project };
}

// ============================================================================
// safeParseDevice - validates Digital Twin (System A) device data
// ============================================================================

/**
 * Validates that a value matches the Digital Twin API Device shape:
 * { id, projectId, type, name, category, x, y, z, rotation, voltage, current, load, properties, createdAt, updatedAt }
 */
export function safeParseDevice(value: unknown): ValidationResult<Device> {
  const errors: string[] = [];

  if (value === null || value === undefined || typeof value !== 'object') {
    return { valid: false, errors: ['Device is not an object'] };
  }

  const obj = value as Record<string, unknown>;

  if (typeof obj.id !== 'string' || obj.id.length === 0) {
    errors.push('Missing or invalid "id" (expected non-empty string)');
  }

  if (typeof obj.projectId !== 'string' || obj.projectId.length === 0) {
    errors.push('Missing or invalid "projectId" (expected non-empty string)');
  }

  if (typeof obj.type !== 'string') {
    errors.push('Missing or invalid "type" (expected string)');
  }

  if (typeof obj.name !== 'string') {
    errors.push('Missing or invalid "name" (expected string)');
  }

  if (typeof obj.category !== 'string') {
    errors.push('Missing or invalid "category" (expected string)');
  }

  if (typeof obj.x !== 'number') {
    errors.push('Missing or invalid "x" (expected number)');
  }

  if (typeof obj.y !== 'number') {
    errors.push('Missing or invalid "y" (expected number)');
  }

  if (obj.z !== undefined && typeof obj.z !== 'number') {
    errors.push('"z" must be a number when present');
  }

  if (obj.voltage !== undefined && typeof obj.voltage !== 'number') {
    errors.push('"voltage" must be a number when present');
  }

  if (obj.current !== undefined && typeof obj.current !== 'number') {
    errors.push('"current" must be a number when present');
  }

  if (obj.load !== undefined && typeof obj.load !== 'number') {
    errors.push('"load" must be a number when present');
  }

  if (typeof obj.createdAt !== 'string') {
    errors.push('Missing or invalid "createdAt" (expected ISO date string)');
  }

  if (typeof obj.updatedAt !== 'string') {
    errors.push('Missing or invalid "updatedAt" (expected ISO date string)');
  }

  if (errors.length > 0) {
    return { valid: false, errors };
  }

  return { valid: true, data: obj as unknown as Device };
}
