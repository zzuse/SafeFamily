# Installation Guide

This guide covers installing and deploying SafeFamily Project with Gunicorn and Nginx.

## Table of Contents

- [Prerequisites](#prerequisites)
- [System Requirements](#system-requirements)
- [Installation Steps](#installation-steps)
- [Gunicorn Configuration](#gunicorn-configuration)
- [Nginx Configuration](#nginx-configuration)
- [SSL/HTTPS Setup](#sslhttps-setup)
- [Systemd Service](#systemd-service)
- [Troubleshooting](#troubleshooting)

## Prerequisites

- Ubuntu 20.04+ / Debian 11+ (or similar Linux distribution)
- Python 3.9+
- Nginx
- PostgreSQL 13+
- Domain name (for SSL certificate)

## System Requirements

- **CPU**: 2+ cores
- **RAM**: 2GB minimum, 4GB recommended
- **Disk**: 20GB minimum
- **Network**: Public IP with ports 80 and 443 open

## Installation Steps

### 1. System Updates and Dependencies
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv nginx postgresql \
    build-essential libpq-dev git
```

### 2. Create Application User
```bash
sudo useradd -m -s /bin/bash safefamily
sudo su - safefamily
```

### 3. Clone Repository
```bash
git clone https://github.com/zzuse/SafeFamily.git
cd SafeFamily
```

### 4. Setup Python Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -e .
# or
pip install -r requirements.txt
```

### 5. Environment Configuration
```bash
cp .env.example .env
nano .env  # Edit with your configuration
```

Example `.env`:
```
FLASK_DEBUG=False
FLASK_SQLALCHEMY_DATABASE_URI=postgresql://user:password@localhost/safefamily
FLASK_APP_SECRET_KEY=your-secret-key-here
FLASK_JWT_SECRET_KEY=your_jwt_secret_key
```

### 6. Database Setup
```bash
# Create database
sudo -u postgres psql
CREATE DATABASE safefamily;
CREATE USER safefamily WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE safefamily TO safefamily;
\q

# Run migrations (if applicable)
python -m safe_family.cli.migrate
```

## Gunicorn Configuration

### 1. Install Gunicorn
```bash
pip install gunicorn
```

### 2. Test Gunicorn
```bash
# From project root
gunicorn --workers 4 --bind 127.0.0.1:8000 safe_family:app
```

## Nginx Configuration

### 1. Main Nginx Configuration

Create `/etc/nginx/sites-available/safefamily`:

### 2. Enable Nginx Site
```bash
# Copy config to Nginx
sudo cp deploy/nginx/sites-available/safefamily /etc/nginx/sites-available/

# Test configuration
sudo nginx -t

# Enable site
sudo ln -s /etc/nginx/sites-available/safefamily /etc/nginx/sites-enabled/

# Reload Nginx
sudo systemctl reload nginx
```

## SSL/HTTPS Setup

### Option 1: Let's Encrypt (Recommended)
```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Create webroot directory
sudo mkdir -p /var/www/certbot

# Obtain certificate
sudo certbot certonly --webroot \
    -w /var/www/certbot \
    -d yourdomain.com \
    -d www.yourdomain.com \
    --email your-email@example.com \
    --agree-tos \
    --no-eff-email

# Test automatic renewal
sudo certbot renew --dry-run

# Setup auto-renewal cron job
sudo crontab -e
# Add this line:
0 3 * * * certbot renew --post-hook "systemctl reload nginx"
```

### Option 2: Custom Certificate
```bash
# Copy your certificates
sudo mkdir -p /etc/ssl/safefamily
sudo cp your-cert.crt /etc/ssl/safefamily/
sudo cp your-key.key /etc/ssl/safefamily/
sudo chmod 600 /etc/ssl/safefamily/your-key.key

# Update Nginx config paths accordingly
```

## Systemd Service

### 1. Create Systemd Service File

Create `/etc/systemd/system/gunicorn-safefamily.service`:


### 2. Enable and Start Service
```bash
# Copy service file
sudo cp deploy/systemd/gunicorn.service /etc/systemd/system/gunicorn-safefamily.service

# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable gunicorn-safefamily

# Start service
sudo systemctl start gunicorn-safefamily

# Check status
sudo systemctl status gunicorn-safefamily

# View logs
sudo journalctl -u gunicorn-safefamily -f
```

## Deployment Scripts

### Automated Deployment Script

Make it executable:
```bash
chmod +x scripts/deploy.sh
```

## Troubleshooting

### Check Service Status
```bash
sudo systemctl status gunicorn-safefamily
sudo systemctl status nginx
```

### View Logs
```bash
# Gunicorn logs
sudo journalctl -u gunicorn-safefamily -n 100 --no-pager

# Nginx logs
sudo tail -f /var/log/nginx/safefamily_error.log
sudo tail -f /var/log/nginx/safefamily_access.log

# Application logs
tail -f /var/log/gunicorn/error.log
```

### Common Issues

**1. Permission Denied on Static Files**
```bash
sudo chown -R safefamily:www-data /home/safefamily/my_project/src/my_project/static
sudo chmod -R 755 /home/safefamily/my_project/src/my_project/static
```

**2. Gunicorn Won't Start**
```bash
# Check config syntax
gunicorn --check-config -c deploy/gunicorn/gunicorn_config.py my_project.wsgi:app

# Test manually
cd /home/safefamily/my_project
source venv/bin/activate
gunicorn my_project.wsgi:app
```

**3. Nginx 502 Bad Gateway**
- Verify Gunicorn is running: `sudo systemctl status gunicorn-safefamily`
- Check firewall rules: `sudo ufw status`
- Verify socket connection: `curl http://127.0.0.1:8000`

**4. SSL Certificate Issues**
```bash
# Check certificate expiry
sudo certbot certificates

# Renew manually
sudo certbot renew
sudo systemctl reload nginx
```

## Security Checklist

- [ ] Firewall configured (UFW/iptables)
- [ ] SSH key-only authentication
- [ ] Non-root user for application
- [ ] SSL/TLS certificates configured
- [ ] Security headers enabled in Nginx
- [ ] Rate limiting configured
- [ ] Database credentials secured
- [ ] SECRET_KEY is random and secure
- [ ] DEBUG=False in production
- [ ] Regular security updates scheduled

## Monitoring

Consider setting up:
- Log aggregation (ELK Stack, Graylog)
- Application monitoring (Sentry, New Relic)
- Server monitoring (Prometheus, Grafana)
- Uptime monitoring (UptimeRobot, Pingdom)

## Support

For issues, please:
1. Check logs (see Troubleshooting section)
2. Review GitHub Issues: https://github.com/zzuse/SafeFamily/issues
3. Contact: zzuseme@gmail.com