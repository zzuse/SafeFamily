#!/bin/ash

# Configuration
LOG_FILE="/etc/AdGuardHome/data/querylog.json"  # Change this to your OpenWRT log file path
SERVER_URL="http://10.0.0.30:8080/logs"        # Change this to your receiving server
CHECKPOINT_FILE="checkpoint.txt"
LOG_POSTER="/tmp/log_poster.log"
MAX_LOG_SIZE=1000000  # 1MB

# Function to rotate log if needed
rotate_log() {
    if [ -f "$LOG_POSTER" ] && [ $(wc -c < "$LOG_POSTER") -gt $MAX_LOG_SIZE ]; then
        [ -f "${LOG_POSTER}.3" ] && rm "${LOG_POSTER}.3"
        [ -f "${LOG_POSTER}.2" ] && mv "${LOG_POSTER}.2" "${LOG_POSTER}.3"
        [ -f "${LOG_POSTER}.1" ] && mv "${LOG_POSTER}.1" "${LOG_POSTER}.2"
        mv "$LOG_POSTER" "${LOG_POSTER}.1"
    fi
}

# Function to log message
log_message() {
    level="$1"
    message="$2"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $level - $message" >> "$LOG_POSTER"
    rotate_log
}

# Read last line number from checkpoint
line_num=$(cat "$CHECKPOINT_FILE" 2>/dev/null || echo 0)

# Process existing lines
if [ -f "$LOG_FILE" ]; then
    tail -n +$((line_num + 1)) "$LOG_FILE" | while read -r line; do
        if [ -n "$line" ]; then
            # Send POST request
            response=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d "$line" "$SERVER_URL")
            if [ "$response" -eq 200 ]; then
                log_message "INFO" "Sent log: $line | Response: $response"
            else
                log_message "ERROR" "Failed to send log: $line | Response: $response"
            fi
            line_num=$((line_num + 1))
            echo $line_num > "$CHECKPOINT_FILE"
        fi
    done
fi

# Now tail the file for new lines
tail -f "$LOG_FILE" | while read -r line; do
    if [ -n "$line" ]; then
        # Send POST request
        response=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d "$line" "$SERVER_URL")
        if [ "$response" -eq 200 ]; then
            log_message "INFO" "Sent log: $line | Response: $response"
        else
            log_message "ERROR" "Failed to send log: $line | Response: $response"
        fi
        line_num=$((line_num + 1))
        echo $line_num > "$CHECKPOINT_FILE"
    fi
done