#!/bin/bash
set -e

echo "CartPilot API - Docker Entrypoint"

# Wait for database to be ready (additional check beyond healthcheck)
echo "Waiting for database connection..."
max_retries=30
retry_count=0

while [ $retry_count -lt $max_retries ]; do
    if python -c "
import asyncio
import asyncpg
import os

async def check():
    url = os.environ.get('DATABASE_URL', '')
    # Convert asyncpg URL format
    url = url.replace('postgresql+asyncpg://', 'postgresql://')
    try:
        conn = await asyncpg.connect(url)
        await conn.close()
        return True
    except Exception as e:
        return False

exit(0 if asyncio.run(check()) else 1)
" 2>/dev/null; then
        echo "Database connection successful!"
        break
    fi
    
    retry_count=$((retry_count + 1))
    echo "Database not ready yet, retrying... ($retry_count/$max_retries)"
    sleep 1
done

if [ $retry_count -eq $max_retries ]; then
    echo "ERROR: Could not connect to database after $max_retries attempts"
    exit 1
fi

# Run database migrations
echo "Running database migrations..."
alembic upgrade head

echo "Migrations complete!"

# Seed catalog if SEED_CATALOG is set
if [ "${SEED_CATALOG:-false}" = "true" ]; then
    echo "Seeding product catalog..."
    python -m scripts.seed_catalog
    echo "Catalog seeding complete!"
fi

# Start the application
echo "Starting CartPilot API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
