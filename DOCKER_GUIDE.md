# Docker Setup Guide

## Overview
This project has separate Docker configurations for development and production environments.

## Files
- `Dockerfile` - Production Dockerfile (optimized, multi-stage build)
- `Dockerfile.dev` - Development Dockerfile (includes dev tools)
- `docker-compose.dev.yml` - Development configuration
- `docker-compose.prod.yml` - Production configuration
- `entrypoint.sh` - Production entrypoint (runs migrations, collectstatic, starts Gunicorn)
- `entrypoint-dev.sh` - Development entrypoint (runs migrations, collectstatic, starts Django dev server)

## Development Environment

### Features
✅ Hot reloading - Code changes reflect immediately  
✅ Volume mounting - Edit files on your host machine  
✅ Django development server - Better debugging  
✅ Debug mode enabled  
✅ Auto migrations on startup  
✅ Exposed ports for direct access  

### Commands

```bash
# Start development environment
docker-compose -f docker-compose.dev.yml up

# Build and start
docker-compose -f docker-compose.dev.yml up --build

# Run in detached mode
docker-compose -f docker-compose.dev.yml up -d

# View logs
docker-compose -f docker-compose.dev.yml logs -f web

# Stop containers
docker-compose -f docker-compose.dev.yml down

# Clean rebuild
docker-compose -f docker-compose.dev.yml down
docker-compose -f docker-compose.dev.yml up --build
```

### Development Workflow
1. Start containers: `docker-compose -f docker-compose.dev.yml up`
2. Make code changes on your host machine
3. Changes automatically reflect in the container (hot reload)
4. Django dev server automatically restarts
5. No need to rebuild containers for code changes

### Running Management Commands
```bash
# Run migrations
docker-compose -f docker-compose.dev.yml exec web python manage.py migrate

# Create superuser
docker-compose -f docker-compose.dev.yml exec web python manage.py createsuperuser

# Collect static files
docker-compose -f docker-compose.dev.yml exec web python manage.py collectstatic

# Shell
docker-compose -f docker-compose.dev.yml exec web python manage.py shell

# Make migrations
docker-compose -f docker-compose.dev.yml exec web python manage.py makemigrations
```

## Production Environment

### Features
✅ Optimized multi-stage build  
✅ Minimal image size  
✅ Non-root user for security  
✅ Gunicorn WSGI server  
✅ Auto-restart policies  
✅ No volume mounts (code baked into image)  

### Commands

```bash
# Start production environment
docker-compose -f docker-compose.prod.yml up

# Build and start
docker-compose -f docker-compose.prod.yml up --build

# Run in detached mode
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.prod.yml logs -f web

# Stop containers
docker-compose -f docker-compose.prod.yml down
```

## Quick Reference

| Task | Development | Production |
|------|-------------|------------|
| Start | `docker-compose -f docker-compose.dev.yml up` | `docker-compose -f docker-compose.prod.yml up` |
| Build | `docker-compose -f docker-compose.dev.yml up --build` | `docker-compose -f docker-compose.prod.yml up --build` |
| Stop | `docker-compose -f docker-compose.dev.yml down` | `docker-compose -f docker-compose.prod.yml down` |
| Logs | `docker-compose -f docker-compose.dev.yml logs -f` | `docker-compose -f docker-compose.prod.yml logs -f` |
| Shell | `docker-compose -f docker-compose.dev.yml exec web bash` | `docker-compose -f docker-compose.prod.yml exec web bash` |

## Bash Aliases (Optional)

Add these to your `~/.bashrc` or `~/.bash_aliases` for convenience:

```bash
# Development
alias dcdev='docker-compose -f docker-compose.dev.yml'
alias dcdev-up='docker-compose -f docker-compose.dev.yml up'
alias dcdev-down='docker-compose -f docker-compose.dev.yml down'
alias dcdev-build='docker-compose -f docker-compose.dev.yml up --build'
alias dcdev-logs='docker-compose -f docker-compose.dev.yml logs -f'

# Production
alias dcprod='docker-compose -f docker-compose.prod.yml'
alias dcprod-up='docker-compose -f docker-compose.prod.yml up'
alias dcprod-down='docker-compose -f docker-compose.prod.yml down'
alias dcprod-build='docker-compose -f docker-compose.prod.yml up --build'

# Then you can use:
# dcdev-up          # Start development
# dcdev-build       # Build and start development
# dcdev-logs        # View development logs
# dcprod-up -d      # Start production in detached mode
```

## Troubleshooting

### Code changes not reflecting
```bash
# Restart the web service
docker-compose -f docker-compose.dev.yml restart web

# Or rebuild if needed
docker-compose -f docker-compose.dev.yml down
docker-compose -f docker-compose.dev.yml up --build
```

### Container config errors
```bash
# Clean up everything
docker-compose -f docker-compose.dev.yml down
docker system prune -f
docker-compose -f docker-compose.dev.yml up --build
```

### Permission issues
If you encounter permission errors, you may need to fix ownership:
```bash
sudo chown -R $USER:$USER .
```

## Volume Mounting

### Development Volumes
- `.:/app` - Your entire project code (for hot reloading)
- `/app/static_cdn` - Excluded (generated inside container)

### Why exclude static_cdn?
Static files are collected inside the container to avoid permission issues and ensure consistency.
