# Vught Pace Keeper - Development Commands
# Usage: just <command>

# Default: list available commands
default:
    @just --list

# --- Database ---

# Start PostgreSQL/PostGIS in Docker
db:
    docker-compose up -d db

# Stop the database
db-stop:
    docker-compose stop db

# Connect to PostgreSQL shell
db-shell:
    docker-compose exec db psql -U vught_user -d vught_pace_keeper

# Reset database (destructive!)
db-reset:
    docker-compose down -v
    docker-compose up -d db
    @echo "Waiting for database to be ready..."
    @sleep 3
    just migrate
    just fixtures

# --- Django ---

# Run development server
run:
    uv run python manage.py runserver

# Run development server on all interfaces
run-public:
    uv run python manage.py runserver 0.0.0.0:8000

# Make migrations
makemigrations *ARGS:
    uv run python manage.py makemigrations {{ ARGS }}

# Apply migrations
migrate:
    uv run python manage.py migrate

# Create superuser
superuser:
    uv run python manage.py createsuperuser

# Load sample fixture data
fixtures:
    uv run python manage.py loaddata sample_data

# Django shell
shell:
    uv run python manage.py shell

# Django shell plus (if installed)
shell-plus:
    uv run python manage.py shell_plus

# Collect static files
collectstatic:
    uv run python manage.py collectstatic --noinput

# --- Testing ---

# Run tests
test *ARGS:
    uv run pytest {{ ARGS }}

# Run tests with coverage
test-cov:
    uv run pytest --cov=vught_pace_keeper --cov-report=term-missing

# --- Utilities ---

# Install/sync dependencies
install:
    uv sync

# Generate a new Django secret key
secret-key:
    uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# Generate a new Fernet key for token encryption
fernet-key:
    uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Check for missing migrations
check-migrations:
    uv run python manage.py makemigrations --check --dry-run

# Run linting
lint:
    uv run ruff check .

# Run linting with auto-fix
lint-fix:
    uv run ruff check . --fix

# Format code
fmt:
    uv run ruff format .

# --- Tailwind CSS ---

# Download Tailwind standalone CLI (run once)
tw-install:
    curl -sLO https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64
    chmod +x tailwindcss-linux-x64
    mv tailwindcss-linux-x64 tailwindcss

# Build Tailwind CSS once
tw-build:
    ./tailwindcss -i src/vught_pace_keeper/static/css/input.css -o src/vught_pace_keeper/static/css/output.css --minify

# Watch Tailwind CSS for changes
tw-watch:
    ./tailwindcss -i src/vught_pace_keeper/static/css/input.css -o src/vught_pace_keeper/static/css/output.css --watch

# --- WSL Setup ---

# Install system dependencies for GeoDjango (run once)
setup-wsl:
    sudo apt update
    sudo apt install -y gdal-bin libgdal-dev libgeos-dev libproj-dev

# --- Full workflows ---

# Fresh start: db + migrate + fixtures + run
fresh: db migrate fixtures run

# Quick start: just db and run (assumes migrations are applied)
start: db run
