from datetime import datetime
import logging

def current_time() -> str:
    """Return the current local date and time"""
    logging.info("execute current_time tool")
    return datetime.now().isoformat()