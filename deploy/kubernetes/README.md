# Kubernetes deployment

The base deploys the four backend workloads (`api`, `worker`, `mcp-server`, and `guardian`),
their private services, a migration Job, and default-deny ingress controls. It expects managed
PostgreSQL 16 with `pgvector`, S3-compatible encrypted object storage, an OIDC provider, and an
OTLP collector.

1. Copy `base/secret.example.yaml`, replace every placeholder through your secret manager, and
   apply it as `xyena-secrets` without committing it.
2. Replace the image in `base/platform.yaml` with an immutable digest.
3. Apply the secret, then `kubectl apply -k deploy/kubernetes/base`.
4. Expose only `xyena-api` through the cluster ingress. MCP and Guardian remain private. If hosted
   MCP access is required, publish `/mcp` through a dedicated authenticated gateway and retain the
   service-token header.

The migration Job is intentionally separate. Production rollout automation must wait for it to
complete before updating application Deployments.
