# 🚀 FireAI Multi-Floor Roadmap

## next-phase: Riser Management & Multi-Floor Support

---

### السيناريو: مبنى من 5 طوابق

**Challenge**: لا يوجد كود يربط الطوابق ببعضها. لا يوجد "مسار صاعد" (Riser) للكابلات بين الطوابق.

---

## Phase 1: Multi-Floor Import

### الهدف
استيراد ملفات DXF متعددة أو ملف واحد متعدد الطبقات

```python
class BuildingExtractor:
    """Extract multi-floor plan"""
    
    def extract_floors(self, dxf_file: str) -> List[Floor]:
        """استخراج جميع الطوابق"""
        # Method 1: Multiple DXF files (floor_1.dxf, floor_2.dxf, ...)
        # Method 2: Single DXF with layer grouping (LAYER_FLOOR_1, LAYER_FLOOR_2, ...)
        # Method 3: Block-based floor plans
        pass
    
    def identify_riser_paths(self, floors: List[Floor]) -> List[Riser]:
        """تحديد مسارات riser العمود shafts"""
        # Common riser shaft location across floors
        # Extract from DXF or calculate center of building
        pass
```

---

## Phase 2: Riser-Aware Cable Routing

### الهدف
ربط الكابلات عبر الطوابق باستخدام Riser

```python
class RiserRouter:
    """توجيه الكابلات مع riser"""
    
    def route_to_riser(self, device: Device, riser: Riser, floor: Floor) -> List[Point]:
        """مسار من الجهاز إلى riser"""
        # 1. Device → Floor riser entry (same floor)
        # 2. Riser vertical path (floor to floor)
        # 3. Riser → Panel (at ground floor)
        pass
    
    def calculate_building_cable(self, floors: List[Floor], risers: List[Riser]) -> BuildingCabling:
        """حساب الكابلات了整个 المبنى"""
        # Aggregate all floors
        # Inter-floor riser cables
        # Total copper cost estimation
        pass
```

---

## Phase 3: Optimal Panel Placement

### الهدف
تحسين موقع اللوحة عبر جميع الطوابق

```python
class PanelOptimizer:
    """تحسين موقع اللوحة"""
    
    def find_optimal_location(self, floors: List[Floor]) -> Point:
        """
       _find_optimal_location: موقع اللوحة الذي يقلل إجمالي الكابلات
        """
        # Try all possible panel locations
        # Calculate total cable for each
        # Return minimum cost location
        pass
```

---

## Phase 4: Performance Optimization

### الهدف
تحسين الأداء للمباني الكبيرة

```python
# Performance benchmarks
BENCHMARKS = {
    "small_building": {"rooms": 10, "nodes": 100, "max_time_sec": 1},
    "medium_building": {"rooms": 50, "nodes": 500, "max_time_sec": 5},
    "large_building": {"rooms": 200, "nodes": 2000, "max_time_sec": 30},
}

# Optimization strategies
OPTIMIZATIONS = {
    "sparse_grid": "Use larger grid spacing for empty areas",
    "parallel_floors": "Process floors in parallel",
    "cache_walls": "Cache wall distances",
}
```

---

## Phase 5: Fire Wall Compliance

### الهدف
ضمان عدم اختراق الكابلات لجدران الحريق

```python
class FireWallCompliance:
    """الامتثال لجدران الحريق"""
    
    def identify_fire_walls(self, dxf_file: str) -> List[Wall]:
        """تحديد جدران الحريق"""
        # Look for: FIRE_WALL, FIRE_RATED, FW-1HR, etc.
        pass
    
    def route_around_fire_wall(self, route: Route, fire_walls: List[Wall]) -> bool:
        """التحقق من عدم اختراق جدار الحريق"""
        return all(not route.crosses(fw) for fw in fire_walls)
```

---

## ملخصRoadmap

| Phase | الوصف | الأولوية |
|-------|-------|---------|
| **Phase 1** | Multi-floor import | P1 |
| **Phase 2** | Riser routing | P1 |
| **Phase 3** | Panel optimization | P2 |
| **Phase 4** | Performance | P2 |
| **Phase 5** | Fire wall compliance | P1 |

---

## الاختبار الحقيقية

```bash
# Floor-by-floor test
for i in {1..5}; do
  fireai build -f floor_${i}.dxf -c 1.0 -p 5,5 -o floor_${i}_out
done

# Check results:
# - Any red violations from beams?
# - Cable through fire wall?
# - Device distribution in interior rooms?
# - Compare total cable lengths across floors
```

---

*Generated: 2025*
*Status: Ready for implementation*
