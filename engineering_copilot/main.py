"""
ETAP-AI-WORK Engineering Copilot - Main Entry Point
================================================

Principal Software Architect: Eng. Ahmed Elbaz
"""
from fastapi import FastAPI
from engineering_copilot.mcp_server.mcp_server import get_mcp_app
from engineering_copilot import __version__, __author__

def create_app() -> FastAPI:
    """
    Create and configure the Engineering Copilot application.
    
    Returns:
        FastAPI: Configured application instance
    """
    # Use the MCP server app as the main app
    app = get_mcp_app()
    
    # Add additional routes specific to the Engineering Copilot
    @app.get("/engineering-copilot/info")
    async def get_info():
        """Get information about the Engineering Copilot."""
        return {
            "name": "ETAP-AI-WORK Engineering Copilot",
            "version": __version__,
            "author": __author__,
            "description": "AI-driven engineering platform for ETAP, AutoCAD, and Revit integration",
            "capabilities": [
                "Natural Language Processing",
                "CAD Drawing Generation",
                "BIM Model Creation",
                "ETAP Model Synchronization",
                "Engineering Validation",
                "Report Generation",
                "Multi-Platform Translation"
            ]
        }
    
    return app


# For direct execution
if __name__ == "__main__":
    import uvicorn
    app = create_app()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        reload=True
    )