package com.safety.crawler.parser;

import lombok.extern.slf4j.Slf4j;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Component;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Slf4j
@Component
public class GovDocParser {

    private static final Pattern DATE_PATTERN = Pattern.compile("\\d{4}[-/]\\d{1,2}[-/]\\d{1,2}");

    /**
     * 解析一篇政府文章页面，提取结构化信息。
     * 适用于福建省/国家应急管理部 TRS CMS 模板。
     */
    public DocItem parse(String url) {
        try {
            Document doc = Jsoup.connect(url)
                    .userAgent("Mozilla/5.0 (compatible; SafetyBot/1.0)")
                    .timeout(15000)
                    .get();

            // 标题: <meta name="ArticleTitle"> 或 <div class="article_title">
            String title = meta(doc, "ArticleTitle");
            if (title.isEmpty()) {
                Element titleEl = doc.selectFirst(".article_title");
                title = titleEl != null ? titleEl.text().trim() : "";
            }

            // 日期: <meta name="PubDate"> 或 <span class="article_time">
            String dateStr = meta(doc, "PubDate");
            if (dateStr.isEmpty()) {
                Element timeEl = doc.selectFirst(".article_time");
                dateStr = timeEl != null ? timeEl.text().trim() : "";
            }
            String pubDate = extractDate(dateStr);

            // 来源: <meta name="SiteName"> 或 <meta name="ContentSource">
            String source = meta(doc, "SiteName");
            if (source.isEmpty()) {
                source = meta(doc, "ContentSource");
            }

            // 正文: 尝试多种常见政府CMS容器
            Element contentEl = doc.selectFirst(
                    ".article_content, .TRS_Editor, #zoom, .content, " +
                    ".article-body, .article-con, .text-content, " +
                    "div.view.TRS_UEDITOR, .Custom_UnionStyle, " +
                    "div[class*=article], div[class*=content]");
            String content = contentEl != null ? contentEl.text().trim() : "";

            if (title.isEmpty()) {
                log.warn("标题解析失败: {}", url);
                return null;
            }

            log.info("解析成功: {} | {}", pubDate, title);
            return DocItem.builder()
                    .title(title)
                    .url(url)
                    .publishDate(pubDate)
                    .source(source)
                    .region("福建省")
                    .content(content)
                    .build();

        } catch (Exception e) {
            log.error("解析页面失败 {}: {}", url, e.getMessage());
            return null;
        }
    }

    /** 从 meta 标签提取内容 */
    private String meta(Document doc, String name) {
        Element el = doc.selectFirst("meta[name=" + name + "]");
        return el != null ? el.attr("content").trim() : "";
    }

    /** 从文本中提取日期 */
    private String extractDate(String text) {
        Matcher m = DATE_PATTERN.matcher(text);
        if (m.find()) {
            String ds = m.group().replace("/", "-");
            try {
                return LocalDate.parse(ds, DateTimeFormatter.ofPattern("yyyy-M-d")).toString();
            } catch (Exception ignored) {}
        }
        return LocalDate.now().toString();
    }
}
