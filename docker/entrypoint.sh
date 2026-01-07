#!/bin/bash
set -e

echo "==> Starting Vught Pace Keeper..."

# Run database migrations
echo "==> Running database migrations..."
python manage.py migrate --noinput

echo "==> Migrations complete."

# Execute the main command (passed as arguments)
exec "$@"
