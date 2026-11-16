# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    git \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Firefox (and its system libraries) for Playwright gas price snapshots.
# Firefox, not Chromium: cbc.ca's CDN blocks headless Chromium (ERR_HTTP2_PROTOCOL_ERROR).
# A shared path (not /root/.cache) so the unprivileged app user can launch it.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install --with-deps firefox && chmod -R a+rX /ms-playwright

# The app runs as an unprivileged user, not root: a bug that lets someone run
# code in the container then can't read root-only files, install packages or
# change the image. Its uid/gid should match the host user that owns the
# mounted folders (./logs, the AdGuard rules repo, the SSH key folder), so set
# APP_UID / APP_GID in .env to `id -u` / `id -g` if they aren't 1000.
ARG APP_UID=1000
ARG APP_GID=1000
# safe.directory: the rules repo is bind-mounted from the host, so tell git it
# is expected at that path.
RUN groupadd --non-unique --gid ${APP_GID} app \
    && useradd --non-unique --create-home --uid ${APP_UID} --gid ${APP_GID} app \
    && git config --system --add safe.directory /app/adguard_rules

# Copy the project files
COPY --chown=app:app . .

# Create logs directory
RUN mkdir -p logs && chown app:app /app /app/logs

USER app
ENV HOME=/home/app

# Expose the port the app runs on
EXPOSE 8000

# Use environment variables to configure Gunicorn
ENV GUNICORN_WORKERS=4
ENV GUNICORN_BIND=0.0.0.0:8000

# Run the application
CMD gunicorn --workers=${GUNICORN_WORKERS} --forwarded-allow-ips="*" --bind=${GUNICORN_BIND} run:flask_app
