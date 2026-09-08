package com.safety.service.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.safety.pojo.dto.AiHazardDTO;
import com.safety.pojo.dto.HazardDTO;
import com.safety.pojo.vo.HazardStatsVO;
import com.safety.pojo.vo.HazardVO;

public interface HazardService {
    HazardVO create(Long userId, HazardDTO dto);
    HazardVO createAi(AiHazardDTO dto);
    /** 管理员派单：指定处理人，0 待处理 -> 1 已接单 */
    HazardVO assign(Long id, Long adminId, Long handlerId);
    /** 处理人员开始整改：1 -> 2（仅限派给自己的任务；管理员可任意） */
    HazardVO start(Long id, Long userId, Integer role);
    /** 处理人员完成：2 -> 3（仅限派给自己的任务；管理员可任意） */
    HazardVO complete(Long id, Long userId, Integer role);
    /** 管理员人工审核：通过(pass=true)/驳回(pass=false, status=4) */
    HazardVO review(Long id, Long adminId, boolean pass, String remark);
    /** 管理员批量审核：批量通过或批量驳回 */
    java.util.List<HazardVO> batchReview(java.util.List<Long> ids, Long adminId, boolean pass, String remark);
    Page<HazardVO> page(int current, int size, Long userId, Integer role);
    HazardVO getById(Long id);
    HazardStatsVO getStats();
}
