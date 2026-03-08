"""
LiveCold Dashboard Package
Authentication and dashboard components for LiveCold platform
"""

from .models import init_db
from .auth import initialize_super_admin

__all__ = ["init_db", "initialize_super_admin"]
