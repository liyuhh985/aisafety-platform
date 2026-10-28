package com.safety.service.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.safety.pojo.entity.Hazard;
import com.safety.pojo.vo.HazardMapVO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.math.BigDecimal;
import java.util.List;

@Mapper
public interface HazardMapper extends BaseMapper<Hazard> {

    /**
     * 撤回：仅「创建人本人 + status=0（未受理）」时生效（条件更新，避免先查后改的竞态）。
     * 返回受影响行数：0 表示不满足条件（不存在 / 非本人 / 已被受理 / 已撤回）。
     */
    @Update("UPDATE tb_hazard SET status = 5, withdrawn_at = NOW(), withdrawn_by = #{userId},"
            + " update_time = NOW() WHERE id = #{id} AND user_id = #{userId} AND status = 0")
    int withdraw(@Param("id") Long id, @Param("userId") Long userId);

    /** 管理员撤回无效工单：仅待处理/已接单/整改中可进入已撤回。 */
    @Update("UPDATE tb_hazard SET status = 5, withdrawn_at = NOW(),"
            + " withdrawn_by = #{adminId}, withdrawn_reason = #{reason}, update_time = NOW()"
            + " WHERE id = #{id} AND status IN (0, 1, 2)")
    int adminWithdraw(@Param("id") Long id,
                      @Param("adminId") Long adminId,
                      @Param("reason") String reason);

    /** 派单/改派：待处理、已接单或已驳回任务可原子流转到已接单并替换处理人。 */
    @Update("UPDATE tb_hazard SET status = 1, reviewed = 0, handler_id = #{handlerId},"
            + " update_time = NOW() WHERE id = #{id} AND status IN (0, 1, 4)")
    int assign(@Param("id") Long id, @Param("handlerId") Long handlerId);

    /** 处理人流转：状态和 handler_id 在同一条 UPDATE 中校验，避免旧实体覆盖并发撤回。 */
    @Update("UPDATE tb_hazard SET status = #{toStatus},"
            + " reviewed = CASE WHEN #{toStatus} = 3 THEN 0 ELSE reviewed END,"
            + " update_time = NOW() WHERE id = #{id} AND status = #{fromStatus}"
            + " AND handler_id = #{userId}")
    int transitionForHandler(@Param("id") Long id,
                             @Param("fromStatus") int fromStatus,
                             @Param("toStatus") int toStatus,
                             @Param("userId") Long userId);

    /** 管理员流转：仍必须匹配旧状态，但不限定处理人。 */
    @Update("UPDATE tb_hazard SET status = #{toStatus},"
            + " reviewed = CASE WHEN #{toStatus} = 3 THEN 0 ELSE reviewed END,"
            + " update_time = NOW() WHERE id = #{id} AND status = #{fromStatus}")
    int transitionAsAdmin(@Param("id") Long id,
                          @Param("fromStatus") int fromStatus,
                          @Param("toStatus") int toStatus);

    /** 终审：只有待验收（status=3 且 reviewed=0/null）能被一个并发请求消费。 */
    @Update("UPDATE tb_hazard SET status = #{toStatus}, reviewed = #{reviewed}, update_time = NOW()"
            + " WHERE id = #{id} AND status = 3 AND (reviewed = 0 OR reviewed IS NULL)")
    int review(@Param("id") Long id,
               @Param("toStatus") int toStatus,
               @Param("reviewed") int reviewed);

    /** 创建人修改定位：仅待处理且本人，禁止整行回写。 */
    @Update("UPDATE tb_hazard SET longitude = #{longitude}, latitude = #{latitude},"
            + " address = #{address}, district = COALESCE(NULLIF(#{district}, ''), district),"
            + " update_time = NOW() WHERE id = #{id} AND user_id = #{userId} AND status = 0")
    int updateLocationByCreator(@Param("id") Long id,
                                @Param("userId") Long userId,
                                @Param("longitude") BigDecimal longitude,
                                @Param("latitude") BigDecimal latitude,
                                @Param("address") String address,
                                @Param("district") String district);

    /** 管理员修改定位：仍只允许待处理状态。 */
    @Update("UPDATE tb_hazard SET longitude = #{longitude}, latitude = #{latitude},"
            + " address = #{address}, district = COALESCE(NULLIF(#{district}, ''), district),"
            + " update_time = NOW() WHERE id = #{id} AND status = 0")
    int updateLocationAsAdmin(@Param("id") Long id,
                              @Param("longitude") BigDecimal longitude,
                              @Param("latitude") BigDecimal latitude,
                              @Param("address") String address,
                              @Param("district") String district);

    /** 公开地图只读取脱敏白名单列，且最多由服务层限制为 100 行。 */
    @Select("SELECT id, longitude, latitude, hazard_type, status, district"
            + " FROM tb_hazard WHERE status <> 5 AND longitude IS NOT NULL AND latitude IS NOT NULL"
            + " ORDER BY create_time DESC LIMIT #{limit}")
    List<HazardMapVO> selectMapPoints(@Param("limit") int limit);

    /** AI 建单幂等：按 request_id 回查已建记录。 */
    @Select("SELECT * FROM tb_hazard WHERE request_id = #{requestId} LIMIT 1")
    Hazard selectByRequestId(@Param("requestId") String requestId);
}