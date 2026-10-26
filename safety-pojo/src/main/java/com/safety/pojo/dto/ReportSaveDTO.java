package com.safety.pojo.dto;

import lombok.Data;

import java.util.List;

@Data
public class ReportSaveDTO {
    /** 先通过 /api/upload/image 上传得到的服务端文件标识。 */
    private Long fileId;
    private String imageUrl;
    private String hazardCategory;
    private String severity;
    private String description;
    private List<String> rectification;
    private String reportText;
}
