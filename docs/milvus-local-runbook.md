# Milvus Local Runbook

This runbook uses one Milvus Standalone service with three logical collections. MySQL remains the source of truth for document content.

## Versions

- Milvus image: `milvusdb/milvus:v2.6.10`
- PyMilvus: `pymilvus==2.6.10`
- Required dependencies: etcd `v3.5.25`, MinIO `RELEASE.2024-05-28T17-19-04Z`

The server and SDK versions are pinned in `ai-module/docker-compose.milvus.yml` and `ai-module/requirements.txt`.

## Prerequisites

- Docker Desktop with the `docker compose` command.
- MySQL available using the values in the local `ai-module/.env`.
- SiliconFlow credentials in the local `ai-module/.env`.
- Local MinIO credentials in `MILVUS_MINIO_USER` and `MILVUS_MINIO_PASSWORD`. Do not commit these values.

Install the Python dependency with the interpreter used by the AI service:

```powershell
cd ai-module
python -m pip install -r requirements.txt
python -c "from pymilvus import MilvusClient; print('ok')"
```

## Start And Health Check

```powershell
cd ai-module
docker compose -f docker-compose.milvus.yml up -d
docker compose -f docker-compose.milvus.yml ps
python -m unittest tests.test_milvus_integration -v
```

The integration test is skipped unless `RUN_MILVUS_INTEGRATION=1` is set. To run it:

```powershell
$env:RUN_MILVUS_INTEGRATION="1"
python -m unittest tests.test_milvus_integration -v
```

The three collections are mapped as follows:

| MySQL table | Milvus collection |
| --- | --- |
| `tb_hazard_case` | `hazard_cases` |
| `tb_hazard_knowledge` | `hazard_policies` |
| `tb_regulation` | `hazard_regulations` |

## Synchronization

Run a full rebuild only after MySQL and the embedding API are available:

```powershell
python -m tools.knowledge_sync --source all --rebuild
```

Incremental synchronization processes one source at a time:

```powershell
python -m tools.knowledge_sync --source case
python -m tools.knowledge_sync --source policy
python -m tools.knowledge_sync --source regulation
```

The command logs read, skipped, upserted, and failed record counts. Embedding errors stop the command and return a non-zero exit code. The 256-dimensional local n-gram fallback is never inserted into Milvus.

## Enable Retrieval

After a successful full sync and smoke test, set these values only in the local `.env`:

```text
MILVUS_ENABLED=true
VECTOR_BACKEND=milvus
MILVUS_FALLBACK_TO_MYSQL=true
```

Restart the Python AI service. Test these queries and verify separate case, policy, and regulation sections:

```text
施工现场临时用电隐患
高处作业未设置防护措施
消防通道被占用
```

Milvus returns IDs only. Every formatted document must be hydrated from the latest MySQL row.

## Fallback And Rollback

To test fallback, stop only the Milvus container:

```powershell
docker compose -f docker-compose.milvus.yml stop standalone
```

With `MILVUS_FALLBACK_TO_MYSQL=true`, the AI service logs one concise warning per source and continues with the existing MySQL vector and keyword retrieval. Start Milvus again and restart the AI service after health checks pass.

For an immediate rollback, set:

```text
VECTOR_BACKEND=mysql
MILVUS_ENABLED=false
```

Restart only the AI service. Keep Milvus volumes intact during normal rollback.

## Stop And Backup

Stop the stack without deleting persistent data:

```powershell
docker compose -f docker-compose.milvus.yml stop
```

The compose file uses named volumes `milvus-etcd-data`, `milvus-minio-data`, and `milvus-data`. List their actual project-qualified names before backup:

```powershell
docker volume ls --filter label=com.docker.compose.project
```

Back up a volume by replacing `<volume-name>` and `<backup-folder>` with local paths:

```powershell
docker run --rm -v <volume-name>:/source -v <backup-folder>:/backup alpine tar czf /backup/milvus-volume.tgz -C /source .
```

Do not use `docker compose down -v` during a normal stop or rollback. It deletes the named volumes.
