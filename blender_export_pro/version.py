"""Single source of truth for the plugin version.

Kept separate so blender_codegen can stamp exported scripts without
importing the package __init__ (avoids circular imports).
"""

__version__ = "0.1.0"
