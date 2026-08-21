"""
Routes package.
"""
from .shipments import router as shipments_router
from .activities import router as activities_router
from .dashboard import router as dashboard_router
from .pages import router as pages_router

__all__ = ["shipments_router", "activities_router", "dashboard_router", "pages_router"]
