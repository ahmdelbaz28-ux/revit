"""
auto_placement.py - خوارزمية اقتراح مواقع الأجهزة (شبكة متداخلة)
الوصف: توزع الأجهزة بشكل متداخل (Staggered) على كامل طول وعرض الغرفة
       لضمان تغطية مثالية حتى في الغرف الضيقة.
"""
import math
from typing import List, Literal
from src.core.models import Room, Device, DeviceType, Point

def suggest_devices(
    room: Room,
    spacing: float,
    pattern: Literal["staggered", "rectilinear"] = "staggered"
) -> List[Device]:
    """
    يقترح شبكة أجهزة متداخلة (أو مستقيمة) بناءً على أبعاد الغرفة والتباعد المسموح.
    - spacing: أقصى مسافة بين جهازين متجاورين (مثلاً 9.1م لـ NFPA 72).
    """
    if not room.polygon or not room.polygon.exterior:
        return []

    # 1. أبعاد الصندوق المحيط
    coords = [(p.x, p.y) for p in room.polygon.exterior]
    min_x, max_x = min(c[0] for c in coords), max(c[0] for c in coords)
    min_y, max_y = min(c[1] for c in coords), max(c[1] for c in coords)

    room_width = max_x - min_x
    room_height = max_y - min_y

    # 2. لا هامش - نغطي كل المساحة
    edge_margin = max(0.3, spacing / 6)  # Dynamic margin based on spacing to avoid wall edge cases

    # 3. المساحة الفعالة
    eff_w = max(0.0, room_width - 2 * edge_margin)
    eff_h = max(0.0, room_height - 2 * edge_margin)

    # 4. عدد الأعمدة والصفوف
    cols = max(1, math.ceil(eff_w / spacing) + 1) if eff_w > 0 else 1
    rows = max(1, math.ceil(eff_h / spacing) + 1) if eff_h > 0 else 1

    # 5. التباعد الفعلي
    x_step = eff_w / (cols - 1) if cols > 1 else 0.0
    y_step = eff_h / (rows - 1) if rows > 1 else 0.0

    devices = []
    for i in range(cols):
        for j in range(rows):
            x = min_x + edge_margin + i * x_step
            y = min_y + edge_margin + j * y_step

            # الشبكة المتداخلة: إزاحة الصفوف الزوجية
            if pattern == "staggered" and j % 2 == 1:
                x += x_step / 2.0

            pt = Point(x, y)
            if room.polygon.is_point_inside(pt):
                devices.append(Device(
                    position=pt,
                    device_type=DeviceType.SMOKE_DETECTOR,
                    coverage_radius=spacing / 2
                ))
    return devices
