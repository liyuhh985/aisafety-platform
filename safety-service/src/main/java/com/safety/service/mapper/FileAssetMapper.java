package com.safety.service.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.safety.pojo.entity.FileAsset;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface FileAssetMapper extends BaseMapper<FileAsset> {

    @Select("SELECT * FROM tb_file_asset WHERE id = #{id} AND user_id = #{userId} LIMIT 1")
    FileAsset selectOwned(@Param("id") Long id, @Param("userId") Long userId);

    @Update("UPDATE tb_file_asset SET status = 'ATTACHED', visibility = #{visibility}, expires_at = NULL, update_time = NOW() "
            + "WHERE id = #{id} AND user_id = #{userId} AND status = 'TEMP'")
    int markAttached(@Param("id") Long id, @Param("userId") Long userId,
                     @Param("visibility") String visibility);

    @Delete("DELETE FROM tb_file_asset WHERE object_key = #{objectKey}")
    int deleteByObjectKey(@Param("objectKey") String objectKey);

    @Select("SELECT * FROM tb_file_asset WHERE "
            + "(status = 'TEMP' AND expires_at < NOW()) OR "
            + "(status = 'DELETING' AND update_time < DATE_SUB(NOW(), INTERVAL 10 MINUTE)) "
            + "ORDER BY update_time LIMIT #{limit}")
    List<FileAsset> findExpiredTemps(@Param("limit") int limit);

    @Update("UPDATE tb_file_asset SET status = 'DELETING', claim_token = #{claimToken}, update_time = NOW() "
            + "WHERE id = #{id} AND ((status = 'TEMP' AND expires_at < NOW()) OR "
            + "(status = 'DELETING' AND update_time < DATE_SUB(NOW(), INTERVAL 10 MINUTE)))")
    int claimExpiredTemp(@Param("id") Long id, @Param("claimToken") String claimToken);

    @Update("UPDATE tb_file_asset SET status = 'TEMP', expires_at = DATE_ADD(NOW(), INTERVAL 1 HOUR), "
            + "update_time = NOW() WHERE id = #{id} AND status = 'DELETING' AND claim_token = #{claimToken}")
    int releaseCleanupFailure(@Param("id") Long id, @Param("claimToken") String claimToken);

    @Delete("DELETE FROM tb_file_asset WHERE id = #{id} AND status = 'DELETING' "
            + "AND claim_token = #{claimToken}")
    int deleteClaimedTemp(@Param("id") Long id, @Param("claimToken") String claimToken);
}



