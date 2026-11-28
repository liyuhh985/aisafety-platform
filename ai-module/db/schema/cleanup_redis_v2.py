# -*- coding: utf-8 -*-
"""Precise Redis cleanup for Taxonomy v2a.

Only configured session/history/Java hazard-cache/checkpoint prefixes are
scanned. The script never calls FLUSHDB and refuses to delete if any auth,
email-code, or rate-limit key is in scope.
"""

import argparse
import os
import sys
from dataclasses import dataclass

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

import redis

from config import (
    CHECKPOINT_BACKEND,
    REDIS_DB,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
    REDIS_TIMEOUT_SECONDS,
    SESSION_REDIS_PREFIX,
)

FORBIDDEN_PREFIXES = (
    "safety:token:",
    "safety:email_code:",
    "safety:limit:",
)

FIXED_DELETE_PREFIXES = (
    "ai:hist:",
    "safety:hazard:",
    "safety:hazard:list:",
)

SCAN_BATCH_SIZE = 500
DELETE_BATCH_SIZE = 200


@dataclass(frozen=True)
class RemovalPlan:
    keys: tuple[str, ...]
    per_prefix: dict[str, tuple[str, ...]]
    forbidden_hits: tuple[str, ...]

    @property
    def total(self) -> int:
        return len(self.keys)


def build_delete_prefixes(checkpoint_prefixes=()) -> tuple[str, ...]:
    prefixes = []
    if SESSION_REDIS_PREFIX:
        prefixes.append(SESSION_REDIS_PREFIX)
    prefixes.extend(FIXED_DELETE_PREFIXES)
    if CHECKPOINT_BACKEND == "redis":
        prefixes.extend(checkpoint_prefixes)
    return tuple(dict.fromkeys(p for p in prefixes if p))


def resolve_checkpoint_prefixes(client) -> tuple[str, ...]:
    """Read the installed RedisSaver prefixes instead of hard-coding them."""
    from langgraph.checkpoint.redis import RedisSaver

    saver = RedisSaver(redis_client=client)
    prefixes = (
        str(getattr(saver, "_checkpoint_prefix", "checkpoint")) + ":",
        str(getattr(saver, "_checkpoint_write_prefix", "checkpoint_write")) + ":",
        "checkpoint_latest:",
    )
    return tuple(dict.fromkeys(prefixes))


def _scan_prefix(client, prefix: str) -> tuple[str, ...]:
    return tuple(client.scan_iter(match=prefix + "*", count=SCAN_BATCH_SIZE))


def collect_removal_plan(client, prefixes) -> RemovalPlan:
    seen = set()
    per_prefix = {}
    for prefix in prefixes:
        keys = tuple(sorted(str(key) for key in _scan_prefix(client, prefix)))
        per_prefix[prefix] = keys
        seen.update(keys)

    ordered_keys = tuple(sorted(seen))
    forbidden_hits = tuple(
        key for key in ordered_keys if key.startswith(FORBIDDEN_PREFIXES)
    )
    return RemovalPlan(
        keys=ordered_keys,
        per_prefix=per_prefix,
        forbidden_hits=forbidden_hits,
    )


def execute_removal_plan(client, plan: RemovalPlan, batch_size=DELETE_BATCH_SIZE) -> int:
    if plan.forbidden_hits:
        raise RuntimeError(
            "Redis 安全闸门触发：待删集合命中认证/验证码/限流键 "
            + ", ".join(plan.forbidden_hits[:10])
        )
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    deleted = 0
    for offset in range(0, len(plan.keys), batch_size):
        batch = plan.keys[offset : offset + batch_size]
        if not batch:
            continue
        if hasattr(client, "unlink"):
            removed = int(client.unlink(*batch))
        else:
            removed = int(client.delete(*batch))
        deleted += removed
    return deleted


def print_plan(plan: RemovalPlan, prefix_order=()):
    print("[Redis] 待删 key 总数（去重后）=%d" % plan.total)
    for prefix in prefix_order:
        keys = plan.per_prefix.get(prefix, ())
        print("  %s count=%d sample=%s" % (prefix, len(keys), list(keys[:5])))
    print(
        "[Redis] 安全白名单命中：safety:token:=%d safety:email_code:=%d safety:limit:=%d"
        % (
            sum(1 for key in plan.keys if key.startswith("safety:token:")),
            sum(1 for key in plan.keys if key.startswith("safety:email_code:")),
            sum(1 for key in plan.keys if key.startswith("safety:limit:")),
        )
    )


def _redis_client():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD or None,
        db=REDIS_DB,
        decode_responses=True,
        socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        socket_timeout=REDIS_TIMEOUT_SECONDS,
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Taxonomy v2a Redis cleanup")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="scan and print only")
    group.add_argument("--execute", action="store_true", help="delete only scanned keys")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not (args.dry_run or args.execute):
        args.dry_run = True

    client = _redis_client()
    try:
        client.ping()
        checkpoint_prefixes = (
            resolve_checkpoint_prefixes(client) if CHECKPOINT_BACKEND == "redis" else ()
        )
        prefixes = build_delete_prefixes(checkpoint_prefixes)
        print(
            "[Redis] configured SESSION_REDIS_PREFIX=%r CHECKPOINT_BACKEND=%r"
            % (SESSION_REDIS_PREFIX, CHECKPOINT_BACKEND)
        )
        plan = collect_removal_plan(client, prefixes)
        print_plan(plan, prefixes)
        if plan.forbidden_hits:
            raise RuntimeError("Redis 安全闸门触发；禁止执行删键")
        if args.execute:
            deleted = execute_removal_plan(client, plan)
            print("[Redis] 已删除 %d 个 key（仅限已打印前缀）" % deleted)
        else:
            print("[Redis] dry-run 完成，未删除任何 key")
        return 0
    except Exception as exc:
        print("[STOP] %s" % exc, file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
