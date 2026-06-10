"""
FACP L3 Engine - Deterministic computation core
"""
from typing import Dict, Any, Optional, Protocol
from abc import ABC, abstractmethod
import time
import hashlib
import threading
from ..protocol.message_schema import FACPRequest, FACPResponse
from ..runtime.state_machine import ExecutionState
from ..runtime.resource_manager import ResourceConstraints


class EngineModule(ABC):
    """
    Abstract base class for engine modules
    """
    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the module with given parameters
        """
        pass
    
    @abstractmethod
    def validate_input(self, params: Dict[str, Any]) -> tuple[bool, list]:
        """
        Validate input parameters
        Returns: (is_valid, error_list)
        """
        pass


class Calculator(EngineModule):
    """
    Calculation engine module
    """
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform calculations based on parameters
        """
        # Extract calculation type and parameters
        calc_type = params.get("type", "generic")
        calc_params = params.get("params", {})
        
        # Perform calculation based on type
        if calc_type == "voltage_drop":
            return self._calculate_voltage_drop(calc_params)
        elif calc_type == "cable_sizing":
            return self._calculate_cable_sizing(calc_params)
        elif calc_type == "load_calculation":
            return self._calculate_load(calc_params)
        elif calc_type == "battery_sizing":
            return self._calculate_battery_sizing(calc_params)
        else:
            # Generic calculation
            return {
                "result": self._perform_generic_calculation(calc_params),
                "calculation_type": calc_type,
                "calculated_at": time.time(),
                "success": True
            }
    
    def validate_input(self, params: Dict[str, Any]) -> tuple[bool, list]:
        """
        Validate calculation parameters
        """
        errors = []
        
        calc_type = params.get("type", "")
        calc_params = params.get("params", {})
        
        if not calc_type:
            errors.append("Calculation type is required")
        
        if not isinstance(calc_params, dict):
            errors.append("Calculation parameters must be a dictionary")
        
        # Validate based on calculation type
        if calc_type == "voltage_drop":
            required_fields = ["current", "length", "resistance"]
            for field in required_fields:
                if field not in calc_params:
                    errors.append(f"Missing required field for voltage drop calculation: {field}")
        
        elif calc_type == "cable_sizing":
            required_fields = ["current", "material", "ambient_temperature"]
            for field in required_fields:
                if field not in calc_params:
                    errors.append(f"Missing required field for cable sizing calculation: {field}")
        
        elif calc_type == "load_calculation":
            required_fields = ["connected_load", "diversity_factor"]
            for field in required_fields:
                if field not in calc_params:
                    errors.append(f"Missing required field for load calculation: {field}")
        
        elif calc_type == "battery_sizing":
            required_fields = ["load_current", "backup_time", "efficiency"]
            for field in required_fields:
                if field not in calc_params:
                    errors.append(f"Missing required field for battery sizing calculation: {field}")
        
        return len(errors) == 0, errors
    
    def _calculate_voltage_drop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate voltage drop
        """
        current = params.get("current", 0)
        length = params.get("length", 0)
        resistance = params.get("resistance", 0.01)  # Default resistance per meter
        system_type = params.get("system_type", "single_phase")  # single_phase or three_phase
        
        # Calculate voltage drop
        if system_type == "three_phase":
            voltage_drop = 1.732 * current * length * resistance
        else:
            voltage_drop = 2 * current * length * resistance
        
        # Calculate percentage voltage drop
        supply_voltage = params.get("supply_voltage", 230)  # Default 230V
        voltage_drop_percentage = (voltage_drop / supply_voltage) * 100
        
        return {
            "voltage_drop_volts": round(voltage_drop, 2),
            "voltage_drop_percentage": round(voltage_drop_percentage, 2),
            "acceptable": voltage_drop_percentage <= 3,  # Standard 3% limit
            "supply_voltage": supply_voltage,
            "calculated_at": time.time()
        }
    
    def _calculate_cable_sizing(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate appropriate cable size
        """
        current = params.get("current", 0)
        material = params.get("material", "copper")  # copper or aluminum
        ambient_temp = params.get("ambient_temperature", 30)  # degrees Celsius
        installation_method = params.get("installation_method", "conduit")  # conduit, tray, buried
        
        # Base ampacity values (simplified)
        base_ampacities = {
            "copper": {
                "1.5mm2": 16,
                "2.5mm2": 25,
                "4mm2": 32,
                "6mm2": 40,
                "10mm2": 50,
                "16mm2": 68,
                "25mm2": 95
            },
            "aluminum": {
                "1.5mm2": 12,
                "2.5mm2": 20,
                "4mm2": 25,
                "6mm2": 32,
                "10mm2": 40,
                "16mm2": 55,
                "25mm2": 75
            }
        }
        
        # Temperature correction factor (simplified)
        temp_correction = 1.0 - ((ambient_temp - 30) * 0.005)  # Approximate
        
        # Find minimum required cable size
        required_current = current / temp_correction
        material_ampacities = base_ampacities.get(material, base_ampacities["copper"])
        
        selected_size = None
        for size, ampacity in sorted(material_ampacities.items(), key=lambda x: x[1]):
            if ampacity >= required_current:
                selected_size = size
                break
        
        if not selected_size:
            selected_size = list(material_ampacities.keys())[-1]  # Use largest available
        
        return {
            "recommended_cable_size": selected_size,
            "material": material,
            "required_current": round(required_current, 2),
            "ambient_temperature": ambient_temp,
            "temperature_correction": round(temp_correction, 3),
            "calculated_at": time.time()
        }
    
    def _calculate_load(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate electrical load
        """
        connected_load = params.get("connected_load", 0)  # kW
        diversity_factor = params.get("diversity_factor", 1.0)
        power_factor = params.get("power_factor", 0.8)
        
        diversified_load = connected_load * diversity_factor
        apparent_power = diversified_load / power_factor  # kVA
        full_load_current = params.get("voltage", 400)  # Default 400V for 3-phase
        
        # Calculate full load current (simplified)
        if params.get("system_type") == "single_phase":
            full_load_current = (diversified_load * 1000) / (230 * power_factor)
        else:
            full_load_current = (diversified_load * 1000) / (1.732 * 400 * power_factor)
        
        return {
            "connected_load_kw": connected_load,
            "diversity_factor": diversity_factor,
            "diversified_load_kw": round(diversified_load, 2),
            "apparent_power_kva": round(apparent_power, 2),
            "power_factor": power_factor,
            "estimated_full_load_current_a": round(full_load_current, 2),
            "calculated_at": time.time()
        }
    
    def _calculate_battery_sizing(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate battery sizing for backup systems
        """
        load_current = params.get("load_current", 0)  # Amps
        backup_time = params.get("backup_time", 1)  # Hours
        efficiency = params.get("efficiency", 0.85)  # 85% efficiency
        depth_of_discharge = params.get("depth_of_discharge", 0.8)  # 80% DoD
        temperature_factor = params.get("temperature_factor", 1.0)  # Temperature derating
        
        # Calculate required battery capacity
        required_capacity = (load_current * backup_time) / (efficiency * depth_of_discharge)
        derated_capacity = required_capacity / temperature_factor
        
        # Recommend standard battery sizes
        standard_sizes = [7, 12, 18, 26, 33, 40, 65, 100, 140, 200]
        recommended_size = min([size for size in standard_sizes if size >= derated_capacity], default=max(standard_sizes))
        
        return {
            "required_load_current_a": load_current,
            "required_backup_time_h": backup_time,
            "efficiency_factor": efficiency,
            "depth_of_discharge": depth_of_discharge,
            "temperature_factor": temperature_factor,
            "required_capacity_ah": round(required_capacity, 2),
            "derated_capacity_ah": round(derated_capacity, 2),
            "recommended_battery_size_ah": recommended_size,
            "calculated_at": time.time()
        }
    
    def _perform_generic_calculation(self, params: Dict[str, Any]) -> Any:
        """
        Perform a generic calculation
        """
        # This is a simplified example - in real implementation, 
        # this would be more sophisticated
        operation = params.get("operation", "add")
        operands = params.get("operands", [])
        
        if operation == "add" and len(operands) >= 2:
            return sum(operands)
        elif operation == "multiply" and len(operands) >= 2:
            result = 1
            for operand in operands:
                result *= operand
            return result
        else:
            return {"error": "Unsupported operation or insufficient operands"}


class Validator(EngineModule):
    """
    Validation engine module
    """
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform validation based on parameters
        """
        validation_type = params.get("type", "generic")
        validation_params = params.get("params", {})
        
        if validation_type == "compliance_nfpa":
            return self._validate_nfpa_compliance(validation_params)
        elif validation_type == "compliance_iec":
            return self._validate_iec_compliance(validation_params)
        elif validation_type == "compliance_egyptian":
            return self._validate_egyptian_compliance(validation_params)
        elif validation_type == "compliance_saudi":
            return self._validate_saudi_compliance(validation_params)
        else:
            # Generic validation
            return {
                "valid": self._perform_generic_validation(validation_params),
                "validation_type": validation_type,
                "validated_at": time.time(),
                "success": True
            }
    
    def validate_input(self, params: Dict[str, Any]) -> tuple[bool, list]:
        """
        Validate validation parameters
        """
        errors = []
        
        validation_type = params.get("type", "")
        validation_params = params.get("params", {})
        
        if not validation_type:
            errors.append("Validation type is required")
        
        if not isinstance(validation_params, dict):
            errors.append("Validation parameters must be a dictionary")
        
        return len(errors) == 0, errors
    
    def _validate_nfpa_compliance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate compliance with NFPA standards
        """
        # This would contain actual NFPA validation logic
        # For now, returning a sample validation result
        system_type = params.get("system_type", "fire_alarm")
        components = params.get("components", [])
        
        issues = []
        
        # Sample validation rules
        if system_type == "fire_alarm":
            # Check for proper notification appliance coverage
            notification_appliances = [c for c in components if c.get("type") == "notification_appliance"]
            if len(notification_appliances) == 0:
                issues.append("No notification appliances found")
            elif len(notification_appliances) < 2:
                issues.append("Minimum 2 notification appliances required per NFPA 72")
        
        # Check for proper initiating device spacing
        initiating_devices = [c for c in components if c.get("type") == "initiating_device"]
        if len(initiating_devices) == 0:
            issues.append("No initiating devices found")
        
        return {
            "compliant": len(issues) == 0,
            "issues_found": issues,
            "system_type": system_type,
            "components_validated": len(components),
            "validated_at": time.time()
        }
    
    def _validate_iec_compliance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate compliance with IEC standards
        """
        # This would contain actual IEC validation logic
        equipment_type = params.get("equipment_type", "switchgear")
        ratings = params.get("ratings", {})
        
        issues = []
        
        # Sample validation rules
        if equipment_type == "switchgear":
            required_ratings = ["voltage_rating", "current_rating", "withstand_rating"]
            for rating in required_ratings:
                if rating not in ratings:
                    issues.append(f"Missing {rating} for IEC compliance")
        
        return {
            "compliant": len(issues) == 0,
            "issues_found": issues,
            "equipment_type": equipment_type,
            "validated_at": time.time()
        }
    
    def _validate_egyptian_compliance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate compliance with Egyptian electrical standards
        """
        # This would contain actual Egyptian standard validation logic
        system_type = params.get("system_type", "distribution")
        location = params.get("location", "industrial")
        
        issues = []
        
        # Sample validation rules for Egyptian standards
        if location == "residential":
            # Check for RCCB requirements
            has_rccb = any(comp.get("type") == "rcb" for comp in params.get("components", []))
            if not has_rccb:
                issues.append("RCCB required for residential installations per Egyptian standards")
        
        return {
            "compliant": len(issues) == 0,
            "issues_found": issues,
            "system_type": system_type,
            "location": location,
            "validated_at": time.time()
        }
    
    def _validate_saudi_compliance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate compliance with Saudi electrical standards
        """
        # This would contain actual Saudi standard validation logic
        voltage_system = params.get("voltage_system", "low_voltage")
        installation_type = params.get("installation_type", "indoor")
        
        issues = []
        
        # Sample validation rules for Saudi standards
        if voltage_system == "low_voltage" and installation_type == "outdoor":
            # Check for proper IP ratings
            has_proper_ip = any(comp.get("ip_rating", "IP20").startswith("IP") 
                              for comp in params.get("components", []))
            if not has_proper_ip:
                issues.append("Proper IP rating required for outdoor low voltage installations per Saudi standards")
        
        return {
            "compliant": len(issues) == 0,
            "issues_found": issues,
            "voltage_system": voltage_system,
            "installation_type": installation_type,
            "validated_at": time.time()
        }
    
    def _perform_generic_validation(self, params: Dict[str, Any]) -> bool:
        """
        Perform generic validation
        """
        # This is a simplified example
        data = params.get("data", {})
        rules = params.get("rules", [])
        
        # Apply simple validation rules
        for rule in rules:
            field = rule.get("field")
            operator = rule.get("operator")
            expected_value = rule.get("value")
            
            actual_value = data.get(field)
            
            if operator == "equals" and actual_value != expected_value:
                return False
            elif operator == "greater_than" and actual_value <= expected_value:
                return False
            elif operator == "less_than" and actual_value >= expected_value:
                return False
        
        return True


class Transformer(EngineModule):
    """
    Transformation engine module
    """
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform data transformation
        """
        transform_type = params.get("type", "generic")
        input_data = params.get("input", {})
        
        if transform_type == "dwg_to_bim":
            return self._transform_dwg_to_bim(input_data)
        elif transform_type == "bim_to_dwg":
            return self._transform_bim_to_dwg(input_data)
        elif transform_type == "format_conversion":
            return self._transform_format(input_data, params.get("target_format"))
        else:
            # Generic transformation
            return {
                "transformed_data": self._perform_generic_transform(input_data),
                "transform_type": transform_type,
                "transformed_at": time.time(),
                "success": True
            }
    
    def validate_input(self, params: Dict[str, Any]) -> tuple[bool, list]:
        """
        Validate transformation parameters
        """
        errors = []
        
        transform_type = params.get("type", "")
        input_data = params.get("input", {})
        
        if not transform_type:
            errors.append("Transform type is required")
        
        if not isinstance(input_data, dict):
            errors.append("Input data must be a dictionary")
        
        return len(errors) == 0, errors
    
    def _transform_dwg_to_bim(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform DWG data to BIM format
        """
        # This would contain actual DWG to BIM transformation logic
        # For now, returning a sample transformation result
        dwg_entities = input_data.get("entities", [])
        metadata = input_data.get("metadata", {})
        
        # Simulate transformation process
        bim_elements = []
        for entity in dwg_entities:
            element_type = entity.get("type", "unknown")
            
            if element_type in ["wall", "line"]:
                bim_element = {
                    "type": "wall",
                    "start_point": entity.get("start", [0, 0, 0]),
                    "end_point": entity.get("end", [0, 0, 0]),
                    "material": entity.get("layer", "default"),
                    "properties": {
                        "height": entity.get("height", 3000),
                        "thickness": entity.get("thickness", 200)
                    }
                }
            elif element_type in ["door", "opening"]:
                bim_element = {
                    "type": "door",
                    "location": entity.get("center", [0, 0, 0]),
                    "properties": {
                        "width": entity.get("width", 900),
                        "height": entity.get("height", 2100)
                    }
                }
            elif element_type in ["window", "window_frame"]:
                bim_element = {
                    "type": "window",
                    "location": entity.get("center", [0, 0, 0]),
                    "properties": {
                        "width": entity.get("width", 1200),
                        "height": entity.get("height", 1200)
                    }
                }
            else:
                bim_element = {
                    "type": "generic",
                    "raw_data": entity
                }
            
            bim_elements.append(bim_element)
        
        return {
            "bim_elements": bim_elements,
            "original_entity_count": len(dwg_entities),
            "converted_element_count": len(bim_elements),
            "transformation_metadata": metadata,
            "transformed_at": time.time()
        }
    
    def _transform_bim_to_dwg(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform BIM data to DWG format
        """
        # This would contain actual BIM to DWG transformation logic
        bim_elements = input_data.get("elements", [])
        metadata = input_data.get("metadata", {})
        
        # Simulate transformation process
        dwg_entities = []
        for element in bim_elements:
            element_type = element.get("type", "unknown")
            
            if element_type == "wall":
                dwg_entity = {
                    "type": "line",
                    "start": element.get("start_point", [0, 0, 0]),
                    "end": element.get("end_point", [0, 0, 0]),
                    "layer": element.get("material", "walls"),
                    "properties": element.get("properties", {})
                }
            elif element_type == "door":
                dwg_entity = {
                    "type": "insert",
                    "block_name": "door",
                    "insertion_point": element.get("location", [0, 0, 0]),
                    "scale": [1, 1, 1],
                    "rotation": 0,
                    "properties": element.get("properties", {})
                }
            elif element_type == "window":
                dwg_entity = {
                    "type": "insert",
                    "block_name": "window",
                    "insertion_point": element.get("location", [0, 0, 0]),
                    "scale": [1, 1, 1],
                    "rotation": 0,
                    "properties": element.get("properties", {})
                }
            else:
                dwg_entity = {
                    "type": "point",
                    "location": element.get("location", [0, 0, 0]),
                    "properties": element
                }
            
            dwg_entities.append(dwg_entity)
        
        return {
            "dwg_entities": dwg_entities,
            "original_element_count": len(bim_elements),
            "converted_entity_count": len(dwg_entities),
            "transformation_metadata": metadata,
            "transformed_at": time.time()
        }
    
    def _transform_format(self, input_data: Dict[str, Any], target_format: str) -> Dict[str, Any]:
        """
        Transform to target format
        """
        # This would contain actual format transformation logic
        return {
            "transformed_data": input_data,  # Placeholder
            "target_format": target_format,
            "format_transformed_at": time.time()
        }
    
    def _perform_generic_transform(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform generic transformation
        """
        # This is a simplified example
        operation = input_data.get("operation", "identity")
        data = input_data.get("data", {})
        
        if operation == "uppercase":
            if isinstance(data, str):
                return data.upper()
            elif isinstance(data, dict):
                return {k.upper(): v for k, v in data.items()}
        elif operation == "normalize":
            # Normalize numeric values
            normalized = {}
            for k, v in data.items():
                if isinstance(v, (int, float)):
                    normalized[k] = round(v, 2)
                else:
                    normalized[k] = v
            return normalized
        else:
            return data  # Identity transform


class Engine:
    """
    Main Engine class that coordinates modules
    """
    def __init__(self, resource_constraints: ResourceConstraints = None):
        self.calculator = Calculator()
        self.validator = Validator()
        self.transformer = Transformer()
        self.modules = {
            "calculate": self.calculator,
            "validate": self.validator,
            "transform": self.transformer
        }
        self.resource_constraints = resource_constraints or ResourceConstraints()
        self.execution_stats = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0
        }
        self.lock = threading.Lock()
    
    def execute_method(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a method with given parameters
        """
        with self.lock:
            self.execution_stats["total_executions"] += 1
        
        # Determine which module to use based on method
        if method.startswith("engine.calculate") or method.startswith("calc."):
            module = self.calculator
        elif method.startswith("engine.validate") or method.startswith("validate."):
            module = self.validator
        elif method.startswith("engine.transform") or method.startswith("transform."):
            module = self.transformer
        else:
            # Default to calculator for unknown methods
            module = self.calculator
        
        # Validate input
        is_valid, errors = module.validate_input({"params": params})
        if not is_valid:
            with self.lock:
                self.execution_stats["failed_executions"] += 1
            return {
                "success": False,
                "error": f"Input validation failed: {', '.join(errors)}",
                "method": method
            }
        
        try:
            # Execute the module
            result = module.execute({"params": params})
            
            with self.lock:
                self.execution_stats["successful_executions"] += 1
            
            return {
                "success": True,
                "result": result,
                "method": method,
                "executed_at": time.time()
            }
        except Exception as e:
            with self.lock:
                self.execution_stats["failed_executions"] += 1
            return {
                "success": False,
                "error": f"Execution failed: {str(e)}",
                "method": method
            }
    
    def get_module(self, module_name: str) -> Optional[EngineModule]:
        """
        Get a specific module by name
        """
        return self.modules.get(module_name)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get engine statistics
        """
        with self.lock:
            return self.execution_stats.copy()
    
    def reset_stats(self):
        """
        Reset engine statistics
        """
        with self.lock:
            self.execution_stats = {
                "total_executions": 0,
                "successful_executions": 0,
                "failed_executions": 0
            }


class DeterministicEngine(Engine):
    """
    Deterministic version of the engine that ensures reproducible results
    """
    def __init__(self, resource_constraints: ResourceConstraints = None):
        super().__init__(resource_constraints)
        self.deterministic_mode = True
    
    def execute_method(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute method in deterministic mode
        """
        # Create a deterministic input hash to ensure reproducible results
        input_hash = self._create_deterministic_hash(method, params)
        
        # Set a fixed random seed based on the input hash to ensure deterministic behavior
        import random
        random.seed(input_hash % (2**32))  # Use modulo to fit in 32-bit integer range
        
        # Execute the method
        result = super().execute_method(method, params)
        
        # Add deterministic signature to the result
        result["deterministic_signature"] = input_hash
        
        return result
    
    def _create_deterministic_hash(self, method: str, params: Dict[str, Any]) -> int:
        """
        Create a deterministic hash of the input
        """
        import json
        input_str = f"{method}{json.dumps(params, sort_keys=True, default=str)}"
        return int(hashlib.sha256(input_str.encode()).hexdigest(), 16)