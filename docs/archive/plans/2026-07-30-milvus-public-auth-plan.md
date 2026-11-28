> 状态：implemented
> 最后核对：2026-10-09
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# Milvus Public Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require a rotated Milvus root credential for direct TCP 19530 access from the local AI service.

**Architecture:** Milvus built-in authorization protects the existing standalone instance while Docker publishes only gRPC port 19530 publicly. The AI module reads credentials from untracked environment configuration and passes them directly to `pymilvus.MilvusClient`; MySQL fallback remains enabled. Health, etcd, and MinIO endpoints stay private.

**Tech Stack:** Python 3.13, PyMilvus 2.6.10, unittest, Docker Compose v5, Milvus 2.6.10, PowerShell, SSH

## Global Constraints

- Do not print, commit, or place the generated password in command arguments.
- Keep TCP 9091 bound to `127.0.0.1`; do not publish etcd or the dedicated MinIO service.
- Retain all existing Docker volumes and all 125 synchronized vectors.
- Recreate only `milvus-standalone` when changing authentication or port binding.
- Keep `MILVUS_FALLBACK_TO_MYSQL=true`.
- The temporary Tencent Cloud source range is `0.0.0.0/0`; replace it with the client egress `/32` as soon as practical.
- No TLS is added in this task, so the all-IPv4 rule is explicitly temporary.
- Preserve unrelated user changes in the dirty worktree and do not create subagents.

---

### Task 1: Authenticated PyMilvus Client

**Files:**
- Modify: `ai-module/tests/test_milvus_config.py`
- Modify: `ai-module/tests/test_milvus_store.py`
- Modify: `ai-module/config.py`
- Modify: `ai-module/tools/milvus_store.py`
- Modify: `ai-module/.env.example`

**Interfaces:**
- Consumes: environment variables `MILVUS_USER` and `MILVUS_PASSWORD`
- Produces: `MilvusVectorStore(user: str, password: str)` and an authenticated `MilvusClient`

- [ ] **Step 1: Add failing configuration assertions**

Add `MILVUS_USER` and `MILVUS_PASSWORD` to `MilvusConfigTests.ENV_DEFAULTS`, then assert they load as strings:

```python
"MILVUS_USER": "root",
"MILVUS_PASSWORD": "test-secret",
```

```python
self.assertEqual(config.MILVUS_USER, "root")
self.assertEqual(config.MILVUS_PASSWORD, "test-secret")
```

- [ ] **Step 2: Add a failing client-construction test**

Patch `pymilvus.MilvusClient` with a recording constructor and assert the real store passes credentials without changing injected fake clients:

```python
def test_connect_passes_configured_user_and_password(self):
    captured = {}

    class RecordingClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    store = MilvusVectorStore(
        host="milvus.example",
        port=19530,
        user="root",
        password="test-secret",
        embedding_dim=3,
    )
    module = types.SimpleNamespace(MilvusClient=RecordingClient)

    with patch.dict(sys.modules, {"pymilvus": module}):
        store.connect()

    self.assertEqual(captured["uri"], "http://milvus.example:19530")
    self.assertEqual(captured["user"], "root")
    self.assertEqual(captured["password"], "test-secret")
```

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```powershell
cd ai-module
python -m unittest tests.test_milvus_config tests.test_milvus_store -v
```

Expected: configuration assertions fail because the constants do not exist, and the store test fails because `user` and `password` are not accepted.

- [ ] **Step 4: Implement minimal credential configuration**

In `config.py` add:

```python
MILVUS_USER = os.getenv("MILVUS_USER", "")
MILVUS_PASSWORD = os.getenv("MILVUS_PASSWORD", "")
```

Import both constants in `tools/milvus_store.py`, add constructor parameters and fields, and pass them to `MilvusClient`:

```python
user: str = MILVUS_USER,
password: str = MILVUS_PASSWORD,
```

```python
self.user = user
self.password = password
```

```python
self.client = MilvusClient(
    uri=f"http://{self.host}:{self.port}",
    user=self.user,
    password=self.password,
    timeout=self.timeout_seconds,
)
```

Add blank examples, which contain no real secret:

```text
MILVUS_USER=
MILVUS_PASSWORD=
```

- [ ] **Step 5: Run focused and full unit tests**

Run:

```powershell
python -m unittest tests.test_milvus_config tests.test_milvus_store -v
python -m unittest discover -s tests -v
```

Expected: all unit tests pass; live tests remain skipped without their opt-in environment variables.

- [ ] **Step 6: Review the scoped diff**

Run:

```powershell
git diff --check -- ai-module/config.py ai-module/tools/milvus_store.py ai-module/tests/test_milvus_config.py ai-module/tests/test_milvus_store.py ai-module/.env.example
git diff -- ai-module/config.py ai-module/tools/milvus_store.py ai-module/tests/test_milvus_config.py ai-module/tests/test_milvus_store.py ai-module/.env.example
```

Do not commit these files separately because `config.py` and related files already contain overlapping user-owned changes in the dirty worktree.

### Task 2: Enable And Bootstrap Server Authentication

**Files:**
- Modify remotely: `/home/ubuntu/milvus/docker-compose.yml`
- Modify remotely: `/home/ubuntu/milvus/.env`
- Modify locally, ignored: `ai-module/.env`

**Interfaces:**
- Consumes: Milvus built-in bootstrap credential `root:Milvus`
- Produces: a generated 64-character hexadecimal password stored in both ignored environment files

- [ ] **Step 1: Back up and validate the remote Compose file**

Over SSH, copy `docker-compose.yml` to `docker-compose.yml.pre-auth`, require exactly one current loopback 19530 mapping, and run `docker compose config --quiet`. Abort if any check fails.

```bash
cd /home/ubuntu/milvus
cp -p docker-compose.yml docker-compose.yml.pre-auth
test "$(grep -c '127.0.0.1:19530:19530' docker-compose.yml)" -eq 1
docker compose config --quiet
```

- [ ] **Step 2: Generate and store the secret without output**

Use one PowerShell process to generate 32 random bytes as lowercase hexadecimal. The script updates the ignored local `.env`, sends the secret only over SSH standard input, and never writes it to stdout or a command argument:

```powershell
$taskEnvPath = (Resolve-Path "ai-module\.env").Path
$taskPassword = [Convert]::ToHexString(
    [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
).ToLowerInvariant()

function Set-TaskEnvValue {
    param([string]$Path, [string]$Name, [string]$Value)
    $taskLines = [Collections.Generic.List[string]]::new()
    $taskFound = $false
    foreach ($taskLine in [IO.File]::ReadAllLines($Path)) {
        if ($taskLine -match "^$([regex]::Escape($Name))=") {
            $taskLines.Add("$Name=$Value")
            $taskFound = $true
        } else {
            $taskLines.Add($taskLine)
        }
    }
    if (-not $taskFound) { $taskLines.Add("$Name=$Value") }
    [IO.File]::WriteAllLines(
        $Path,
        $taskLines,
        [Text.UTF8Encoding]::new($false)
    )
}

Set-TaskEnvValue $taskEnvPath "MILVUS_HOST" "106.53.219.214"
Set-TaskEnvValue $taskEnvPath "MILVUS_PORT" "19530"
Set-TaskEnvValue $taskEnvPath "MILVUS_USER" "root"
Set-TaskEnvValue $taskEnvPath "MILVUS_PASSWORD" $taskPassword
Set-TaskEnvValue $taskEnvPath "MILVUS_ENABLED" "true"
Set-TaskEnvValue $taskEnvPath "VECTOR_BACKEND" "milvus"
Set-TaskEnvValue $taskEnvPath "MILVUS_FALLBACK_TO_MYSQL" "true"

$taskRemoteScript = @'
set -eu
read -r task_secret
cd /home/ubuntu/milvus
umask 077
if grep -q '^MILVUS_ROOT_PASSWORD=' .env; then
  sed -i "s/^MILVUS_ROOT_PASSWORD=.*/MILVUS_ROOT_PASSWORD=$task_secret/" .env
else
  printf '\nMILVUS_ROOT_PASSWORD=%s\n' "$task_secret" >> .env
fi
chmod 600 .env
'@
$taskPassword | ssh -o BatchMode=yes 106.53.219.214 $taskRemoteScript
if ($LASTEXITCODE -ne 0) { throw "Remote secret storage failed" }
$taskPassword = $null
Write-Output "local_secret_stored=true"
Write-Output "remote_secret_stored=true"
```

- [ ] **Step 3: Add authorization and public gRPC binding**

Edit only these exact remote Compose values:

```yaml
environment:
  COMMON_SECURITY_AUTHORIZATIONENABLED: "true"
ports:
  - "0.0.0.0:19530:19530"
  - "127.0.0.1:9091:9091"
```

Validate with:

```bash
docker compose config --quiet
docker compose config | sed -n '/standalone:/,/^[^ ]/p'
```

Mask all password, secret, and access-key values before returning output.

- [ ] **Step 4: Recreate only Milvus standalone**

Run:

```bash
cd /home/ubuntu/milvus
docker compose up -d --no-deps --force-recreate standalone
```

Poll `.State.Health.Status` until it is `healthy`. Confirm etcd and MinIO container IDs did not change and all three restart counts remain zero.

- [ ] **Step 5: Rotate the default root password through an SSH tunnel**

Open a temporary local forward on port 29530. Load the generated password from the ignored local `.env` into the process without printing it, then run:

```python
import os

from pymilvus import MilvusClient

client = MilvusClient(
    uri="http://127.0.0.1:29530",
    user="root",
    password="Milvus",
)
client.update_password(
    user_name="root",
    old_password="Milvus",
    new_password=os.environ["MILVUS_PASSWORD"],
    reset_connection=True,
)
client.close()
```

Always close the SSH tunnel in a `finally` block.

- [ ] **Step 6: Verify credential rejection and acceptance**

Through the tunnel, call `list_collections()` three times:

- no user/password: must fail;
- `root:Milvus`: must fail;
- `root` with the generated password: must succeed.

Print only boolean results. Never print exception messages that could include connection metadata.

```python
import os
from pymilvus import MilvusClient


def can_list(user="", password=""):
    try:
        client = MilvusClient(
            uri="http://127.0.0.1:29530",
            user=user,
            password=password,
        )
        client.list_collections()
        client.close()
        return True
    except Exception:
        return False


anonymous_allowed = can_list()
default_allowed = can_list("root", "Milvus")
generated_allowed = can_list("root", os.environ["MILVUS_PASSWORD"])
print(f"anonymous_rejected={not anonymous_allowed}")
print(f"default_rejected={not default_allowed}")
print(f"generated_accepted={generated_allowed}")
assert not anonymous_allowed
assert not default_allowed
assert generated_allowed
```

- [ ] **Step 7: Verify data and private dependencies**

Using the generated credential, query `count(*)` and require:

```text
hazard_cases=42
hazard_policies=30
hazard_regulations=53
```

On the server, require `127.0.0.1:9091`, `0.0.0.0:19530`, healthy states for all three Milvus containers, and no published ports for the dedicated etcd or MinIO containers.

### Task 3: Enable The Application And Validate Direct Access

**Files:**
- Modify, ignored: `ai-module/.env`
- Modify: `docs/milvus-remote-runbook.md`

**Interfaces:**
- Consumes: authenticated public Milvus endpoint `106.53.219.214:19530`
- Produces: direct authenticated retrieval with MySQL fallback

- [ ] **Step 1: Verify ignored local runtime settings**

Task 2 has already stored these values in `ai-module/.env` without printing the password:

```text
MILVUS_HOST=106.53.219.214
MILVUS_PORT=19530
MILVUS_USER=root
MILVUS_ENABLED=true
VECTOR_BACKEND=milvus
MILVUS_FALLBACK_TO_MYSQL=true
```

Retain the generated `MILVUS_PASSWORD` value from Task 2.

- [ ] **Step 2: Pause for the Tencent Cloud security-group rule**

The user adds an inbound rule with protocol TCP, port 19530, and source `0.0.0.0/0`. Do not open 9091, 2379, 2380, 9000, or 9001.

- [ ] **Step 3: Verify direct authenticated connectivity**

Without an SSH tunnel, instantiate `MilvusVectorStore()` from `ai-module` and require `healthcheck()` to return true. Confirm TCP 19530 is reachable and TCP 9091 is not reachable from the client.

- [ ] **Step 4: Run live integration and quality tests directly**

Run:

```powershell
$env:RUN_MILVUS_INTEGRATION="1"
$env:RUN_RETRIEVAL_QUALITY="1"
python -m unittest tests.test_milvus_integration tests.test_retrieval_quality_cases -v
```

Expected: collection integration, ten-query Top-3 quality, and latency tests pass.

- [ ] **Step 5: Update the remote runbook**

Document `MILVUS_USER`, `MILVUS_PASSWORD`, built-in authorization, direct endpoint usage, the temporary all-IPv4 security-group rule, and the requirement to replace it with `125.79.183.235/32` when the current egress address is stable. Keep the existing warning that port 9091 and dependency ports remain private.

- [ ] **Step 6: Run final verification**

Run:

```powershell
python -m unittest discover -s tests -v
python -m unittest test_orchestrator_stream test_server_sse_errors test_server_upload_validation -v
git diff --check
git status --short --branch
```

Expected: all non-live tests pass, live tests have already passed directly, no whitespace errors exist, and unrelated user changes remain untouched.

### Task 4: Rollback Procedure If Authentication Deployment Fails

**Files:**
- Restore remotely only when acceptance checks fail: `/home/ubuntu/milvus/docker-compose.yml.pre-auth`

**Interfaces:**
- Consumes: the pre-auth Compose backup
- Produces: the last known healthy loopback-only Milvus deployment without deleting data

- [ ] **Step 1: Restore only after a failed server acceptance check**

Run:

```bash
cd /home/ubuntu/milvus
cp -p docker-compose.yml.pre-auth docker-compose.yml
docker compose config --quiet
docker compose up -d --no-deps --force-recreate standalone
```

- [ ] **Step 2: Confirm rollback health and data**

Require `milvus-standalone` to return to healthy, port 19530 to bind only to `127.0.0.1`, and the three collection counts to remain 42, 30, and 53 through the SSH tunnel.

- [ ] **Step 3: Keep application fallback enabled**

Set `VECTOR_BACKEND=mysql`, `MILVUS_ENABLED=false`, and retain `MILVUS_FALLBACK_TO_MYSQL=true` in the ignored local `.env` until a corrected authentication deployment passes all acceptance checks.
