package com.safety.service.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.safety.pojo.entity.HazardCase;
import com.safety.service.mapper.HazardCaseMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class CaseService {

    private final HazardCaseMapper mapper;
    private final VectorSyncOutboxService outboxService;

    public Page<HazardCase> page(int current, int size, String city, String category) {
        LambdaQueryWrapper<HazardCase> wrapper = new LambdaQueryWrapper<>();
        if (city != null && !city.isEmpty()) {
            wrapper.eq(HazardCase::getCity, city);
        }
        if (category != null && !category.isEmpty()) {
            wrapper.eq(HazardCase::getCategory, category);
        }
        wrapper.orderByDesc(HazardCase::getCreateTime);
        return mapper.selectPage(new Page<>(current, size), wrapper);
    }

    @Transactional(rollbackFor = Exception.class)
    public boolean delete(Long id) {
        if (mapper.deleteById(id) != 1) {
            return false;
        }
        outboxService.enqueueDelete("tb_hazard_case", id);
        return true;
    }
}
