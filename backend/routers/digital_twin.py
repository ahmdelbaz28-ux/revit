import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.rbac import Permission
from backend.auth import require_permission
from backend.services.digital_twin_service import DigitalTwinService, ConversionConfig, ConversionResult, ConversionConfigManager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["digital-twin"])

# Initialize service and config manager
service = DigitalTwinService()
config_manager = ConversionConfigManager()

# Pydantic models
class ConvertRequest(BaseModel):
    """Request model for conversion operation."""
    source_filepath: str
    target_filepath: str
    conversion_type: str  # "autocad_to_revit" or "revit_to_autocad"
    template_path: Optional[str] = None

class ConvertResponse(BaseModel):
    """Response model for conversion operation."""
    success: bool
    source_file: str
    target_file: str
    elements_converted: int
    errors: List[str] = []
    warnings: List[str] = []

class OperationResponse(BaseModel):
    """Generic operation response."""
    success: bool
    message: str
    handle: Optional[str] = None

class HistoryResponse(BaseModel):
    """Response model for conversion history."""
    history: List[Dict[str, Any]]

class ConfigureRequest(BaseModel):
    """Request model for configuration update."""
    config: Dict[str, Any]

class ConfigureResponse(BaseModel):
    """Response model for configuration update."""
    success: bool
    message: str

class RollbackRequest(BaseModel):
    """Request model for rollback operation."""
    target_file: str

class MappingsResponse(BaseModel):
    """Response model for available mappings."""
    layer_to_category: Dict[str, str]
    category_to_layer: Dict[str, str]
    linetype_to_element: Dict[str, str]
    block_to_family: Dict[str, str]
    units: Dict[str, Any]
    levels: Dict[str, Any]


# Add new endpoints
@router.post("/convert", response_model=ConvertResponse, tags=["digital-twin"])
async def convert_files(request: ConvertRequest) -> ConvertResponse:
    """
    Perform bidirectional CAD/BIM conversion.
    
    Args:
        request: Conversion parameters
        
    Returns:
        Conversion result
    """
    try:
        if request.conversion_type == "autocad_to_revit":
            result = service.convert_autocad_to_revit(
                request.source_filepath, 
                request.target_filepath, 
                request.template_path
            )
        elif request.conversion_type == "revit_to_autocad":
            result = service.convert_revit_to_autocad(
                request.source_filepath, 
                request.target_filepath
            )
        else:
            raise HTTPException(status_code=400, detail=f"Invalid conversion type: {request.conversion_type}")
        
        return ConvertResponse(
            success=result.success,
            source_file=result.source_file,
            target_file=result.target_file,
            elements_converted=result.elements_converted,
            duration_seconds=result.duration_seconds,
            errors=result.errors,
            warnings=result.warnings
        )
    except Exception as e:
        logger.error(f"Error during conversion: {e}")
        raise HTTPException(status_code=500, detail=f"Error during conversion: {str(e)}")

@router.get("/history", response_model=HistoryResponse, tags=["digital-twin"])
async def get_conversion_history() -> HistoryResponse:
    """
    Get conversion history.
    
    Returns:
        List of conversion history entries
    """
    try:
        history = service.get_conversion_history()
        return HistoryResponse(history=history)
    except Exception as e:
        logger.error(f"Error getting conversion history: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting conversion history: {str(e)}")


# Add new endpoints
@router.post("/configure", response_model=ConfigureResponse, tags=["digital-twin"])
async def configure_conversion(request: ConfigureRequest) -> ConfigureResponse:
    """
    Update conversion configuration.
    
    Args:
        request: New configuration parameters
        
    Returns:
        Configuration update status
    """
    try:
        config = ConversionConfig.from_dict(request.config)
        success = config_manager.save_config(config)
        
        if success:
            return ConfigureResponse(
                success=True,
                message="Configuration updated successfully"
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to save configuration")
    except Exception as e:
        logger.error(f"Error updating configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating configuration: {str(e)}")

@router.post("/rollback/{version_id}", tags=["digital-twin"])
async def rollback_version(version_id: str, request: RollbackRequest) -> Dict[str, Any]:
    """
    Rollback to a specific version.
    
    Args:
        version_id: Version ID to rollback to
        request: Target file path for rollback
        
    Returns:
        Rollback status
    """
    try:
        success = service.rollback_to_version(version_id, request.target_file)
        if success:
            return {
                "success": True,
                "message": f"Successfully rolled back to version {version_id}",
                "version_id": version_id
            }
        else:
            raise HTTPException(status_code=404, detail=f"Version {version_id} not found or rollback failed")
    except Exception as e:
        logger.error(f"Error during rollback: {e}")
        raise HTTPException(status_code=500, detail=f"Error during rollback: {str(e)}")


# Add new endpoints
@router.get("/mappings", response_model=MappingsResponse, tags=["digital-twin"])
async def get_available_mappings() -> MappingsResponse:
    """
    Get available mapping configurations.
    
    Returns:
        Available mapping configurations
    """
    try:
        mappings = config_manager.get_available_mappings()
        return MappingsResponse(
            layer_to_category=mappings["layer_to_category"],
            category_to_layer=mappings["category_to_layer"],
            linetype_to_element=mappings["linetype_to_element"],
            block_to_family=mappings["block_to_family"],
            units=mappings["units"],
            levels=mappings["levels"]
        )
    except Exception as e:
        logger.error(f"Error getting mappings: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting mappings: {str(e)}")

@router.get("/status", tags=["digital-twin"])
async def get_digital_twin_status() -> Dict[str, Any]:
    """
    Get Digital Twin service status.
    
    Returns:
        Service status information
    """
    try:
        history = service.get_conversion_history()
        return {
            "status": "ready",
            "total_conversions": len(history),
            "last_conversion": history[-1] if history else None,
            "config_loaded": True,
            "timestamp": __import__('datetime').datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting Digital Twin status: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting Digital Twin status: {str(e)}")

@router.post("/update_mapping", tags=["digital-twin"])
async def update_single_mapping(
    layer: str, 
    category: str, 
    direction: str = "autocad_to_revit"
) -> Dict[str, Any]:
    """
    Update a single mapping rule.
    
    Args:
        layer: Source layer/category name
        category: Target category/layer name
        direction: Direction of mapping ("autocad_to_revit" or "revit_to_autocad")
        
    Returns:
        Update status
    """
    try:
        success = config_manager.update_mapping(layer, category, direction)
        if success:
            return {
                "success": True,
                "message": f"Mapping updated: {layer} -> {category} ({direction})",
                "mapping": {layer: category}
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update mapping")
    except Exception as e:
        logger.error(f"Error updating mapping: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating mapping: {str(e)}")

@router.get("/config", tags=["digital-twin"])
async def get_current_config() -> Dict[str, Any]:
    """
    Get current conversion configuration.
    
    Returns:
        Current configuration
    """
    try:
        config = config_manager.load_config()
        return {
            "config": config.to_dict(),
            "loaded_from": str(config_manager.config_file) if config_manager.config_file.exists() else "default"
        }
    except Exception as e:
        logger.error(f"Error getting configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting configuration: {str(e)}")


@router.post(
    "/rollback/{version_id}",
    response_model=OperationResponse,
    dependencies=[Depends(require_permission(Permission.SYSTEM_CONFIG))],
)
async def rollback_to_version(version_id: str):
    """
    Rollback to a specific conversion version.
    
    Args:
        version_id: Version ID to rollback to
    
    Returns:
        OperationResponse with success status
    """
    try:
        service = get_digital_twin_service()
        success = service.rollback_to_version(version_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {version_id} not found",
            )
        
        return OperationResponse(
            success=True,
            message=f"Successfully rolled back to version {version_id}",
        )
    except Exception as e:
        logger.error(f"Failed to rollback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rollback failed: {str(e)}",
        )


@router.get(
    "/config",
    response_model=ConversionConfig,
    dependencies=[Depends(require_permission(Permission.EXPORT_READ))],
)
async def get_config():
    """
    Get conversion configuration.
    
    Returns:
        ConversionConfig with current settings
    """
    try:
        config = _config_manager.load()
        return config
    except Exception as e:
        logger.error(f"Failed to get config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get config: {str(e)}",
        )


@router.put(
    "/config",
    response_model=OperationResponse,
    dependencies=[Depends(require_permission(Permission.SYSTEM_CONFIG))],
)
async def update_config(config: ConversionConfig):
    """
    Update conversion configuration.
    
    Args:
        config: ConversionConfig with new settings
    
    Returns:
        OperationResponse with success status
    """
    try:
        _config_manager.save(config)
        
        return OperationResponse(
            success=True,
            message="Configuration updated successfully",
        )
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Update failed: {str(e)}",
        )


@router.get(
    "/download/{filename:path}",
    dependencies=[Depends(require_permission(Permission.EXPORT_READ))],
)
async def download_file(filename: str):
    """
    Download a converted file.
    
    Args:
        filename: Path to file
    
    Returns:
        FileResponse with file content
    """
    try:
        # Restrict downloads to uploads directory only
        resolved_path = _safe_resolve_upload_path(filename)

        if not os.path.exists(resolved_path) or not os.path.isfile(resolved_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )

        return FileResponse(
            path=resolved_path,
            filename=os.path.basename(resolved_path),
            media_type="application/octet-stream",
        )
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Download failed: {str(e)}",
        )
