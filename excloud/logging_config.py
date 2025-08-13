"""
Logging configuration for the Excloud SDK.
"""

import logging
import os


def setup_logger():
    """Setup the Excloud logger with appropriate level based on environment."""
    logger = logging.getLogger("orca")
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    handler = logging.StreamHandler()
    
    # Set log level based on environment variable
    if os.getenv("EXCLOUD_DEBUG") == "1":
        logger.setLevel(logging.DEBUG)
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter("🔧 DEBUG: %(message)s")
    else:
        logger.setLevel(logging.WARNING)  # Only show warnings and errors by default
        handler.setLevel(logging.WARNING)
        formatter = logging.Formatter("%(message)s")
    
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False  # Don't propagate to root logger
    
    return logger
