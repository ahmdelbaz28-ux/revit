# Semantic Failure Manifold (SFM) Specification v1.0

## 0. المبدأ
LossVector in CFL v2.1 is NOT a primitive. It is a projection from a higher-dimensional Semantic Failure Manifold (SFM). This ensures orthogonality, extensibility, and metric stability.

## 1. الإحداثيات الأساسية (Semantic Primitives)
SFM is a Riemannian manifold M with base coordinates:
- ψ₁: Entity Ambiguity (degree of unrecognized identity)
- ψ₂: Spatial Vagueness (geometric imprecision in location)
- ψ₃: Functional Unknownness (inability to determine safety function)
- ψ₄: Topological Ambiguity (uncertainty in connectivity/adjacency)

These primitives are orthogonal and independent. All higher-level loss dimensions are derived from them via the metric tensor.

## 2. الموتّر المتري الدلالي (Semantic Metric Tensor)
g_ij defines the geometric relationship between primitives. It is a symmetric positive-definite matrix that encodes:
- Importance weights between primitives (e.g., functional unknownness may be more severe than spatial vagueness in safety-critical contexts)
- Non-linear coupling (e.g., high entity ambiguity combined with high topological ambiguity amplifies risk multiplicatively)

## 3. إسقاط LossVector (Π_Loss)
Π_Loss: M → R⁴ (the observed LossVector space)
Given a point p ∈ M, the components of LossVector are computed as:
- safety_critical_loss = f(ψ₃)  [functional unknownness directly determines safety criticality]
- unrecognized_ratio = g(ψ₁)
- topology_ambiguity = h(ψ₄)
- semantic_distance = k(ψ₁, ψ₂, ψ₃)  [composite metric]

The functions f, g, h, k are determined by the metric tensor and the geometry of M.

## 4. أسطح القرار (Decision Surfaces)
Instead of hard thresholds, CLB bands are defined by decision surfaces Φ(LossVector) = 0, where Φ is a scalar function derived from the distance in M between the current point and the fully canonical point.
- L0: Φ < τ₀
- L1: τ₀ ≤ Φ < τ₁
- L2: safety_critical_loss = true OR Φ ≥ τ₁
- L3: Φ ≥ τ₂ (catastrophic)

## 5. قابلية التوسع (Extensions)
New loss dimensions (e.g., "regulatory_version_drift") emerge as projections from the same SFM, encoded via the metric tensor. The system does not need new vector storage; only the metric tensor is updated through the Governance Process.

## 6. العلاقة مع CFL
CFL's Interpretation Layer computes a point in SFM (ψ₁...ψ₄). The Canonicalization Layer then computes LossVector via Π_Loss and applies decision surfaces. CFL does not need to know the metric tensor internals; it only calls Π_Loss.