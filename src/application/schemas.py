"""
schemas.py - نماذج بيانات الكابلات والتوجيه
=========================================
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class CableType(str, Enum):
    """أنواع الكابلات"""
    FPL = "FPL"        # Fire Alarm Power Limited
    FPLR = "FPLR"      # Fire Alarm Power Limited Riser
    FPLP = "FPLP"      # Fire Alarm Power Limited Plenum
    NP = "NP"           # Non-Power


class WireGauge(str, Enum):
    """مقاييس الأسلاك (AWG)"""
    AWG_18 = "18"
    AWG_16 = "16"
    AWG_14 = "14"
    AWG_12 = "12"


@dataclass
class CableSpecification:
    """مواصفات الكابل"""
    cable_type: CableType = CableType.FPL
    gauge: WireGauge = WireGauge.AWG_18
    
    # المقاومة أوم لكل 1000 قدم
    resistance_ohm_per_1000ft: float = 6.4
    
    # السعة الحالية (أمبير)
    current_capacity_amp: float = 3.0
    
    @property
    def resistance_ohm_per_meter(self) -> float:
        """المقاومة لكل متر"""
        return self.resistance_ohm_per_1000ft / 304.8


@dataclass
class CablePath:
    """مسار كابل واحد"""
    device_id: int
    path_points: List[tuple] = field(default_factory=list)
    total_length_m: float = 0.0
    
    # calculations
    cable_type: CableType = CableType.FPL
    wire_gauge: WireGauge = WireGauge.AWG_18
    
    def calculate_length(self) -> float:
        """حساب الطول الإجمالي للمسار"""
        if len(self.path_points) < 2:
            self.total_length_m = 0.0
            return 0.0
        
        total = 0.0
        for i in range(len(self.path_points) - 1):
            p1 = self.path_points[i]
            p2 = self.path_points[i + 1]
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            total += (dx**2 + dy**2) ** 0.5
        
        self.total_length_m = total
        return total


@dataclass
class LoopGroup:
    """مجموعة حلقة واحدة"""
    loop_id: int
    devices: List[int] = field(default_factory=list)
    
    # calculations
    total_length_m: float = 0.0
    total_current_ma: float = 0.0
    voltage_drop_v: float = 0.0
    is_compliant: bool = True
    
    # panel settings
    panel_voltage_v: float = 24.0
    max_devices: int = 250
    max_current_ma: float = 5000.0  # 5A for panel
    
    # references
    panel_location: Optional[tuple] = None
    cable_spec: CableSpecification = field(default_factory=CableSpecification)
    
    def add_device(self, device_id: int, device_current_ma: float = 0.0):
        """إضافة جهاز للحلقة"""
        self.devices.append(device_id)
        self.total_current_ma += device_current_ma
    
    def calculate_voltage_drop(self) -> float:
        """حساب انخفاض الجهد
        
        V_drop = 2 × I_total × R_per_meter × max_distance
        
       _factor 2 لأن هناك سلكين (ذهاب وعودة)
        """
        # max distance from panel to any device in loop
        max_distance = 0.0
        if self.panel_location and self.devices:
            # Would need device positions - simplified for now
            max_distance = self.total_length_m / len(self.devices)
        
        r_per_m = self.cable_spec.resistance_ohm_per_meter
        self.voltage_drop_v = (
            2 * (self.total_current_ma / 1000.0) * r_per_m * max_distance
        )
        return self.voltage_drop_v
    
    def check_compliance(self) -> bool:
        """التحقق من الامتثال"""
        # Check current
        if self.total_current_ma > self.max_current_ma:
            self.is_compliant = False
            return False
        
        # Check voltage drop (should be < 10% of panel voltage)
        self.calculate_voltage_drop()
        max_allowed_drop = self.panel_voltage_v * 0.10  # 10%
        if self.voltage_drop_v > max_allowed_drop:
            self.is_compliant = False
            return False
        
        # Check device count
        if len(self.devices) > self.max_devices:
            self.is_compliant = False
            return False
        
        self.is_compliant = True
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى قاموس"""
        return {
            'loop_id': self.loop_id,
            'devices': self.devices,
            'device_count': len(self.devices),
            'total_length_m': round(self.total_length_m, 2),
            'total_current_ma': round(self.total_current_ma, 2),
            'voltage_drop_v': round(self.voltage_drop_v, 3),
            'is_compliant': self.is_compliant,
            'panel_voltage_v': self.panel_voltage_v
        }


@dataclass
class RoutingResult:
    """نتيجة التوجيه الكاملة"""
    loops: List[LoopGroup] = field(default_factory=list)
    
    # statistics
    total_devices: int = 0
    total_cable_meters: float = 0.0
    compliant_loops: int = 0
    non_compliant_loops: int = 0
    
    def add_loop(self, loop: LoopGroup):
        """إضافة حلقة"""
        loop.loop_id = len(self.loops) + 1
        self.loops.append(loop)
        self.total_devices += len(loop.devices)
        self.total_cable_meters += loop.total_length_m
        
        if loop.is_compliant:
            self.compliant_loops += 1
        else:
            self.non_compliant_loops += 1
    
    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى قاموس"""
        return {
            'summary': {
                'total_loops': len(self.loops),
                'total_devices': self.total_devices,
                'total_cable_meters': round(self.total_cable_meters, 2),
                'compliant_loops': self.compliant_loops,
                'non_compliant_loops': self.non_compliant_loops
            },
            'loops': [loop.to_dict() for loop in self.loops]
        }
