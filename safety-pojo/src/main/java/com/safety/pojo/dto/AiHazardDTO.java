package com.safety.pojo.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

import java.math.BigDecimal;

/**
 * AI 上报专用 DTO：由 Python 侧生成，经用户确认后由 Python 调用 Java 写入 tb_hazard。
 * 与前端手填 HazardDTO 解耦；category 必填，address/坐标/图片允许为空。
 */
@Data
public class AiHazardDTO {
    /** 上报用户（由 Python 从会话/用户上下文带入） */
    private Long userId;

    /** 隐患类别（4 类：占道 / 井盖与道路 / 消防通道 / 施工） */
    @NotBlank(message = "隐患类别不能为空")
    private String category;

    /** 自然语言地址文本（尽量有，允许空） */
    private String address;

    /** 行政区（省/市/区），地理编码或 AI 抽取 */
    private String district;

    /** 经度（可空：AI 无法定位时留空） */
    private BigDecimal longitude;

    /** 纬度（可空） */
    private BigDecimal latitude;

    /** 图片 URL（可空：AI 可能无图） */
    private String imageUrl;

    private String description;

    /** 严重程度：0 一般 / 1 较重 / 2 严重（或按项目约定，默认映射） */
    private Integer severity;

    /** AI 生成报告全文（可空） */
    private String report;
}
