package com.safety.pojo.dto;

import lombok.Data;

import java.math.BigDecimal;

/**
 * MQ 建单消息体（Python 生产，Java 消费）。
 * 字段与 Python 侧 tools/hazard_create_queue.build_message() 对齐。
 */
@Data
public class HazardCreateMessage {
    /** 幂等键：Python 侧 ai_hazard_create_request.request_id */
    private String requestId;
    private Long userId;
    private String sessionId;
    private String category;
    private String address;
    private String district;
    private BigDecimal longitude;
    private BigDecimal latitude;
    private String description;
    private Integer severity;
    private String imageUrl;
    private String report;
    private String createdAt;
}