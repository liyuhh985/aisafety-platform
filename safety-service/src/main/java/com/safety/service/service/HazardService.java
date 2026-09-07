package com.safety.service.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.safety.pojo.dto.AiHazardDTO;
import com.safety.pojo.dto.HazardDTO;
import com.safety.pojo.vo.HazardStatsVO;
import com.safety.pojo.vo.HazardVO;

public interface HazardService {
    HazardVO create(Long userId, HazardDTO dto);
    HazardVO createAi(AiHazardDTO dto);
    HazardVO accept(Long id, Long userId);
    HazardVO start(Long id, Long userId);
    HazardVO complete(Long id, Long userId);
    Page<HazardVO> page(int current, int size, Long userId, Integer role);
    HazardVO getById(Long id);
    HazardStatsVO getStats();
}
