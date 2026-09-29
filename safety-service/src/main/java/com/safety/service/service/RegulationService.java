package com.safety.service.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.safety.pojo.entity.Regulation;
import com.safety.service.mapper.RegulationMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class RegulationService {

    private final RegulationMapper mapper;
    private final VectorSyncOutboxService outboxService;

    public Page<Regulation> page(int current, int size, String category) {
        LambdaQueryWrapper<Regulation> q = new LambdaQueryWrapper<>();
        if (category != null && !category.isEmpty()) {
            q.eq(Regulation::getCategory, category);
        }
        q.orderByAsc(Regulation::getCategory, Regulation::getLawName);
        return mapper.selectPage(new Page<>(current, size), q);
    }

    public Regulation getById(Long id) {
        return mapper.selectById(id);
    }

    @Transactional(rollbackFor = Exception.class)
    public boolean delete(Long id) {
        if (mapper.deleteById(id) != 1) {
            return false;
        }
        outboxService.enqueueDelete("tb_regulation", id);
        return true;
    }
}
