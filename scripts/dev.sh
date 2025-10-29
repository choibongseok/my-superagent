#!/bin/bash

# AgentHQ Development Environment Startup Script
# One-click startup for local development with Docker Compose

set -e

# Move to project root
cd "$(dirname "$0")/.."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}  AgentHQ Development Setup${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# Check if .env exists
if [ ! -f "backend/.env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found. Creating from .env.example...${NC}"
    cp backend/.env.example backend/.env
    echo -e "${GREEN}✅ Created backend/.env${NC}"
    echo -e "${YELLOW}📝 Please edit backend/.env and add your API keys:${NC}"
    echo "   - OPENAI_API_KEY"
    echo "   - GOOGLE_CLIENT_ID"
    echo "   - GOOGLE_CLIENT_SECRET"
    echo ""
    read -p "Press Enter to continue after editing .env, or Ctrl+C to cancel..."
fi

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed. Please install Docker Desktop.${NC}"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo -e "${RED}❌ Docker daemon is not running. Please start Docker Desktop.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker is running${NC}"

# Check Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed.${NC}"
    exit 1
fi

# Use docker compose or docker-compose
COMPOSE_CMD="docker compose"
if ! docker compose version &> /dev/null; then
    COMPOSE_CMD="docker-compose"
fi

echo -e "${GREEN}✅ Docker Compose is available${NC}"
echo ""

# Stop any running containers
echo -e "${YELLOW}🛑 Stopping existing containers...${NC}"
$COMPOSE_CMD down 2>/dev/null || true

# Build and start services
echo ""
echo -e "${BLUE}🔨 Building Docker images...${NC}"
$COMPOSE_CMD build

echo ""
echo -e "${BLUE}🚀 Starting services...${NC}"
$COMPOSE_CMD up -d

# Wait for services to be healthy
echo ""
echo -e "${YELLOW}⏳ Waiting for services to be healthy...${NC}"

# Wait for PostgreSQL
echo -n "   PostgreSQL: "
for i in {1..30}; do
    if docker exec agenthq-postgres pg_isready -U agenthq &> /dev/null; then
        echo -e "${GREEN}✅${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ Failed${NC}"
        exit 1
    fi
    sleep 1
done

# Wait for Redis
echo -n "   Redis: "
for i in {1..30}; do
    if docker exec agenthq-redis redis-cli ping &> /dev/null; then
        echo -e "${GREEN}✅${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ Failed${NC}"
        exit 1
    fi
    sleep 1
done

# Run database migrations
echo ""
echo -e "${BLUE}📊 Running database migrations...${NC}"
docker exec agenthq-backend alembic upgrade head

# Wait for backend to be ready
echo ""
echo -n "   Backend API: "
for i in {1..60}; do
    if curl -s http://localhost:8000/health &> /dev/null; then
        echo -e "${GREEN}✅${NC}"
        break
    fi
    if [ $i -eq 60 ]; then
        echo -e "${RED}❌ Failed to start${NC}"
        echo -e "${YELLOW}Check logs with: docker logs agenthq-backend${NC}"
        exit 1
    fi
    sleep 1
done

# Check Celery worker
echo -n "   Celery Worker: "
sleep 3
if docker exec agenthq-celery-worker celery -A app.agents.celery_app inspect ping &> /dev/null; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${YELLOW}⚠️  Warning: Celery worker may not be ready${NC}"
fi

# Success message
echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}  ✅ AgentHQ is running!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo -e "${BLUE}📡 Services:${NC}"
echo "   Backend API:       http://localhost:8000"
echo "   API Docs:          http://localhost:8000/docs"
echo "   Celery Flower:     http://localhost:5555"
echo "   PostgreSQL:        localhost:5432"
echo "   Redis:             localhost:6379"
echo ""
echo -e "${BLUE}🔧 Useful commands:${NC}"
echo "   View logs:         docker-compose logs -f"
echo "   Stop services:     ./stop.sh"
echo "   Backend logs:      docker logs -f agenthq-backend"
echo "   Worker logs:       docker logs -f agenthq-celery-worker"
echo "   Database shell:    docker exec -it agenthq-postgres psql -U agenthq"
echo "   Redis CLI:         docker exec -it agenthq-redis redis-cli"
echo ""
echo -e "${YELLOW}💡 Tips:${NC}"
echo "   - API docs available at http://localhost:8000/docs"
echo "   - Monitor Celery tasks at http://localhost:5555"
echo "   - Hot reload is enabled for backend code changes"
echo ""
