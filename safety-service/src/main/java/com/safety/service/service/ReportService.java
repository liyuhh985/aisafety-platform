package com.safety.service.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.safety.pojo.dto.ReportSaveDTO;
import com.safety.pojo.entity.HazardReport;
import com.safety.service.mapper.HazardReportMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class ReportService {

    private final HazardReportMapper mapper;
    private static final ObjectMapper json = new ObjectMapper();

    public HazardReport save(Long userId, ReportSaveDTO dto) {
        HazardReport r = new HazardReport();
        r.setUserId(userId);
        r.setImageUrl(dto.getImageUrl());
        r.setHazardCategory(dto.getHazardCategory());
        r.setSeverity(dto.getSeverity());
        r.setDescription(dto.getDescription());
        r.setReportText(dto.getReportText());
        try {
            r.setRectification(json.writeValueAsString(dto.getRectification()));
        } catch (JsonProcessingException e) {
            r.setRectification("[]");
        }
        mapper.insert(r);
        return r;
    }

    public Page<HazardReport> page(Long userId, int current, int size) {
        Page<HazardReport> page = new Page<>(current, size);
        LambdaQueryWrapper<HazardReport> q = new LambdaQueryWrapper<>();
        if (userId != null) {
            q.eq(HazardReport::getUserId, userId);
        }
        q.orderByDesc(HazardReport::getCreateTime)
         .select(HazardReport::getId, HazardReport::getImageUrl,
                 HazardReport::getHazardCategory, HazardReport::getSeverity,
                 HazardReport::getDescription, HazardReport::getCreateTime);
        return mapper.selectPage(page, q);
    }

    public HazardReport getById(Long id) {
        return mapper.selectById(id);
    }

    public void delete(Long id) {
        mapper.deleteById(id);
    }
}
