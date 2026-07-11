/**
 * miningApi.ts — Mining fire protection API client.
 *
 * V214: Exposes the 6 mining endpoints from backend/routers/mining.py:
 *   GET  /api/v1/mining/standards
 *   POST /api/v1/mining/methane-check
 *   POST /api/v1/mining/ventilation-check
 *   POST /api/v1/mining/co-check
 *   POST /api/v1/mining/conveyor-suppression
 *   POST /api/v1/mining/compliance-report
 *
 * Standards: NFPA 120-2022, NFPA 122-2022, MSHA 30 CFR Part 75, IEC 60079-10-1
 */

const API_BASE = "/api/v1";

// V214 self-critique fix: import getApiKey to send X-API-Key header.
// Without this, every mining endpoint returns 401 Unauthorized.
import { getApiKey } from "./apiKey";

async function miningApiCall<T>(
        path: string,
        options: RequestInit = {},
): Promise<T> {
        const headers: Record<string, string> = {
                "Content-Type": "application/json",
                ...((options.headers as Record<string, string>) || {}),
        };

        // V214: Add API key — all mining endpoints require authentication
        const apiKey = getApiKey();
        if (apiKey) {
                headers["X-API-Key"] = apiKey;
        }

        const response = await fetch(`${API_BASE}${path}`, {
                ...options,
                headers,
                credentials: "same-origin",
        });

        if (!response.ok) {
                const errorBody = await response.json().catch(() => ({}));
                throw new Error(
                        errorBody?.detail || `HTTP ${response.status}: ${response.statusText}`,
                );
        }

        return response.json();
}

export const miningApi = {
        /** GET /mining/standards — List supported mining standards */
        getStandards: () =>
                miningApiCall<{
                        success: boolean;
                        standards: Array<{ code: string; title: string }>;
                }>("/mining/standards"),

        /** POST /mining/methane-check — Classify methane hazard per MSHA §75.323 */
        methaneCheck: (data: { concentration_pct: number; location?: string }) =>
                miningApiCall<{
                        success: boolean;
                        concentration_pct: number;
                        hazard_level: string;
                        is_in_explosive_range: boolean;
                        distance_to_lel_pct: number;
                        location: string;
                        standard: string;
                        thresholds: Record<string, number>;
                }>("/mining/methane-check", {
                        method: "POST",
                        body: JSON.stringify(data),
                }),

        /** POST /mining/ventilation-check — Check MSHA ventilation compliance */
        ventilationCheck: (data: {
                airflow_m3_s: number;
                location_type?: string;
                cross_sectional_area_m2?: number;
        }) =>
                miningApiCall<{
                        success: boolean;
                        airflow_m3_s: number;
                        location_type: string;
                        is_compliant: boolean;
                        violations: string[];
                        velocity_m_s: number | null;
                        standard: string;
                }>("/mining/ventilation-check", {
                        method: "POST",
                        body: JSON.stringify(data),
                }),

        /** POST /mining/co-check — Classify CO hazard per MSHA §75.351 */
        coCheck: (data: { co_ppm: number }) =>
                miningApiCall<{
                        success: boolean;
                        co_ppm: number;
                        hazard_level: string;
                        thresholds: Record<string, number>;
                        standard: string;
                }>("/mining/co-check", {
                        method: "POST",
                        body: JSON.stringify(data),
                }),

        /** POST /mining/conveyor-suppression — Design suppression per NFPA 120 §8.4 */
        conveyorSuppression: (data: {
                belt_length_m: number;
                belt_width_m: number;
                belt_speed_m_s?: number;
                has_fire_resistant_belt?: boolean;
        }) =>
                miningApiCall<{
                        success: boolean;
                        design: {
                                number_of_nozzle_groups: number;
                                water_flow_rate_lpm: number;
                                water_duration_min: number;
                                total_water_volume_l: number;
                                nozzle_locations: string[];
                                is_compliant: boolean;
                                violations: string[];
                        };
                        standard: string;
                }>("/mining/conveyor-suppression", {
                        method: "POST",
                        body: JSON.stringify(data),
                }),

        /** POST /mining/compliance-report — Full MSHA + NFPA 120 compliance report */
        complianceReport: (data: {
                mine_name: string;
                section_name: string;
                methane_pct?: number;
                co_ppm?: number;
                airflow_m3_s?: number;
                ventilation_location?: string;
                conveyor_length_m?: number;
                conveyor_width_m?: number;
                has_fire_resistant_belt?: boolean;
        }) =>
                miningApiCall<{
                        success: boolean;
                        overall_status: string;
                        checks: Array<{
                                rule_id: string;
                                standard: string;
                                description: string;
                                status: string;
                                details: string;
                                remediation: string;
                        }>;
                        markdown_report: string;
                }>("/mining/compliance-report", {
                        method: "POST",
                        body: JSON.stringify(data),
                }),
};
