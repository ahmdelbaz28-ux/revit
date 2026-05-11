"""
auto_placement.py - خوارزمية اقتراح مواقع_devices (شبكة ديناميكية)
الوصف: توزع الأجهزة تلقائياً على كامل طول وعرض الغرفة بناءً على التباعد
       المسموح من المعيار، مع مراعاة هامش آمن من الجدران.
"""
import math
from typing import List
from src.core.models import Room, Device, DeviceType, Point

def suggest_devices(room: Room, spacing: float, edge_margin: float = None) -> List[Device]:
    """
    يقترح شبكة أجهزة ديناميكية بناءً على أبعاد الغرفة والتباعد المسموح.
    - spacing: أقصى مسافة بين جهازين متجاورين (مثلاً 9.1م لـ NFPA 72).
    - edge_margin: المسافة الدنيا من الجدار (افتراضي = نصف قطر التغطية).
    """
    if not room.polygon or not room.polygon.exterior:
        return []

    # إذا لم يُعطَ هامش، نستخدم هامش صغير (50 سم) أو أقل من نصف أصغر بُعد
    if edge_margin is None:
        # استخدمmin(half spacing, quarter of smaller dimension)
        edge_margin = min(spacing / 2.0, 1.0)

    # 1. حساب الصندوق المحيط بالغرفة
    coords = [(p.x, p.y) for p in room.polygon.exterior]
    min_x = min(c[0] for c in coords)
    max_x = max(c[0] for c in coords)
    min_y = min(c[1] for c in coords)
    max_y = max(c[1] for c in coords)

    room_width = max_x - min_x
    room_height = max_y - min_y

    # 2. حساب المساحة الفعالة التي يمكن وضع الأجهزة فيها
    effective_width = max(0, room_width - 2 * edge_margin)
    effective_height = max(0, room_height - 2 * edge_margin)

    # إذا كانت المساحة الفعالة سالبة أو صفرية، نضع جهازاً واحداً في المركز
    if effective_width <= 0 and effective_height <= 0:
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        point = Point(center_x, center_y)
        if room.polygon.is_point_inside(point):
            return [Device(position=point, device_type=DeviceType.SMOKE_DETECTOR,
                          coverage_radius=spacing / 2)]
        return []

    # 3. حساب عدد الأعمدة والصفوف
    # نضيف 1 لأن الأجهزة توضع عند الحواف أيضاً
    cols = max(1, math.ceil(effective_width / spacing) + 1)
    rows = max(1, math.ceil(effective_height / spacing) + 1)

    # 4. حساب التباعد الفعلي لضمان توزيع متساوٍ
    x_step = effective_width / (cols - 1) if cols > 1 else 0
    y_step = effective_height / (rows - 1) if rows > 1 else 0

    # 5. توليد نقاط الشبكة
    devices = []
    for i in range(cols):
        for j in range(rows):
            x = min_x + edge_margin + i * x_step
            y = min_y + edge_margin + j * y_step
            point = Point(x, y)

            # التأكد أن النقطة داخل المضلع الفعلي للغرفة (يعالج الأشكال غير المستطيلة)
            if room.polygon.is_point_inside(point):
                devices.append(Device(
                    position=point,
                    device_type=DeviceType.SMOKE_DETECTOR,
                    coverage_radius=spacing / 2,
                    room_id=room.room_id  # Set room_id
                ))

    return devices