# Temporal

Local infrastructure is split into focused Compose fragments under `docker/compose/` and imported by the root `docker-compose.yaml`.

Temporal is used for durable background workflows. RabbitMQ is intentionally not part of the local stack.

## Services

- `postgres`: application database on `localhost:5432`
- `redis`: application cache/runtime Redis on `localhost:8379`
- `qdrant`: vector database on `localhost:6333` and `localhost:6334`
- `temporal`: Temporal frontend on `localhost:7233`
- `temporal-ui`: Temporal UI on `http://localhost:8080`
- `temporal-postgresql`: internal Temporal persistence database
- `temporal-elasticsearch`: Temporal visibility store on `localhost:9200`

Temporal Postgres is separate from the application Postgres service and is not exposed on host port `5432`.

## Commands

Validate the merged Compose config:

```bash
docker compose config
```

Start the application dependencies:

```bash
docker compose up -d postgres redis qdrant
```

Start the full local stack, including the FastAPI backend on `http://localhost:8000`:

```bash
docker compose up -d
```

The backend container bind-mounts `backend/` for live reload and uses a Linux virtualenv volume for container dependencies. Docker Compose reads the same development secrets file as local backend tooling: `backend/config/values/secrets.yaml`. Use Compose service names such as `postgres` and `redis` in that file when running the backend in containers.

Start Temporal and its UI:

```bash
docker compose up -d temporal-ui
```

Run the email worker:

```bash
docker compose up -d email-worker
```

The API and worker both read `TEMPORAL_ADDRESS`, `TEMPORAL_NAMESPACE`, and `TEMPORAL_EMAIL_TASK_QUEUE`. The default email task queue is `manudocs-email`.

Inspect service state:

```bash
docker compose ps
```

The Temporal auto-setup container initializes Postgres schemas and Elasticsearch visibility. The namespace setup job ensures the `default` namespace is available before the UI starts.