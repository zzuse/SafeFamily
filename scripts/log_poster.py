import json
import logging
import time
from logging.handlers import RotatingFileHandler

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


def tail_log(file_path, url, checkpoint_file="checkpoint.txt"):
    try:
        with open(checkpoint_file) as f:
            f.seek(0)
            last_position = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        last_position = 0

    with open(file_path) as f:
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
                response = requests.post(url, json=log_entry)
                logging.info(
                    f"Sent log: {json.dumps(log_entry)} | Response: {response.status_code} {response.text}",
                )
            except json.JSONDecodeError:
                logging.exception(f"Skipping invalid JSON: {line}")
            except requests.RequestException as e:
                logging.exception(f"Failed to send log: {e}")

            last_position = f.tell()
            with open(checkpoint_file, "w") as f_cp:
                f_cp.write(str(last_position))


if __name__ == "__main__":
    LOG_FILE = "/tmp/adguardhome/data/querylog.json"  # Change this to your OpenWRT log file path
    SERVER_URL = "http://10.0.0.30:8080/logs"  # Change this to your receiving server
    tail_log(LOG_FILE, SERVER_URL)
