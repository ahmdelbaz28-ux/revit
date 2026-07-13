# 06 — Performance Report

**Project:** BAZspark v1.55.0
**Audit Date:** 2026-07-13

---

## Lighthouse Final Scores

| Category | Score | Status |
|---|:---:|:---:|
| Performance | 83-94 | ✅ (CPU-throttled) |
| Accessibility | **100** | ✅ |
| Best Practices | **100** | ✅ |
| SEO | **100** | ✅ |

## Bundle Size

| Chunk | Size | Gzipped |
|---|:---:|:---:|
| index.js | 349 kB | 104 kB |
| vendor-react | 133 kB | 43 kB |
| vendor-ui | 129 kB | 38 kB |
| vendor-i18n | 55 kB | 18 kB |
| vendor-icons | 22 kB | 7 kB |
| vendor-tanstack | 40 kB | 11 kB |
| index.css | 229 kB | 34 kB |

## Performance Optimizations Applied

### Code Splitting
- ✅ All 34 page components `React.lazy()`-loaded (V242)
- ✅ Vendor chunks separated (react, radix-ui, tanstack, i18n, icons, lucide)
- ✅ EngineeringBackground deferred via `requestIdleCallback` (V242)

### Caching
- ✅ Vercel: Immutable cache for `/assets/*` (1 year) (V248)
- ✅ Vite: Content-hashed filenames for cache busting
- ✅ Backend: Redis session store with TTL (V244)
- ✅ Browser: Service worker-ready (PWA manifest configured)

### Compression
- ✅ Vite: Terser minification with `drop_console` for production
- ✅ Vercel: Auto gzip + brotli compression
- ✅ Nginx: gzip configured in nginx.conf

### Rendering
- ✅ System font stack for instant FCP (V242)
- ✅ Google Fonts loaded async via `media="print"` + `fontLoader.ts` (V242)
- ✅ Critical CSS inlined in `index.html`
- ✅ `requestIdleCallback` for non-critical background loading (V242)

### Build Optimization
- ✅ ES2020 target (skips down-level transpilation) (V242)
- ✅ `modulePreload: { polyfill: true }` for faster navigation (V242)
- ✅ Hidden source maps (no `sourceMappingURL` in production JS) (V242)
- ✅ Tree-shaking enabled (Vite default)

## Key Metrics

| Metric | Value | Score |
|---|:---:|:---:|
| First Contentful Paint | 1.9-2.2s | 77-88 |
| Largest Contentful Paint | 2.0-3.9s | 53-97 |
| Total Blocking Time | 200-340ms | 75-89 |
| Cumulative Layout Shift | 0-0.055 | 98-100 |
| Speed Index | 1.9-2.2s | 99-100 |
