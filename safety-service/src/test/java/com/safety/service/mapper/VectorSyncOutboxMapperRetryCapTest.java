package com.safety.service.mapper;

import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 契约锁：claim 路径的两条 SQL 都必须带 retry_count 上限，
 * 否则永久失败的任务（例如 Python 端返回 404）会无限重试。
 * 注意：这里断言的是 SQL 文本，不是运行时行为（本模块没有数据库可跑）。
 */
class VectorSyncOutboxMapperRetryCapTest {

    private static final String RETRY_CAP = "retry_count < 10";

    @Test
    void findClaimableStopsAfterRetryCap() throws Exception {
        String sql = normalize(sqlOf("findClaimable"));

        assertTrue(sql.contains(RETRY_CAP),
                "findClaimable 缺少重试上限: " + sql);
    }

    @Test
    void claimStopsAfterRetryCap() throws Exception {
        String sql = normalize(sqlOf("claim"));

        assertTrue(sql.contains(RETRY_CAP),
                "claim 缺少重试上限: " + sql);
    }

    private static String sqlOf(String methodName) throws Exception {
        for (Method method : VectorSyncOutboxMapper.class.getDeclaredMethods()) {
            if (!method.getName().equals(methodName)) {
                continue;
            }
            Select select = method.getAnnotation(Select.class);
            if (select != null) {
                return String.join(" ", select.value());
            }
            Update update = method.getAnnotation(Update.class);
            if (update != null) {
                return String.join(" ", update.value());
            }
        }
        throw new IllegalStateException("No annotated SQL found for " + methodName);
    }

    private static String normalize(String sql) {
        return sql.replaceAll("\s+", " ").toLowerCase();
    }
}
