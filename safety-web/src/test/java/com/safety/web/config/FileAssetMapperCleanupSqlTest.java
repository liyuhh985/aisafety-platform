package com.safety.web.config;

import com.safety.service.mapper.FileAssetMapper;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Update;

import static org.junit.jupiter.api.Assertions.assertTrue;

class FileAssetMapperCleanupSqlTest {

    @Test
    void staleDeletingRowsAreEligibleForLeaseRecovery() throws Exception {
        Method method = FileAssetMapper.class.getMethod("findExpiredTemps", int.class);
        String sql = String.join(" ", method.getAnnotation(org.apache.ibatis.annotations.Select.class).value());

        assertTrue(sql.contains("status = 'DELETING'"));
        assertTrue(sql.contains("update_time <"));
    }
    @Test
    void cleanupMutationRequiresMatchingClaimToken() throws Exception {
        Method release = FileAssetMapper.class.getMethod(
                "releaseCleanupFailure", Long.class, String.class);
        Method delete = FileAssetMapper.class.getMethod(
                "deleteClaimedTemp", Long.class, String.class);

        assertTrue(String.join(" ", release.getAnnotation(Update.class).value())
                .contains("claim_token = #{claimToken}"));
        assertTrue(String.join(" ", delete.getAnnotation(Delete.class).value())
                .contains("claim_token = #{claimToken}"));
    }}

