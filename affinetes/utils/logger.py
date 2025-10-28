"""Centralized logging for affinetes"""

import logging
from typing import Optional


class Logger:
    """Centralized logging with structured format"""
    
    _instance: Optional['Logger'] = None
    
    def __init__(self, level: str = "INFO"):
        self.logger = logging.getLogger("affinetes")
        self.logger.setLevel(getattr(logging, level.upper()))
        
        # Avoid adding multiple handlers
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    @classmethod
    def get(cls, level: str = "INFO") -> logging.Logger:
        """Get or create logger instance"""
        if cls._instance is None:
            cls._instance = Logger(level)
        return cls._instance.logger
    
    @classmethod
    def set_level(cls, level: str):
        """Change log level"""
        logger = cls.get()
        logger.setLevel(getattr(logging, level.upper()))


# Global logger instance
logger = Logger.get()