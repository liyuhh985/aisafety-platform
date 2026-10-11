> 状态：current
> 最后核对：2026-10-09
> 说明：Milvus 运维附录

# Milvus Remote Runbook

Milvus runs on the cloud server as a standalone deployment. MySQL remains the
source of truth for document content, and Milvus stores the synchronized vectors.

## Versions

- Milvus server: `v2.6.10`
- PyMilvus client: `pymilvus==2.6.10`
- etcd: `v3.5.25`
- MinIO: `RELEASE.2024-05-28T17-19-04Z`

## Connectivity

The cloud deployment publishes authenticated Milvus gRPC on TCP 19530. The health
endpoint remains bound to `127.0.0.1:9091`; etcd and the dedicated MinIO service
remain available only on the Docker network.

For direct access from the local AI service, configure:

```text
MILVUS_HOST=106.53.219.214
MILVUS_PORT=19530
MILVUS_USER=root
MILVUS_PASSWORD=the-secret-stored-in-ai-module-dot-env
```

Milvus built-in authorization is enabled and the default root password has been
rotated. Never commit the real password or place it in shell history.

The Tencent Cloud security group temporarily allows TCP 19530 from `0.0.0.0/0`.
This deployment does not yet use TLS, so replace that rule with
`125.79.183.235/32` when the client egress address is stable. Never expose TCP
9091, 2379, 2380, 9000, or 9001.

For private administration or recovery, an SSH tunnel remains available:

```powershell
ssh -N -L 29530:127.0.0.1:19530 <ssh-host>
```

Override `MILVUS_HOST=127.0.0.1` and `MILVUS_PORT=29530` only in the process that
uses this recovery tunnel.

## Health Check

Check the deployment on the cloud server:

```bash
cd ~/milvus
docker compose ps
curl -fsS http://127.0.0.1:9091/healthz
```

The health endpoint must return `OK`. The `milvus-standalone`, `milvus-etcd`, and
`milvus-minio` containers must all be healthy before synchronization or retrieval.

## Synchronization

Run a full rebuild after MySQL, the embedding API, and authenticated Milvus are
available:

```powershell
cd ai-module
python -m tools.knowledge_sync --source all --rebuild
```

Incremental synchronization processes one source at a time:

```powershell
python -m tools.knowledge_sync --source case
python -m tools.knowledge_sync --source policy
python -m tools.knowledge_sync --source regulation
```

The source-to-collection mapping is:

| MySQL table | Milvus collection |
| --- | --- |
| `tb_hazard_case` | `hazard_cases` |
| `tb_hazard_knowledge` | `hazard_policies` |
| `tb_regulation` | `hazard_regulations` |

## Enable Retrieval

After synchronization and live retrieval tests pass, set:

```text
MILVUS_HOST=106.53.219.214
MILVUS_PORT=19530
MILVUS_USER=root
MILVUS_PASSWORD=the-secret-stored-in-ai-module-dot-env
MILVUS_ENABLED=true
VECTOR_BACKEND=milvus
MILVUS_FALLBACK_TO_MYSQL=true
```

Restart the AI service after changing its environment. Milvus returns document IDs;
the service hydrates current document content from MySQL before formatting results.

## Tests

Run live tests from `ai-module` using the ignored `.env` credentials:

```powershell
$env:RUN_MILVUS_INTEGRATION="1"
python -m unittest tests.test_milvus_integration -v

$env:RUN_RETRIEVAL_QUALITY="1"
python -m unittest tests.test_retrieval_quality_cases -v
```

## Fallback And Rollback

Keep `MILVUS_FALLBACK_TO_MYSQL=true` so a Milvus connection or retrieval failure
falls back to the existing MySQL vector path.

For an immediate rollback, set:

```text
VECTOR_BACKEND=mysql
MILVUS_ENABLED=false
```

Restart only the AI service. Do not delete the cloud Milvus volumes during a normal
rollback.

## Cloud Operations

Run lifecycle commands only on the cloud server from `~/milvus`:

```bash
docker compose stop
docker compose up -d
docker compose logs --tail 100 standalone
```

Do not use `docker compose down -v` during normal operation. It deletes the named
etcd, MinIO, and Milvus volumes.
