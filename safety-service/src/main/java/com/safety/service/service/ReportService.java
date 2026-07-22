package com.safety.service.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.safety.pojo.dto.ReportSaveDTO;
import com.safety.pojo.entity.HazardReport;
import com.safety.service.mapper.HazardReportMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class ReportService {

    private final HazardReportMapper mapper;

    @Transactional
    public HazardReport save(Long userId, ReportSaveDTO dto) {
        HazardReport r = new HazardReport();
        r.setUserId(userId);
        r.setImageUrl(dto.getImageUrl());
        r.setVision(dto.getVision());
        r.setReport(dto.getReport());
        mapper.insert(r);
        return r;
    }

    public Page<HazardReport> page(Long userId, int current, int size) {
        Page<HazardReport> page = new Page<>(current, size);
        LambdaQueryWrapper<HazardReport> q = new LambdaQueryWrapper<>();
        if (userId != null) {
            q.eq(HazardReport::getUserId, userId);
        }
        q.orderByDesc(HazardReport::getCreateTime);
        return mapper.selectPage(page, q);
    }

    public HazardReport getById(Long id) {
        return mapper.selectById(id);
    }

    public void delete(Long id) {
        mapper.deleteById(id);
    }
}
