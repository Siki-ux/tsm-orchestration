# water_dp-api Integration Guide

This guide explains how to run water_dp-api integrated with tsm-orchestration, using a shared PostgreSQL database.

## Architecture

```
dpV2/
├── tsm-orchestration/          ← Infrastructure (database, MQTT, FROST, etc.)
│   ├── docker-compose.yml
│   ├── docker-compose-water-dp.yml  ← Integration overlay
│   └── src/sql/water_dp/       ← Database schema
│
└── water_dp-api/               ← Application code
    ├── app/
    ├── Dockerfile
    └── ...
```

## Prerequisites

1. Both repositories cloned side-by-side in the same directory
2. tsm-orchestration containers running
3. Docker and Docker Compose installed

## Setup Steps

### 1. Start tsm-orchestration base services

```bash
cd tsm-orchestration
cp .env.example .env
# Edit .env as needed

docker-compose up -d
```

Wait for all services to be healthy:
```bash
docker-compose ps
```

### 2. Deploy water_dp database schema

```bash
# Copy SQL files into container and execute
docker-compose exec -T database psql -U postgres -d postgres < src/sql/water_dp/000_deploy_all.sql
```

Verify schema was created:
```bash
docker-compose exec -T database psql -U postgres -d postgres -c "\dn water_dp"
docker-compose exec -T database psql -U postgres -d postgres -c "\dt water_dp.*"
```

### 3. Add water_dp-api environment variables

Add these to your `.env` file:
```bash
# water_dp-api settings
WATER_DP_DEBUG=true
WATER_DP_SECRET_KEY=your-secret-key-change-in-production
WATER_DP_LOG_LEVEL=INFO
WATER_DP_API_PORT=8000
```

### 4. Start water_dp-api services

```bash
# Start with the integration overlay
docker-compose -f docker-compose.yml -f docker-compose-water-dp.yml up -d water-dp-redis water-dp-api water-dp-worker
```

### 5. Verify integration

Check services are running:
```bash
docker-compose -f docker-compose.yml -f docker-compose-water-dp.yml ps
```

Test the API:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/docs
```

## Database Connection

water_dp-api connects to the TSM database using the `water_dp` schema:

```
DATABASE_URL=postgresql://postgres:postgres@database:5432/postgres?options=-csearch_path=water_dp,public
```

This means:
- Tables are accessed in the `water_dp` schema by default
- PostGIS functions from `public` schema are available
- No separate postgres container is needed

## Convenience Commands

### Using docker-compose profiles (alternative)

You can set `COMPOSE_FILE` in `.env` to avoid long command lines:

```bash
# In .env
COMPOSE_FILE=docker-compose.yml:docker-compose-water-dp.yml
```

Then simply:
```bash
docker-compose up -d
```

### View water_dp schema

```bash
docker-compose exec -T database psql -U postgres -d postgres -c "
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'water_dp' ORDER BY table_name;
"
```

### View logs

```bash
# API logs
docker logs -f water-dp-api

# Worker logs
docker logs -f water-dp-worker
```

## Troubleshooting

### "relation does not exist" errors

The water_dp schema wasn't deployed. Run:
```bash
docker-compose exec -T database psql -U postgres -d postgres < src/sql/water_dp/000_deploy_all.sql
```

### Connection refused to database

1. Check TSM database is running: `docker-compose ps database`
2. Verify network connectivity: `docker network inspect tsm-orchestration_default`

### API not starting

1. Check logs: `docker logs water-dp-api`
2. Verify Redis is running: `docker-compose -f docker-compose.yml -f docker-compose-water-dp.yml ps water-dp-redis`

## Migrating from Standalone water_dp-api

If you were previously running water_dp-api with its own postgres:

1. Export data from old database:
   ```bash
   pg_dump -h localhost -p 5433 -U postgres water_app --data-only > water_dp_data.sql
   ```

2. Deploy schema to TSM database (see step 2 above)

3. Import data:
   ```bash
   # Set search_path and import
   docker-compose exec -T database psql -U postgres -d postgres -c "SET search_path TO water_dp;" < water_dp_data.sql
   ```

4. Stop old containers and switch to integrated setup
