package com.safety.crawler.scheduler;

import com.safety.crawler.pipeline.DocPipeline;
import jakarta.annotation.PostConstruct;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.List;

@Slf4j
@Component
@RequiredArgsConstructor
public class CrawlScheduler {

    private final DocPipeline pipeline;

    /**
     * 项目启动时跑一次。
     * 部署后改为 @Scheduled(cron = "0 0 3 * * ?") 每天凌晨3点。
     * URL 来源: 手动收集 + 搜索发现 + 后续 AI 自动检索补充。
     */
    @PostConstruct
    public void onStartup() {
        log.info("========== 启动爬虫任务 ==========");
        int saved = pipeline.process(buildSeedUrls());
        log.info("========== 爬虫任务完成, 本轮新增 {} 条 ==========", saved);
    }

    /**
     * 种子 URL 列表。
     * 来源: 福建省应急管理厅公开的安全隐患相关通知。
     * 后续可扩展从 web_search Function Calling 自动发现新 URL。
     */
    private List<String> buildSeedUrls() {
        return List.of(
                // ====== 三明市 - 老旧小区改造（社区级） ======
                // 列东街道零星楼栋改造 - 可研批复
                "https://www.smsy.gov.cn/zwgk/ggzyjy/gcjsxmzbtb/shpzbaxx/202511/t20251127_2172789.htm",
                // 列东街道零星楼栋改造 - 初设批复
                "https://www.smsy.gov.cn/zwgk/ggzyjy/gcjsxmzbtb/shpzbaxx/202512/t20251219_2177908.htm",
                // 富兴堡街道零星楼栋改造 - 初设批复
                "http://www.smsy.gov.cn/zfxxgkzl/zfxxgkml/xmsh/202512/t20251219_2177944.htm",
                // 东安新村112、113幢危旧房改造
                "http://www.smsy.gov.cn/zfxxgkzl/zfxxgkml/xmsh/202511/t20251127_2172691.htm",
                // 绿岩税务小区海绵化改造
                "https://www.smsy.gov.cn/zwgk/ggzyjy/gcjsxmzbtb/shpzbaxx/202507/t20250711_2138237.htm",
                // 2026年三元区老旧小区改造(一期)
                "https://www.smsy.gov.cn/zwgk/ggzyjy/gcjsxmzbtb/shpzbaxx/202602/t20260212_2189986.htm",
                // 2026年三元区老旧小区改造(二期)可研
                "https://www.smsy.gov.cn/zwgk/ggzyjy/gcjsxmzbtb/shpzbaxx/202602/t20260203_2188101.htm",
                // 2026年三元区老旧小区改造(二期)初设
                "https://www.smsy.gov.cn/zwgk/ggzyjy/gcjsxmzbtb/shpzbaxx/202602/t20260212_2189988.htm",
                // 列东片区老旧小区改造(一期)
                "http://www.smsy.gov.cn/zfxxgkzl/zfxxgkml/xmsh/202302/t20230216_1880345.htm",
                // 列西至洋溪片区老旧小区改造(一期)
                "http://www.smsy.gov.cn/zwgk/ggzyjy/gcjsxmzbtb/shpzbaxx/202302/t20230216_1880354.htm",
                // 城关街道红印山凤岗片区老旧小区改造
                "http://www.smsy.gov.cn/zfxxgkzl/zfxxgkml/xmsh/202302/t20230217_1880608.htm",
                // 荆西至中村片区老旧小区改造(一期)
                "http://www.smsy.gov.cn/zwgk/ggzyjy/gcjsxmzbtb/shpzbaxx/202302/t20230217_1880613.htm",
                // 三元区零星危房改造实施方案
                "http://www.smsy.gov.cn/zfxxgkzl/zfxxgkml/fggzhgfxwj/202210/t20221011_1836599.htm",

                // ====== 三明市 - 安全隐患排查 ======
                // 三明市应急管理局 安全防范视频调度会
                "http://smsajj.sm.gov.cn/xxgk/gzdt/bdxw/202603/t20260330_2197508.htm",
                // 三元区安全生产月 排查整治风险隐患
                "http://www.smsy.gov.cn/zwgk/zhsgjy/yjczyjy/202606/t20260612_2215709.htm",
                // 三明市住建局 2025年老旧小区改造方案
                "https://zjj.sm.gov.cn/xxgk/fgwj/zxwj/cxjss/202506/t20250606_2129133.htm",

                // ====== 福建省应急管理厅 ======
                "http://yjt.fj.gov.cn/zwgk/dtyw/yjyw/202607/t20260718_7189655.htm"
        );
    }
}
