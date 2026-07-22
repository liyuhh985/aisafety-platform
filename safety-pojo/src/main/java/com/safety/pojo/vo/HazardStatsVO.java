package com.safety.pojo.vo;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class HazardStatsVO {
    private long total;
    private long processed;
    private long processing;
    private String rate;
}
