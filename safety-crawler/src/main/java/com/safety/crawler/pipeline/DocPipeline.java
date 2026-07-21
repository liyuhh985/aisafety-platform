package com.safety.crawler.pipeline;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.safety.crawler.parser.DocItem;
import com.safety.crawler.parser.GovDocParser;
import com.safety.pojo.entity.HazardKnowledge;
import com.safety.service.mapper.HazardKnowledgeMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.List;

@Slf4j
@Component
@RequiredArgsConstructor
public class DocPipeline {

    private final GovDocParser parser;
    private final HazardKnowledgeMapper knowledgeMapper;

    /**
     * 逐篇爬取并入库。
     * 每篇都检查 URL 去重，避免重复写入。
     */
    public int process(List<String> urls) {
        int saved = 0;
        for (String url : urls) {
            long count = knowledgeMapper.selectCount(
                    new LambdaQueryWrapper<HazardKnowledge>()
                            .eq(HazardKnowledge::getSource, url));
            if (count > 0) {
                log.debug("已存在，跳过: {}", url);
                continue;
            }

            DocItem item = parser.parse(url);
            if (item == null) continue;

            HazardKnowledge doc = new HazardKnowledge();
            doc.setCategory("POLICY");
            doc.setRegion("三明市");
            doc.setPublishDate(item.getPublishDate());
            doc.setTitle(item.getTitle());
            doc.setContent(item.getContent().length() > 2000
                    ? item.getContent().substring(0, 2000)
                    : item.getContent());
            String sourceUrl = item.getUrl();
            doc.setSource(sourceUrl.length() > 199 ? sourceUrl.substring(0, 199) : sourceUrl);
            knowledgeMapper.insert(doc);
            saved++;
        }
        log.info("爬取完成: {} 条新增 / {} 条待爬", saved, urls.size());
        return saved;
    }
}
