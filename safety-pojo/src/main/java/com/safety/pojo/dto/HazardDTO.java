package com.safety.pojo.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

import java.math.BigDecimal;
import java.util.List;

@Data
public class HazardDTO {
    /** 旧字段仅用于识别并拒绝不可信客户端 URL；新客户端必须先上传再传 fileId。 */
    @Deprecated
    private String imageUrl;

    /** 通过 /api/upload/image 获取的文件标识。 */
    private Long fileId;

    @NotBlank(message = "隐患类型不能为空")
    private String hazardType;

    /** 多类别上报（最多 3 条，第一条为主类别） */
    private List<String> categoryList;

    private String description;

    @NotNull(message = "经度不能为空")
    private BigDecimal longitude;

    @NotNull(message = "纬度不能为空")
    private BigDecimal latitude;

    private String address;

    private Integer severity;
}


