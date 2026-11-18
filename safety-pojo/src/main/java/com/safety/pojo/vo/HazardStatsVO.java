package com.safety.pojo.vo;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class HazardStatsVO {
    private long total;
    private long processed;
    private long processing;
    /** 已撤回（status=5）：不计入 total/rate，单列展示 */
    private long withdrawn;
    private String rate;
}
