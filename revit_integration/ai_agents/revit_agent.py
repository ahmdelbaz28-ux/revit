"""
ETAP-AI-WORK Revit AI Agent
==========================

AI agent for inspecting BIM models, extracting electrical assets, and synchronizing with Digital Twin.

Principal Software Architect: Eng. Ahmed Elbaz
"""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import asyncio

from revit_integration.dto.revit_dto import RevitElementDTO, ElectricalAssetDTO
from revit_integration.services.revit_sync_service import RevitSyncService
from revit_integration.mappings.category_mapper import CategoryMapper
from revit_integration.events.event_publisher import RevitEventPublisher


class RevitAgent:
    """
    AI Agent for Revit BIM model inspection and analysis.
    Capabilities include BIM model inspection, electrical asset extraction, 
    clash detection preparation, model validation, and Digital Twin synchronization.
    """
    
    def __init__(self, sync_service: RevitSyncService, event_publisher: RevitEventPublisher = None):
        self.logger = logging.getLogger(__name__)
        self.sync_service = sync_service
        self.event_publisher = event_publisher or RevitEventPublisher()
        self.category_mapper = CategoryMapper()
        self.capabilities = [
            "bim_model_inspection",
            "electrical_asset_extraction", 
            "clash_detection_preparation",
            "model_validation",
            "digital_twin_synchronization"
        ]
    
    async def inspect_bim_model(self, project_id: str, model_data: List[RevitElementDTO]) -> Dict[str, Any]:
        """
        Inspect BIM model for completeness and quality.
        
        Args:
            project_id: ID of the project
            model_data: List of model elements
            
        Returns:
            Dict: Inspection results
        """
        self.logger.info(f"Inspecting BIM model for project {project_id}")
        
        inspection_results = {
            "project_id": project_id,
            "inspection_date": datetime.utcnow().isoformat(),
            "total_elements": len(model_data),
            "categories_found": [],
            "issues_found": [],
            "completeness_score": 0.0,
            "recommendations": []
        }
        
        # Collect unique categories
        categories = set()
        for element in model_data:
            categories.add(element.category)
        
        inspection_results["categories_found"] = list(categories)
        
        # Check for common issues
        issues = []
        recommendations = []
        
        # Check for missing parameters in electrical equipment
        electrical_elements = [elem for elem in model_data if 'electrical' in elem.category.lower()]
        for elem in electrical_elements:
            missing_params = []
            if not elem.parameters.get('Voltage'):
                missing_params.append('Voltage')
            if not elem.parameters.get('Power'):
                missing_params.append('Power')
            
            if missing_params:
                issues.append({
                    "element_id": elem.id,
                    "element_name": elem.name,
                    "category": elem.category,
                    "missing_parameters": missing_params,
                    "severity": "medium"
                })
        
        # Check for spatial elements without location
        spatial_elements = [elem for elem in model_data if elem.category.lower() in ['rooms', 'spaces']]
        for elem in spatial_elements:
            if not elem.location:
                issues.append({
                    "element_id": elem.id,
                    "element_name": elem.name,
                    "category": elem.category,
                    "issue": "Missing location information",
                    "severity": "high"
                })
        
        inspection_results["issues_found"] = issues
        
        # Calculate completeness score
        total_elements = len(model_data)
        problematic_elements = len(issues)
        if total_elements > 0:
            completeness_score = ((total_elements - problematic_elements) / total_elements) * 100
            inspection_results["completeness_score"] = round(completeness_score, 2)
        
        # Generate recommendations
        if issues:
            recommendations.append("Address missing parameter issues in electrical equipment")
            recommendations.append("Ensure all spatial elements have location information")
            if any(issue["severity"] == "high" for issue in issues):
                recommendations.append("Prioritize fixing high severity issues")
        
        inspection_results["recommendations"] = recommendations
        
        # Publish inspection completed event
        await self.event_publisher.publish_event("RevitModelInspected", {
            "project_id": project_id,
            "total_elements": total_elements,
            "issues_found": len(issues),
            "completeness_score": inspection_results["completeness_score"],
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return inspection_results
    
    async def extract_electrical_assets(self, model_data: List[RevitElementDTO]) -> List[ElectricalAssetDTO]:
        """
        Extract electrical assets from BIM model.
        
        Args:
            model_data: List of model elements
            
        Returns:
            List[ElectricalAssetDTO]: Extracted electrical assets
        """
        self.logger.info(f"Extracting electrical assets from model with {len(model_data)} elements")
        
        electrical_assets = []
        
        for element in model_data:
            # Use the adapter to extract electrical assets
            # For this simulation, we'll create mock electrical assets for electrical equipment
            if 'electrical' in element.category.lower() or 'panel' in element.category.lower():
                # Create electrical asset DTO
                asset = ElectricalAssetDTO(
                    element_id=element.id,
                    asset_type=self.category_mapper.classify_equipment_type(element.name, element.category),
                    name=element.name,
                    voltage_rating=element.parameters.get('Voltage') or element.parameters.get('VoltageRating'),
                    power_rating=element.parameters.get('Power') or element.parameters.get('PowerRating'),
                    manufacturer=element.parameters.get('Manufacturer', ''),
                    model=element.parameters.get('Model', ''),
                    serial_number=element.parameters.get('SerialNumber', ''),
                    capacity=element.parameters.get('Capacity'),
                    connections=[],  # Will be populated during sync
                    location_coordinates=element.location,
                    electrical_parameters={k: v for k, v in element.parameters.items() if 'electrical' in k.lower() or k in ['Voltage', 'Power', 'Current']}
                )
                electrical_assets.append(asset)
        
        self.logger.info(f"Extracted {len(electrical_assets)} electrical assets")
        
        # Publish electrical assets extracted event
        await self.event_publisher.publish_event("ElectricalAssetsExtracted", {
            "asset_count": len(electrical_assets),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return electrical_assets
    
    async def prepare_clash_detection_data(self, model_data: List[RevitElementDTO]) -> Dict[str, Any]:
        """
        Prepare data for clash detection analysis.
        
        Args:
            model_data: List of model elements
            
        Returns:
            Dict: Clash detection data
        """
        self.logger.info(f"Preparing clash detection data for {len(model_data)} elements")
        
        # Group elements by discipline/system
        systems = {
            "electrical": [],
            "mechanical": [],
            "structural": [],
            "architectural": [],
            "plumbing": []
        }
        
        for element in model_data:
            cat_lower = element.category.lower()
            if 'electrical' in cat_lower or 'power' in cat_lower:
                systems["electrical"].append(element)
            elif 'mechanical' in cat_lower or 'hvac' in cat_lower:
                systems["mechanical"].append(element)
            elif 'struct' in cat_lower:
                systems["structural"].append(element)
            elif 'arch' in cat_lower or 'wall' in cat_lower or 'door' in cat_lower or 'window' in cat_lower:
                systems["architectural"].append(element)
            elif 'plumb' in cat_lower or 'pipe' in cat_lower:
                systems["plumbing"].append(element)
            else:
                # Default to architectural for unknown categories
                systems["architectural"].append(element)
        
        clash_detection_data = {
            "systems": systems,
            "element_count_by_system": {sys: len(elems) for sys, elems in systems.items()},
            "potential_conflict_zones": [],  # Would be populated with actual clash detection logic
            "analysis_date": datetime.utcnow().isoformat()
        }
        
        # Identify potential conflict zones based on overlapping locations
        # This is a simplified approach - real clash detection would be more sophisticated
        locations_with_multiple_systems = {}
        
        for system, elements in systems.items():
            for element in elements:
                if element.location:
                    loc_key = f"{element.location['x']}_{element.location['y']}_{element.location['z']}"
                    if loc_key not in locations_with_multiple_systems:
                        locations_with_multiple_systems[loc_key] = []
                    locations_with_multiple_systems[loc_key].append({
                        "system": system,
                        "element_id": element.id,
                        "element_name": element.name
                    })
        
        # Find locations with multiple systems (potential clashes)
        for loc_key, items in locations_with_multiple_systems.items():
            if len(items) > 1:
                clash_detection_data["potential_conflict_zones"].append({
                    "location": loc_key,
                    "conflicting_items": items,
                    "conflict_type": "spatial_overlap"
                })
        
        self.logger.info(f"Found {len(clash_detection_data['potential_conflict_zones'])} potential conflict zones")
        
        return clash_detection_data
    
    async def validate_model(self, model_data: List[RevitElementDTO]) -> Dict[str, Any]:
        """
        Validate BIM model against standards and requirements.
        
        Args:
            model_data: List of model elements
            
        Returns:
            Dict: Validation results
        """
        self.logger.info(f"Validating BIM model with {len(model_data)} elements")
        
        validation_results = {
            "total_elements": len(model_data),
            "valid_elements": 0,
            "invalid_elements": 0,
            "validation_rules_applied": [],
            "errors": [],
            "warnings": [],
            "validation_date": datetime.utcnow().isoformat()
        }
        
        valid_count = 0
        invalid_count = 0
        
        # Apply validation rules
        for element in model_data:
            element_errors = []
            element_warnings = []
            
            # Check for required fields
            if not element.id or element.id == "":
                element_errors.append("Missing element ID")
            
            if not element.name or element.name == "":
                element_warnings.append("Missing element name")
            
            # Check category mapping validity
            validation_result = self.category_mapper.validate_mapping({
                'id': element.id,
                'name': element.name,
                'category': element.category,
                'parameters': element.parameters
            })
            
            if not validation_result['valid']:
                element_errors.extend(validation_result['issues'])
            
            # Add to results
            if element_errors:
                validation_results["errors"].append({
                    "element_id": element.id,
                    "element_name": element.name,
                    "errors": element_errors
                })
                invalid_count += 1
            else:
                valid_count += 1
            
            if element_warnings:
                validation_results["warnings"].append({
                    "element_id": element.id,
                    "element_name": element.name,
                    "warnings": element_warnings
                })
        
        validation_results["valid_elements"] = valid_count
        validation_results["invalid_elements"] = invalid_count
        
        # Calculate validation score
        if len(model_data) > 0:
            validation_score = (valid_count / len(model_data)) * 100
            validation_results["validation_score"] = round(validation_score, 2)
        
        validation_results["validation_rules_applied"] = [
            "required_fields_check",
            "category_mapping_validation",
            "parameter_validation"
        ]
        
        self.logger.info(f"Validation completed: {valid_count} valid, {invalid_count} invalid elements")
        
        return validation_results
    
    async def synchronize_with_digital_twin(self, project_id: str, model_data: List[RevitElementDTO]) -> Dict[str, Any]:
        """
        Synchronize model data with the Digital Twin.
        
        Args:
            project_id: ID of the project
            model_data: List of model elements to sync
            
        Returns:
            Dict: Synchronization results
        """
        self.logger.info(f"Synchronizing project {project_id} with {len(model_data)} elements to Digital Twin")
        
        # Create a mock RevitProjectDTO for the sync service
        from revit_integration.dto.revit_dto import RevitProjectDTO
        project_dto = RevitProjectDTO(
            project_id=project_id,
            project_name=f"Project_{project_id}",
            status="active"
        )
        
        # Use the sync service to perform the synchronization
        sync_status = await self.sync_service.sync_project(project_dto)
        
        sync_results = {
            "project_id": project_id,
            "sync_id": sync_status.sync_id,
            "status": sync_status.status,
            "elements_processed": sync_status.processed_elements,
            "elements_successful": sync_status.successful_elements,
            "elements_failed": sync_status.failed_elements,
            "start_time": sync_status.start_time.isoformat(),
            "end_time": sync_status.end_time.isoformat() if sync_status.end_time else None,
            "duration_seconds": (sync_status.end_time - sync_status.start_time).total_seconds() if sync_status.end_time else None
        }
        
        self.logger.info(f"Datetime Twin synchronization completed: {sync_results['elements_successful']} successful, {sync_results['elements_failed']} failed")
        
        return sync_results
    
    async def analyze_electrical_system(self, electrical_assets: List[ElectricalAssetDTO]) -> Dict[str, Any]:
        """
        Analyze the electrical system based on extracted assets.
        
        Args:
            electrical_assets: List of electrical assets
            
        Returns:
            Dict: Electrical system analysis
        """
        self.logger.info(f"Analyzing electrical system with {len(electrical_assets)} assets")
        
        analysis = {
            "total_assets": len(electrical_assets),
            "by_type": {},
            "by_voltage": {},
            "by_power_rating": {},
            "critical_assets": [],
            "system_topology": {},
            "analysis_date": datetime.utcnow().isoformat()
        }
        
        # Count by type
        for asset in electrical_assets:
            asset_type = asset.asset_type
            if asset_type not in analysis["by_type"]:
                analysis["by_type"][asset_type] = 0
            analysis["by_type"][asset_type] += 1
            
            # Group by voltage
            if asset.voltage_rating:
                voltage_range = f"{int(asset.voltage_rating // 100) * 100}-{int(asset.voltage_rating // 100 + 1) * 100}V"
                if voltage_range not in analysis["by_voltage"]:
                    analysis["by_voltage"][voltage_range] = 0
                analysis["by_voltage"][voltage_range] += 1
            
            # Identify critical assets (high power, critical systems)
            if asset.power_rating and asset.power_rating > 1000:  # Over 1kW
                analysis["critical_assets"].append({
                    "element_id": asset.element_id,
                    "name": asset.name,
                    "asset_type": asset.asset_type,
                    "power_rating": asset.power_rating,
                    "criticality": "high_power"
                })
            
            if asset.asset_type in ["Transformer", "Generator", "UPS"]:
                analysis["critical_assets"].append({
                    "element_id": asset.element_id,
                    "name": asset.name,
                    "asset_type": asset.asset_type,
                    "criticality": "critical_infrastructure"
                })
        
        # Calculate system topology based on connections (simplified)
        # In a real implementation, this would analyze actual connections
        analysis["system_topology"] = {
            "primary_feeds": len([a for a in electrical_assets if a.asset_type == "Panelboard"]),
            "distribution_points": len([a for a in electrical_assets if a.asset_type in ["Transformer", "Switchgear"]]),
            "end_devices": len([a for a in electrical_assets if a.asset_type == "ElectricalEquipment"])
        }
        
        self.logger.info(f"Electrical system analysis completed: {len(analysis['critical_assets'])} critical assets identified")
        
        return analysis
    
    async def generate_report(self, inspection_results: Dict[str, Any], 
                             validation_results: Dict[str, Any], 
                             analysis_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a comprehensive report combining all analysis results.
        
        Args:
            inspection_results: Results from BIM inspection
            validation_results: Results from model validation
            analysis_results: Results from electrical analysis
            
        Returns:
            Dict: Comprehensive report
        """
        self.logger.info("Generating comprehensive Revit integration report")
        
        report = {
            "report_date": datetime.utcnow().isoformat(),
            "executive_summary": {
                "model_quality_score": inspection_results.get("completeness_score", 0),
                "validation_score": validation_results.get("validation_score", 0),
                "total_elements": inspection_results.get("total_elements", 0),
                "critical_findings": len(analysis_results.get("critical_assets", [])),
                "issues_count": len(inspection_results.get("issues_found", []))
            },
            "bim_inspection": inspection_results,
            "model_validation": validation_results,
            "electrical_analysis": analysis_results,
            "recommendations": [],
            "risk_assessment": self._assess_risk(inspection_results, validation_results, analysis_results)
        }
        
        # Generate recommendations based on findings
        recommendations = []
        
        if inspection_results.get("completeness_score", 100) < 80:
            recommendations.append("Model completeness is below acceptable threshold. Address missing information.")
        
        if validation_results.get("validation_score", 100) < 90:
            recommendations.append("Model validation revealed significant issues. Review and fix validation errors.")
        
        if analysis_results.get("critical_assets", []):
            recommendations.append(f"Found {len(analysis_results['critical_assets'])} critical assets requiring special attention.")
        
        if inspection_results.get("issues_found"):
            recommendations.append(f"Address {len(inspection_results['issues_found'])} identified issues before proceeding.")
        
        report["recommendations"] = recommendations
        
        self.logger.info("Comprehensive report generated successfully")
        
        return report
    
    def _assess_risk(self, inspection_results: Dict[str, Any], 
                     validation_results: Dict[str, Any], 
                     analysis_results: Dict[str, Any]) -> str:
        """
        Assess overall risk level based on all analysis results.
        
        Args:
            inspection_results: BIM inspection results
            validation_results: Model validation results
            analysis_results: Electrical analysis results
            
        Returns:
            str: Risk level (Low, Medium, High, Critical)
        """
        scores = []
        if 'completeness_score' in inspection_results:
            scores.append(inspection_results['completeness_score'])
        if 'validation_score' in validation_results:
            scores.append(validation_results['validation_score'])
        
        avg_score = sum(scores) / len(scores) if scores else 100
        
        critical_count = len(analysis_results.get('critical_assets', []))
        issue_count = len(inspection_results.get('issues_found', []))
        
        # Determine risk level
        if avg_score < 70 or critical_count > 5 or issue_count > 20:
            return "Critical"
        elif avg_score < 85 or critical_count > 2 or issue_count > 10:
            return "High"
        elif avg_score < 95 or critical_count > 0 or issue_count > 5:
            return "Medium"
        else:
            return "Low"


# Function to create the Revit Agent with proper dependencies
def create_revit_agent(sync_service: RevitSyncService = None, 
                      event_publisher: RevitEventPublisher = None) -> RevitAgent:
    """
    Factory function to create a RevitAgent with proper dependencies.
    
    Args:
        sync_service: Revit sync service instance
        event_publisher: Event publisher instance
        
    Returns:
        RevitAgent: Configured agent instance
    """
    if sync_service is None:
        # Create default services if not provided
        from revit_integration.aps.data_exchange import APSDataExchange
        from revit_integration.aps.auth_service import APSAuthService
        import os
        
        aps_auth_service = APSAuthService(
            client_id=os.getenv('APS_CLIENT_ID', 'dummy'),
            client_secret=os.getenv('APS_CLIENT_SECRET', 'dummy'),
            redirect_uri=os.getenv('APS_REDIRECT_URI', 'http://localhost:8000/callback')
        )
        aps_data_exchange = APSDataExchange(aps_auth_service)
        sync_service = RevitSyncService(aps_data_exchange)
    
    if event_publisher is None:
        event_publisher = RevitEventPublisher()
    
    return RevitAgent(sync_service, event_publisher)