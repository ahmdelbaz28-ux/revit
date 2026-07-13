# 03 — Performance Report

**Project:** BAZspark v1.55.0
**Audit Date:** 2026-07-13

---

## Lighthouse Final Scores

| Category | Score | Status |
|---|:---:|:---:|
| Performance | 83-94 | ✅ (CPU-throttled; varies) |
| Accessibility | **100** | ✅ |
| Best Practices | **100** | ✅ |
| SEO | **100** | ✅ |

## Key Metrics

| Metric | Value | Score |
|---|:---:|:---:|
| First Contentful Paint | 1.9-2.2s | 77-88 |
| Largest Contentful Paint | 2.0-3.9s | 53-97 |
| Total Blocking Time | 200-340ms | 75-89 |
| Cumulative Layout Shift | 0-0.055 | 98-100 |
| Speed Index | 1.9-2.2s | 99-100 |

## Bundle Size Evolution

| Version | index.js | Gzipped | Improvement |
|:---:|:---:|:---:|:---:|
| V241 | 705 kB | 169 kB | baseline |
| V242 | 349 kB | 104 kB | -50% |
| V247 | 349 kB | 104 kB | maintained |

## Optimization Techniques Applied

1. **Code splitting** — All 34 page components are `React.lazy()`-loaded
2. **Vendor chunk splitting** — react, radix-ui, tanstack, i18n, icons, lucide separated
3. **Deferred background** — EngineeringBackground (30kB SVG) loads via `requestIdleCallback`
4. **System font stack** — Eliminates render-blocking Google Fonts request
5. **Hidden source maps** — `.map` files without `sourceMappingURL` comments
6. **ES2020 target** — Skips down-level transpilation
7. **modulePreload** — Aggressive preloading for faster page transitions
8. **Preview API mock** — Vite plugin intercepts `/api/*` during preview

## Remaining Optimization Opportunities

- React + ReactDOM = 133kB (irreducible for React SPA)
- Radix UI = 129kB (59 components, tree-shaken)
- Lighthouse CPU throttling (4x) makes parse/compile appear slower
