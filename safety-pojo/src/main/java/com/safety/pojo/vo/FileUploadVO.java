package com.safety.pojo.vo;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class FileUploadVO {
    private Long fileId;
    private String objectKey;
    private String url;
    private String filename;
}
