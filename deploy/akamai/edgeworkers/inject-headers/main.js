// ─────────────────────────────────────────────────────────────────────────
// EdgeWorker: inject-headers
// ─────────────────────────────────────────────────────────────────────────
// Adds security headers at the Akamai edge (before the response reaches
// the client). This is faster than adding them at the origin because:
//   1. Headers are added on EVERY response (including cached ones).
//   2. No origin round-trip needed for header injection.
//   3. Even static assets (JS/CSS/images) get the security headers.
//
// This COMPLEMENTS (does not replace) backend/security_middleware.py
// which adds headers at the application layer (defense-in-depth).
// ─────────────────────────────────────────────────────────────────────────

// Headers to inject on every response.
// Aligned with backend/security_middleware.py.
const SECURITY_HEADERS = {
    'X-Frame-Options': 'DENY',
    'X-Content-Type-Options': 'nosniff',
    'Strict-Transport-Security': 'max-age=31536000; includeSubDomains; preload',
    'Referrer-Policy': 'no-referrer',
    'X-XSS-Protection': '0',
    'Permissions-Policy': 'accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()',
    'Cross-Origin-Embedder-Policy': 'require-corp',
    'Cross-Origin-Opener-Policy': 'same-origin',
    'Cross-Origin-Resource-Policy': 'same-origin',
    'X-Akamai-EdgeWorker': 'inject-headers',
};

// CSP — must match backend/security_middleware.py exactly.
const CSP_PRODUCTION = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'";

// Cache-Control for different content types.
function getCacheControl(path, contentType) {
    // Never cache API responses
    if (path.startsWith('/api/')) {
        return 'no-store, no-cache, must-revalidate, max-age=0';
    }
    // Long cache for static assets
    if (path.match(/\.(js|css|woff2?|ttf|png|jpe?g|gif|svg|ico|webp|avif)$/i)) {
        return 'public, max-age=2592000, immutable';  // 30 days
    }
    // Short cache for HTML (allow quick updates)
    if (contentType?.includes('text/html')) {
        return 'no-cache, must-revalidate';
    }
    return null;
}

export function onOriginResponse(request, response) {
    // Inject security headers
    for (const [key, value] of Object.entries(SECURITY_HEADERS)) {
        response.addHeader(key, value);
    }

    // Inject CSP (production policy — dev handled at origin)
    response.addHeader('Content-Security-Policy', CSP_PRODUCTION);

    // Override Cache-Control if the response doesn't already have one,
    // OR if our policy is more restrictive.
    const path = new URL(request.url).pathname;
    const contentType = response.getHeader('Content-Type') || '';
    const cacheControl = getCacheControl(path, contentType);

    if (cacheControl) {
        const existing = response.getHeader('Cache-Control');
        // Only override if not set or if our value is more restrictive
        if (!existing || (existing.includes('max-age') && cacheControl.includes('no-store'))) {
            response.setHeader('Cache-Control', cacheControl);
        }
    }

    // Add traceability header
    response.addHeader('X-Akamai-EdgeWorker-Processed', 'true');
    response.addHeader('X-Akamai-Response-Time', new Date().toISOString());
}

// Also handle client response (catches errors that don't reach origin)
export function onClientResponse(request, response) {
    // Ensure security headers are present even on error responses
    for (const [key, value] of Object.entries(SECURITY_HEADERS)) {
        if (!response.getHeader(key)) {
            response.addHeader(key, value);
        }
    }
    if (!response.getHeader('Content-Security-Policy')) {
        response.addHeader('Content-Security-Policy', CSP_PRODUCTION);
    }
}
