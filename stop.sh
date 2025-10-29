#!/bin/bash

# AgentHQ Development Environment Shutdown Script
# One-click shutdown for local development

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}  AgentHQ Shutdown${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# Use docker compose or docker-compose
COMPOSE_CMD="docker compose"
if ! docker compose version &> /dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
fi

# Check if services are running
if ! $COMPOSE_CMD ps | grep -q "agenthq"; then
    echo -e "${YELLOW}⚠️  No AgentHQ services are running${NC}"
    exit 0
fi

# Stop services
echo -e "${YELLOW}🛑 Stopping services...${NC}"
$COMPOSE_CMD down

echo ""
echo -e "${GREEN}✅ All services stopped${NC}"
echo ""
echo -e "${BLUE}💡 Data preserved in Docker volumes${NC}"
echo "   To remove all data: docker-compose down -v"
echo ""
