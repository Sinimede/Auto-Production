
import os
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Callable
import logging

@dataclass
class LogEntry:
    message: str
    level: str = "INFO"  # INFO, WARNING, ERROR, SUCCESS
    tag: Optional[str] = None
    timestamp: str = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%H:%M:%S")

class LogManager:
    def __init__(self, log_file: Optional[str] = "auto_production.log"):
        self.entries: List[LogEntry] = []
        self._listeners: List[Callable[[LogEntry], None]] = []
        
        # Persistent logging
        self.logger = logging.getLogger("AutoProduction")
        self.logger.setLevel(logging.DEBUG)
        
        # Prevent duplicate handlers
        if not self.logger.handlers:
            # File handler
            if log_file:
                fh = logging.FileHandler(log_file, encoding='utf-8')
                fh.setLevel(logging.DEBUG)
                formatter = logging.Formatter('%(asctime)s [%(levelname)s] [%(name)s] %(message)s')
                fh.setFormatter(formatter)
                self.logger.addHandler(fh)

    def add_entry(self, message: str, level: str = "INFO", tag: Optional[str] = None):
        entry = LogEntry(message=message, level=level, tag=tag)
        self.entries.append(entry)
        
        # Map levels to standard logging
        log_level = logging.INFO
        if level == "ERROR": log_level = logging.ERROR
        elif level == "WARNING": log_level = logging.WARNING
        elif level == "SUCCESS": log_level = logging.INFO
        
        msg_with_tag = f"[{tag}] {message}" if tag else message
        self.logger.log(log_level, msg_with_tag)
        
        for listener in self._listeners:
            listener(entry)
        return entry

    def subscribe(self, callback: Callable[[LogEntry], None]):
        self._listeners.append(callback)

    def get_filtered(self, tag: Optional[str] = None, level: Optional[str] = None):
        return [
            e for e in self.entries 
            if (not tag or e.tag == tag) and (not level or e.level == level)
        ]

    def clear(self):
        self.entries = []
