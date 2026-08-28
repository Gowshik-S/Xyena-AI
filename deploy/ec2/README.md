# Xyena + Guardian EC2 deployment

This deployment runs Xyena, Guardian, the MCP control plane, and all portal origins on one EC2 host. It uses one PostgreSQL 16/pgvector container on the default port with a separate database and least-privilege login for every application. Redis and MinIO are private Docker-network services.

Cloudflare Tunnel is the only public ingress. Nginx and Caddy are intentionally not installed. Every published host port is bound to `127.0.0.1`, so neither PostgreSQL nor an application origin is directly reachable through the EC2 public interface.

## Services

| Public hostname | Local origin | Purpose |
| --- | --- | --- |
| `app.gowshik.in` | `http://localhost:4173` | Xyena web portal |
| `api.gowshik.in` | `http://localhost:8080` | Xyena OpenAPI-compatible API |
| `bank.gowshik.in` | `http://localhost:8090` | Bank and Account Aggregator portal/MCP |
| `gst.gowshik.in` | `http://localhost:8091` | GST portal/MCP |
| `erp.gowshik.in` | `http://localhost:8092` | Buyer ERP portal/MCP |
| `registry.gowshik.in` | `http://localhost:8093` | Business Registry portal/MCP |
| `funder.gowshik.in` | `http://localhost:8094` | Funder Marketplace portal/MCP |
| `delivery.gowshik.in` | `http://localhost:8095` | Delivery portal/MCP |
| `ledger.gowshik.in` | `http://localhost:8096` | Ledger and Payment Operations portal/MCP |

The central MCP gateway (`127.0.0.1:8081`) and Guardian (`127.0.0.1:8082`) are deliberately private. Portal MCP endpoints are protected by bearer credentials; tool execution still passes through the central reviewed registry and Guardian policy path.

## First deployment

```sh
cd /home/ubuntu/Xyena-AI
git pull --ff-only origin main
sudo deploy/ec2/bootstrap-host.sh
sudo docker compose --env-file .env -f compose.ec2.yaml version
sudo deploy/ec2/deploy.sh
```

The bootstrap adds a 2 GiB swap file because this EC2 size has about 4 GiB RAM and image builds can briefly exceed available memory. The deploy script builds sequentially, creates `.env` with mode `0600`, starts all services, registers and reviews every MCP catalog, and checks all local health endpoints. It never prints generated credentials.

After the first SSH session, the `ubuntu` user is in the Docker group; reconnect before running Docker without `sudo`.

## PostgreSQL layout

| Database | Login | Owner workload |
| --- | --- | --- |
| `xyena` | `xyena` | Core API, Guardian, worker, MCP registry |
| `bank_demo` | `bank_app` | Bank and Account Aggregator |
| `gst_demo` | `gst_app` | GST portal |
| `erp_demo` | `erp_app` | Buyer ERP |
| `registry_demo` | `registry_app` | Business Registry |
| `funder_demo` | `funder_app` | Funder Marketplace |
| `delivery_demo` | `delivery_app` | Delivery tracking |
| `ledger_demo` | `ledger_app` | Ledger and Payment Operations |

PostgreSQL is bound to `127.0.0.1:5432`. Applications connect over the private `platform` Docker network. The init script creates databases only when the PostgreSQL volume is first initialized; subsequent deploys preserve all data and credentials.

## Cloudflare Tunnel routes

The installed `cloudflared` service uses a remotely managed tunnel. In Cloudflare Zero Trust, open **Networks > Tunnels**, select tunnel `010e67ed-1248-4ea0-9059-b6f8a3111178`, then create the nine public hostnames in the service table above. Choose HTTP and use the exact `localhost` port. Add each hostname under the `gowshik.in` zone so Cloudflare creates its tunnel DNS record.

Do not publish ports 5432, 6379, 8081, 8082, 9000, or 9001. Do not add an ingress wildcard. Protect operator portals with Cloudflare Access before sharing credentials.

The connector token proves that the EC2 process may join the tunnel, but it is not a Cloudflare API token and cannot create DNS or public-hostname routes. Those routes must be added in the dashboard or with a separately scoped Cloudflare API token.

## Operations

```sh
# Status
sudo docker compose --env-file .env -f compose.ec2.yaml ps

# Local health and reachability
sudo deploy/ec2/smoke.sh

# Logs without revealing environment values
sudo docker compose --env-file .env -f compose.ec2.yaml logs --tail=200 api guardian mcp-server

# Deploy a later Git revision
git pull --ff-only origin main
sudo deploy/ec2/deploy.sh
```

Back up the `xyena-platform_postgres-data` and `xyena-platform_object-data` volumes before destructive maintenance. Never commit `.env`; to view a specific operator credential, read only the required key directly on EC2.

## Required production credentials

The generator safely creates database, service, MCP, portal, and Guardian signing secrets. Before enabling real agent runs, set a valid `XYENA_OPENAI_API_KEY`. Before opening authenticated core APIs to users, replace the placeholder OIDC issuer with the production identity provider and verify that `XYENA_DEV_AUTH_BYPASS=false` remains set.
