// ─────────────────────────────────────────────────────────────────────────
// EdgeWorker: geo-block
// ─────────────────────────────────────────────────────────────────────────
// Geo-based access control at the edge. Reads the country code from
// Akamai's geo database (no header needed — Akamai exposes it natively
// via request.user.location.countryCode) and blocks sanctioned countries
// before the request reaches the origin.
//
// This complements backend/akamai_middleware.py which reads the
// Akamai-Geo-Country header (also injected by Property Manager) for a
// defense-in-depth approach.
//
// Update the SANCTIONED_COUNTRIES list quarterly per OFAC updates.
// ─────────────────────────────────────────────────────────────────────────

import { URL } from 'node:url';
import { createResponse } from 'create-response';

// OFAC sanctioned countries (ISO 3166-1 alpha-2).
// Update from: https://www.treasury.gov/resource-center/sanctions/Programs/Pages/Programs.aspx
const SANCTIONED_COUNTRIES = new Set([
    'IR', // Iran
    'KP', // North Korea
    'SY', // Syria
    'CU', // Cuba
    'VE', // Venezuela (sanctioned regions)
    'BY', // Belarus
    'RU', // Russia (restricted regions)
]);

// Allowed paths even from sanctioned countries (e.g., UN humanitarian access).
const ALLOWED_PATHS_FOR_SANCTIONED = new Set(['/api/health', '/api/v1/health']);

export function onClientRequest(request) {
    // Akamai exposes user geo info natively — no header parsing needed.
    const country = request.user?.location?.countryCode || '';
    const path = new URL(request.url).pathname;

    // Inject geo info into the request so backend can log it.
    request.addHeader('Akamai-Geo-Country', country);
    if (request.user?.location) {
        if (request.user.location.region) {
            request.addHeader('Akamai-Geo-Region', request.user.location.region);
        }
        if (request.user.location.city) {
            request.addHeader('Akamai-Geo-City', request.user.location.city);
        }
    }

    // Block sanctioned countries (except for allowed paths)
    if (SANCTIONED_COUNTRIES.has(country) && !ALLOWED_PATHS_FOR_SANCTIONED.has(path)) {
        return createResponse(
            403,
            {
                'Content-Type': 'application/json',
                'Cache-Control': 'no-store',
            },
            JSON.stringify({
                success: false,
                error: 'Forbidden',
                message: `Access from ${country} is not permitted`,
                code: 'GEO_BLOCKED',
            })
        );
    }

    // Pass through (implicit return)
}
