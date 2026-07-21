package com.safety.crawler.parser;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class DocItem {
    private String title;
    private String url;
    private String publishDate;
    private String source;
    private String region;
    private String content;
}
