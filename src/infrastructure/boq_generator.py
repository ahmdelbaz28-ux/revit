"""
boq_generator.py - مولد جداول الكميات (Bill of Quantities)
=====================================================
"""

import csv
import math
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass


@dataclass
class BOQItem:
    """عنصر في جدول الكميات"""
    item_code: str
    description: str
    unit: str
    quantity: float
    unit_price: float = 0.0
    
    @property
    def total_price(self) -> float:
        return self.quantity * self.unit_price


class BOQGenerator:
    """مولد جداول الكميات"""
    
    # Unit prices (example - should be configurable)
    DEVICE_PRICES = {
        'SMOKE_DETECTOR': 45.0,
        'HEAT_DETECTOR': 42.0,
        'PULL_STATION': 85.0,
        'HORN': 55.0,
        'STROBE': 120.0,
        'CONTROL_PANEL': 2500.0,
    }
    
    CABLE_PRICE_PER_METER = 3.5  # $ per meter
    
    def __init__(self):
        self.items = []
    
    def generate_boq(
        self,
        devices: List[Dict],
        cable_paths: List[List[Tuple[float, float]]],
        panel_location: Tuple[float, float],
        routing_result: Dict[str, Any] = None,
        output_file: str = "boq.csv"
    ) -> bool:
        """
        إنشاء جدول الكميات
        
        Args:
            devices: قائمة الأجهزة
            cable_paths: مسارات الكابلات
            panel_location: موقع اللوحة
            routing_result: نتيجة التوجيه
            output_file: اسم الملف الناتج
        """
        self.items = []
        
        # 1. Count devices by type
        device_counts = {}
        for device in devices:
            dtype = device.get('type', 'SMOKE')
            device_counts[dtype] = device_counts.get(dtype, 0) + 1
        
        # 2. Add device items
        for dtype, count in device_counts.items():
            self.items.append(BOQItem(
                item_code=f"FA-{dtype[:4].upper()}",
                description=f"{dtype.replace('_', ' ')} Detector",
                unit="ea",
                quantity=count,
                unit_price=self.DEVICE_PRICES.get(dtype, 50.0)
            ))
        
        # 3. Control panel
        self.items.append(BOQItem(
            item_code="FA-PANEL",
            description="Fire Alarm Control Panel",
            unit="ea",
            quantity=1,
            unit_price=2500.0
        ))
        
        # 4. Cable total
        total_cable = 0.0
        for path in cable_paths:
            total_cable += self._calculate_path_length(path)
        
        self.items.append(BOQItem(
            item_code="FA-CABLE",
            description="Fire Alarm Cable (FPL)",
            unit="m",
            quantity=total_cable,
            unit_price=self.CABLE_PRICE_PER_METER
        ))
        
        # 5. Save to CSV
        return self._save_csv(output_file)
    
    def _calculate_path_length(
        self,
        path: List[Tuple[float, float]]
    ) -> float:
        """حساب طول المسار"""
        if len(path) < 2:
            return 0.0
        
        total = 0.0
        for i in range(len(path) - 1):
            dx = path[i+1][0] - path[i][0]
            dy = path[i+1][1] - path[i][1]
            total += math.sqrt(dx*dx + dy*dy)
        
        return total
    
    def _save_csv(self, output_file: str) -> bool:
        """حفظ إلى CSV"""
        try:
            with open(output_file, 'w', newline='') as f:
                writer = csv.writer(f)
                
                # Header
                writer.writerow([
                    "Item Code",
                    "Description", 
                    "Unit",
                    "Quantity",
                    "Unit Price ($)",
                    "Total Price ($)"
                ])
                writer.writerow([])  # Blank row
                
                # Items
                total_project = 0.0
                for item in self.items:
                    writer.writerow([
                        item.item_code,
                        item.description,
                        item.unit,
                        f"{item.quantity:.1f}",
                        f"{item.unit_price:.2f}",
                        f"{item.total_price:.2f}"
                    ])
                    total_project += item.total_price
                
                # Summary
                writer.writerow([])
                writer.writerow(["", "TOTAL PROJECT COST", "", "", "", f"${total_project:.2f}"])
            
            return True
            
        except Exception as e:
            print(f"Error saving BOQ: {e}")
            return False
    
    def get_summary(self) -> Dict[str, Any]:
        """الحصول على ملخص"""
        return {
            'total_items': len(self.items),
            'total_devices': sum(i.quantity for i in self.items if i.unit == 'ea'),
            'total_cable_m': sum(i.quantity for i in self.items if i.unit == 'm'),
            'total_cost': sum(i.total_price for i in self.items)
        }


def generate_boq(
    output_file: str,
    devices: List[Dict],
    cable_paths: List[List[Tuple[float, float]]],
    panel_location: Tuple[float, float]
) -> bool:
    """دالة ملائمة"""
    generator = BOQGenerator()
    return generator.generate_boq(
        devices=devices,
        cable_paths=cable_paths,
        panel_location=panel_location,
        output_file=output_file
    )
