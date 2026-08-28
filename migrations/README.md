# Database migrations

Run migrations from a controlled deployment job:

```powershell
uv run alembic upgrade head
```

Application containers do not run migrations automatically. Migrations use an owner role; runtime services use restricted roles with PostgreSQL row-level security.

