package com.safety.service.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.safety.pojo.entity.Hazard;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface HazardMapper extends BaseMapper<Hazard> {

    /**
     * 撤回：仅「创建人本人 + status=0（未受理）」时生效（条件更新，避免先查后改的竞态）。
     * 返回受影响行数：0 表示不满足条件（不存在 / 非本人 / 已被受理 / 已撤回）。
     */
    @Update("UPDATE tb_hazard SET status = 5, withdrawn_at = NOW(), withdrawn_by = #{userId},"
            + " update_time = NOW() WHERE id = #{id} AND user_id = #{userId} AND status = 0")
    int withdraw(@Param("id") Long id, @Param("userId") Long userId);
}
