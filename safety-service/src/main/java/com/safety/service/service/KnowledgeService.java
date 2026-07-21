package com.safety.service.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.safety.pojo.entity.HazardKnowledge;
import com.safety.service.mapper.HazardKnowledgeMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class KnowledgeService {

    private final HazardKnowledgeMapper mapper;

    /** 分页查询文书，可按地区和类别筛选 */
    public Page<HazardKnowledge> page(int current, int size, String region, String category) {
        LambdaQueryWrapper<HazardKnowledge> wrapper = new LambdaQueryWrapper<>();
        if (region != null && !region.isEmpty()) {
            wrapper.eq(HazardKnowledge::getRegion, region);
        }
        if (category != null && !category.isEmpty()) {
            wrapper.eq(HazardKnowledge::getCategory, category);
        }
        wrapper.orderByDesc(HazardKnowledge::getCreateTime);
        return mapper.selectPage(new Page<>(current, size), wrapper);
    }

    public HazardKnowledge getById(Long id) {
        return mapper.selectById(id);
    }
}
