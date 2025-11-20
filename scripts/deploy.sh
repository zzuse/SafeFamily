#!/bin/bash
# scripts/deploy.sh

set -e

echo "Starting deployment..."

# Pull latest code
cd /home/myproject/my_project
git pull origin main

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations (if applicable)
python -m my_project.cli.migrate

# Collect static files (if Django)
# python manage.py collectstatic --noinput

# Restart services
sudo systemctl restart gunicorn-myproject
sudo systemctl reload nginx

echo "Deployment completed successfully!"