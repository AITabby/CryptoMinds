"""CryptoMinds centralized logging configuration."""
import json
import logging
import os
import sys
import uuid
from datetime import datetime


def generate_request_id():
    """Generate a unique request ID for correlation across Python/Express boundary."""
    return str(uuid.uuid4())[:16]


class JsonFormatter(logging.Formatter):
    """Structured JSON log formatter for production."""

    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        # Include request_id if set on the record
        request_id = getattr(record, "request_id", None)
        if request_id:
            log_entry["request_id"] = request_id
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


TEXT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging(level=None, json_mode=None):
    """Configure the root logger once. Call from entry points before other modules."""
    if level is None:
        level = os.getenv("CRYPTOMINDS_LOG_LEVEL", "INFO").upper()
    if json_mode is None:
        json_mode = os.getenv("CRYPTOMINDS_LOG_JSON", "false").lower() == "true"

    log_level = getattr(logging, level, logging.INFO)
    formatter = JsonFormatter() if json_mode else logging.Formatter(TEXT_FORMAT)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    return root