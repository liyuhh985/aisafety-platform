package com.safety.service.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.safety.pojo.dto.HazardDTO;
import com.safety.pojo.vo.HazardVO;

public interface HazardService {
    HazardVO create(Long userId, HazardDTO dto);
    Page<HazardVO> page(int current, int size);
    HazardVO getById(Long id);
}
