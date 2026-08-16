"""历史记忆按 user_id 隔离的集成测试（写入真实 MySQL，测试后清理）。"""
import pytest

from core.memory import (
    _mysql_connection,
    archive_working_to_historical,
    get_historical_context,
)

TEST_USER_A = 990001
TEST_USER_B = 990002


@pytest.fixture(autouse=True)
def cleanup_test_rows():
    yield
    conn = _mysql_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM ai_historical_analysis WHERE user_id IN (%s, %s)",
                (TEST_USER_A, TEST_USER_B),
            )
        conn.commit()
    finally:
        conn.close()


def test_archive_and_context_for_same_user():
    vision = {
        "hazard_category": "消防安全",
        "severity": "高",
        "description": "测试描述-电气线路老化",
    }
    archive_working_to_historical(
        TEST_USER_A, "sess-a", "报告A", vision=vision, dialogue="[用户]: 问题"
    )

    ctx = get_historical_context(TEST_USER_A)

    assert "消防安全" in ctx
    assert "测试描述-电气线路老化" in ctx
    assert "用户关注隐患类别" in ctx


def test_users_are_isolated():
    vision = {"hazard_category": "建筑施工", "severity": "中", "description": "A用户案例"}
    archive_working_to_historical(TEST_USER_A, "sess-a", "报告A", vision=vision)

    ctx_a = get_historical_context(TEST_USER_A)
    ctx_b = get_historical_context(TEST_USER_B)

    assert "建筑施工" in ctx_a
    assert ctx_b == ""


def test_archive_without_user_id_does_nothing():
    archive_working_to_historical(None, "sess-null", "报告")
    # 不应抛异常，也不影响任何用户上下文
    assert get_historical_context(TEST_USER_B) == ""