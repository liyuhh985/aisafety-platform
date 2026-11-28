import subprocess
import sys
from pathlib import Path

from db.schema.cleanup_redis_v2 import (
    FORBIDDEN_PREFIXES,
    RemovalPlan,
    build_delete_prefixes,
    collect_removal_plan,
    execute_removal_plan,
)


class FakeRedis:
    def __init__(self, data):
        self.data = dict(data)
        self.unlinked = []

    def scan_iter(self, match=None, count=None):
        prefix = (match or "").rstrip("*")
        for key in sorted(self.data):
            if key.startswith(prefix):
                yield key

    def unlink(self, *keys):
        deleted = 0
        for key in keys:
            if self.data.pop(key, None) is not None:
                deleted += 1
        self.unlinked.extend(keys)
        return deleted


def test_build_delete_prefixes_reads_runtime_session_and_redis_checkpoint(monkeypatch):
    monkeypatch.setattr(
        "db.schema.cleanup_redis_v2.SESSION_REDIS_PREFIX", "tenant-a:session:"
    )
    monkeypatch.setattr(
        "db.schema.cleanup_redis_v2.CHECKPOINT_BACKEND", "redis"
    )

    prefixes = build_delete_prefixes(
        checkpoint_prefixes=("checkpoint:", "checkpoint_write:", "checkpoint_latest:")
    )

    assert prefixes == (
        "tenant-a:session:",
        "ai:hist:",
        "safety:hazard:",
        "safety:hazard:list:",
        "checkpoint:",
        "checkpoint_write:",
        "checkpoint_latest:",
    )


def test_build_delete_prefixes_skips_checkpoint_prefixes_when_backend_is_memory(monkeypatch):
    monkeypatch.setattr(
        "db.schema.cleanup_redis_v2.SESSION_REDIS_PREFIX", "ai:sess:"
    )
    monkeypatch.setattr(
        "db.schema.cleanup_redis_v2.CHECKPOINT_BACKEND", "memory"
    )

    assert build_delete_prefixes(checkpoint_prefixes=("checkpoint:",)) == (
        "ai:sess:",
        "ai:hist:",
        "safety:hazard:",
        "safety:hazard:list:",
    )


def test_collect_removal_plan_dedupes_overlapping_hazard_list_keys():
    redis = FakeRedis(
        {
            "ai:sess:1:chat": "x",
            "ai:hist:1:context": "x",
            "safety:hazard:9": "x",
            "safety:hazard:list:2": "x",
            "safety:token:abc": "x",
        }
    )

    plan = collect_removal_plan(
        redis,
        ("ai:sess:", "ai:hist:", "safety:hazard:", "safety:hazard:list:"),
    )

    assert plan.total == 4
    assert plan.keys == (
        "ai:hist:1:context",
        "ai:sess:1:chat",
        "safety:hazard:9",
        "safety:hazard:list:2",
    )
    assert plan.forbidden_hits == ()


def test_collect_removal_plan_reports_forbidden_hits_without_touching_keys():
    redis = FakeRedis(
        {
            "ai:sess:1": "x",
            "safety:token:abc": "x",
            "safety:email_code:a@b.com": "x",
            "safety:limit:user:1": "x",
        }
    )

    plan = collect_removal_plan(redis, ("ai:sess:", "safety:"))

    assert plan.forbidden_hits == (
        "safety:email_code:a@b.com",
        "safety:limit:user:1",
        "safety:token:abc",
    )
    assert redis.unlinked == []


def test_execute_removal_plan_refuses_forbidden_hits():
    redis = FakeRedis({"ai:sess:1": "x", "safety:token:abc": "x"})
    plan = RemovalPlan(
        keys=("ai:sess:1",),
        per_prefix={"ai:sess:": ("ai:sess:1",)},
        forbidden_hits=("safety:token:abc",),
    )

    try:
        execute_removal_plan(redis, plan, batch_size=10)
    except RuntimeError as exc:
        assert "安全闸门" in str(exc)
    else:
        raise AssertionError("execute accepted forbidden keys")
    assert redis.data == {"ai:sess:1": "x", "safety:token:abc": "x"}


def test_execute_removal_plan_deletes_only_planned_keys_in_batches():
    redis = FakeRedis(
        {
            "ai:sess:1": "x",
            "ai:hist:1": "x",
            "keep": "x",
        }
    )
    plan = RemovalPlan(
        keys=("ai:sess:1", "ai:hist:1"),
        per_prefix={"ai:sess:": ("ai:sess:1",), "ai:hist:": ("ai:hist:1",)},
        forbidden_hits=(),
    )

    deleted = execute_removal_plan(redis, plan, batch_size=1)

    assert deleted == 2
    assert redis.data == {"keep": "x"}
    assert redis.unlinked == ["ai:sess:1", "ai:hist:1"]
    assert FORBIDDEN_PREFIXES == (
        "safety:token:",
        "safety:email_code:",
        "safety:limit:",
    )



def test_script_runs_as_file_and_can_import_project_config():
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "db/schema/cleanup_redis_v2.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "--dry-run" in result.stdout
