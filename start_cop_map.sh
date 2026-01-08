#!/bin/bash

# ==============================================================================
# Orchestrates the local environment for the Map POI project.
#    Handles directory navigation, Docker daemon initialization,
#    PostgreSQL container startup, DB schema init, and the Node.js dev server.
# ==============================================================================

# Configuration
REPO_PATH="/Users/pablo/Desktop/Scripts/mapa-puntos-interes" # <-- Change this to your local cop-map repo path

# Cleanup function to run on Ctrl+C
cleanup() {
    echo -e "\n\n🛑 Stopping services..."
    docker compose down
    echo "✅ Cleaned up containers. Goodbye!"
    exit
}

# Register the trap to catch SIGINT (Ctrl+C)
trap cleanup SIGINT

# 1. Move to repository
if ! cd "$REPO_PATH" 2>/dev/null; then
    echo "❌ Error: Check where your actual cop-map project is."
    echo "Path attempted: $REPO_PATH"
    exit 1
fi

# 2. Check and Start Docker
if ! docker info >/dev/null 2>&1; then
    echo "🚀 Starting Docker Desktop..."
    open -a Docker

    echo -n "⏳ Initializing docker daemon..."
    # Wait until docker is ready
    while ! docker info >/dev/null 2>&1; do
        echo -n "."
        sleep 1
    done
    echo -e "\n✅ Docker is ready!"
fi

# 3. Start PostgreSQL
echo "📦 Starting PostgreSQL..."
docker compose up -d

# 4. Initialize database (conditional)
read -p "❓ Initialize database schema? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "⚙️  Running database initialization..."
    node scripts/init-db.js
fi

# 5. Start Map Server
#echo "🌐 Starting map server at http://localhost:3000"
#echo "💡 Press Ctrl+C to stop the server and shut down the database."
npm run dev
