"""Tail the AdGuard query log and POST new entries to the SafeFamily receiver."""

import json
import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import requests

# Set up 1MB per file, keep last 3 logs
log_handler = RotatingFileHandler(
    "/tmp/log_poster.log",
    maxBytes=1000000,
    backupCount=3,
)
logging.basicConfig(
    level=logging.INFO,
    handlers=[log_handler],
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def tail_log(file_path: str, url: str, checkpoint_file: str = "checkpoint.txt") -> None:
    """Follow the query log and POST each new JSON line to the receiver."""
    checkpoint_path = Path(checkpoint_file)
    try:
        last_position = int(checkpoint_path.read_text().strip())
    except (FileNotFoundError, ValueError):
        last_position = 0

    with Path(file_path).open() as f:
        f.seek(0, 2)  # Move to end of file
        file_size = f.tell()
        if last_position > file_size:
            last_position = 0  # Reset if file was truncated

        f.seek(last_position)

        while True:
            line = f.readline()
            if not line:
                time.sleep(1)  # Wait for new data
                continue

            try:
                log_entry = json.loads(line.strip())
                response = requests.post(url, json=log_entry, timeout=10)
                logger.info(
                    "Sent log: %s | Response: %s %s",
                    json.dumps(log_entry),
                    response.status_code,
                    response.text,
                )
            except json.JSONDecodeError:
                logger.exception("Skipping invalid JSON: %s", line)
            except requests.RequestException:
                logger.exception("Failed to send log")

            last_position = f.tell()
            checkpoint_path.write_text(str(last_position))


if __name__ == "__main__":
    LOG_FILE = "/tmp/adguardhome/data/querylog.json"  # Change this to your OpenWRT log file path
    SERVER_URL = "http://10.0.0.30:8080/logs"  # Change this to your receiving server
    tail_log(LOG_FILE, SERVER_URL)
