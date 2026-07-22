package com.safety.pojo.dto;

import lombok.Data;
import java.util.List;

@Data
public class ReportSaveDTO {
    private String imageUrl;
    private String hazardCategory;
    private String severity;
    private String description;
    private List<String> rectification;
    private String reportText;
}
