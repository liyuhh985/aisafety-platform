# Milvus Public Authentication Design

## Goal

Allow the local AI service to connect directly to the cloud Milvus 2.6.10
instance over TCP 19530 while requiring Milvus authentication.

## Scope

- Enable Milvus built-in authorization.
- Replace the default `root` password with a generated high-entropy password.
- Listen publicly on TCP 19530.
- Keep port 9091, etcd, and MinIO private.
- Add authenticated Milvus client configuration to the AI module.
- Verify authenticated retrieval and rejection of invalid credentials.
- Preserve the existing MySQL fallback path.

Tencent Cloud security-group configuration is performed by the user. The initial
source range will be all IPv4 addresses (`0.0.0.0/0`) at the user's request and
must later be reduced to the client's current egress IP with a `/32` mask.

## Security Boundary

The first deployment will use Milvus authentication without TLS. This prevents
anonymous use but does not encrypt credentials or vector traffic in transit.
Opening TCP 19530 to `0.0.0.0/0` is therefore temporary and higher risk than an
SSH tunnel, VPN, TLS, or a source-IP allowlist.

The following endpoints remain inaccessible from the public network:

- Milvus health endpoint: `127.0.0.1:9091`
- Milvus etcd dependency: Docker network only
- Milvus MinIO dependency: Docker network only

No credential is committed to Git or printed in command output. The generated
password is stored only in `/home/ubuntu/milvus/.env` on the server and the ignored
`ai-module/.env` file on the client. Both files must be readable only by their owner
where the platform supports file permissions.

## Server Configuration

The remote Compose service adds:

```yaml
environment:
  COMMON_SECURITY_AUTHORIZATIONENABLED: "true"
ports:
  - "0.0.0.0:19530:19530"
  - "127.0.0.1:9091:9091"
```

Only `milvus-standalone` is recreated. The etcd, MinIO, and Milvus data volumes are
retained.

After authorization is enabled and the server is healthy, a one-time local client
connects through the existing SSH tunnel with the built-in `root:Milvus` credential
and changes the root password to a generated value of at least 32 random characters.
The default credential is used only for this bootstrap operation.

## Client Configuration

The AI module adds two environment variables:

```text
MILVUS_USER=root
MILVUS_PASSWORD=<generated secret>
```

`config.py` reads these values. `MilvusVectorStore` passes them to `MilvusClient`
without logging them. Existing dependency injection for test clients remains
unchanged.

The production connection values become:

```text
MILVUS_HOST=106.53.219.214
MILVUS_PORT=19530
MILVUS_ENABLED=true
VECTOR_BACKEND=milvus
MILVUS_FALLBACK_TO_MYSQL=true
```

## Deployment Sequence

1. Generate and store the new secret without displaying it.
2. Add authentication and public port binding to the remote Compose file.
3. Recreate only `milvus-standalone` and wait for a healthy status.
4. Rotate the built-in root password through the loopback SSH tunnel.
5. Update the ignored local `.env` with the new client credential.
6. Run authenticated integration and retrieval-quality tests through the tunnel.
7. Verify anonymous access and the default password are rejected.
8. Verify the new password works through the public server address after the user
   opens TCP 19530 in the Tencent Cloud security group.

The security group must not expose TCP 9091, 2379, 2380, 9000, or 9001.

## Error Handling And Rollback

If Milvus fails to become healthy after authorization is enabled, restore the
previous Compose file and recreate only `milvus-standalone`. Do not delete volumes.

If password rotation succeeds but the application cannot authenticate, keep Milvus
authorization enabled, correct the client credential through the SSH tunnel, and
leave `VECTOR_BACKEND=mysql` until authenticated live tests pass.

If direct public validation is unavailable because the security group has not been
updated, keep the public binding in place only after authentication tests pass over
the tunnel. Do not claim public connectivity until a direct test succeeds.

## Testing And Acceptance

- A unit test fails first unless `MilvusVectorStore` supplies configured credentials.
- Existing unauthenticated fake-client tests continue to pass.
- All AI-module unit tests pass.
- Authenticated `MilvusClient.list_collections()` succeeds.
- Existing collection counts remain 42 cases, 30 policies, and 53 regulations.
- Anonymous access fails.
- `root:Milvus` fails after password rotation.
- The generated credential passes the live integration and retrieval-quality tests.
- `milvus-standalone`, `milvus-etcd`, and `milvus-minio` remain healthy.
- TCP 9091 remains bound to `127.0.0.1`.
