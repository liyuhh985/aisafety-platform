package com.safety.pojo.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
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

    /** 全部隐患类别；单隐患 1 条，复合隐患最多 3 条，顺序即展示顺序。 */
    @NotEmpty(message = "隐患类别不能为空")
    @Size(max = 3, message = "隐患类别最多 3 个")
    private List<@NotBlank(message = "隐患类别不能为空") String> categoryList;

    private String description;

    @NotNull(message = "经度不能为空")
    private BigDecimal longitude;

    @NotNull(message = "纬度不能为空")
    private BigDecimal latitude;

    private String address;

    private Integer severity;
}


