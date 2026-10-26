package com.safety.service.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.safety.common.exception.BusinessException;
import com.safety.pojo.dto.ReportSaveDTO;
import com.safety.pojo.entity.FileAsset;
import com.safety.pojo.entity.HazardReport;
import com.safety.service.mapper.HazardReportMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Slf4j
@Service
public class ReportService {

    /** 图片对象名在 image_url 里的最大长度，超过就认为解析结果不可信。 */
    private static final int MAX_OBJECT_KEY_LENGTH = 128;
    private static final String REPORT_SOURCE_TABLE = "tb_hazard_report";

    private final HazardReportMapper mapper;
    private final FileUploadService fileUploadService;
    private final ResourceCleanupOutboxService cleanupOutboxService;
    private final FileAssetService fileAssetService;
    private final TransactionTemplate cleanupTransaction;

    private static final ObjectMapper json = new ObjectMapper();

    @Autowired
    public ReportService(
            HazardReportMapper mapper,
            FileUploadService fileUploadService,
            ResourceCleanupOutboxService cleanupOutboxService,
            FileAssetService fileAssetService,
            PlatformTransactionManager transactionManager) {
        this.mapper = mapper;
        this.fileUploadService = fileUploadService;
        this.cleanupOutboxService = cleanupOutboxService;
        this.fileAssetService = fileAssetService;
        this.cleanupTransaction = new TransactionTemplate(transactionManager);
    }

    /** 兼容旧单元测试的构造器；生产环境使用带 FileAssetService 的构造器。 */
    ReportService(
            HazardReportMapper mapper,
            FileUploadService fileUploadService,
            ResourceCleanupOutboxService cleanupOutboxService,
            PlatformTransactionManager transactionManager) {
        this(mapper, fileUploadService, cleanupOutboxService, null, transactionManager);
    }

    @Transactional(rollbackFor = Exception.class)
    public HazardReport save(Long userId, ReportSaveDTO dto) {
        FileAsset asset = null;
        if (dto.getFileId() != null) {
            if (fileAssetService == null) {
                throw new BusinessException(500, "文件服务未就绪");
            }
            asset = fileAssetService.requireOwned(dto.getFileId(), userId);
            if (!FileAssetService.STATUS_TEMP.equals(asset.getStatus())) {
                throw new BusinessException(409, "图片已使用或状态无效");
            }
        } else if (dto.getImageUrl() != null && !dto.getImageUrl().isBlank()) {
            throw new BusinessException(400, "请先通过上传接口上传图片");
        }

        HazardReport r = new HazardReport();
        r.setUserId(userId);
        if (asset != null) {
            r.setImageUrl(fileAssetService.accessPath(asset));
            r.setImageKey(asset.getObjectKey());
        }
        r.setHazardCategory(dto.getHazardCategory());
        r.setSeverity(dto.getSeverity());
        r.setDescription(dto.getDescription());
        r.setReportText(dto.getReportText());
        try {
            r.setRectification(json.writeValueAsString(dto.getRectification()));
        } catch (JsonProcessingException e) {
            r.setRectification("[]");
        }
        mapper.insert(r);
        if (asset != null) {
            fileAssetService.markAttached(asset.getId(), userId, FileAssetService.VISIBILITY_PRIVATE);
        }
        return r;
    }

    public Page<HazardReport> page(Long userId, int current, int size) {
        Page<HazardReport> page = new Page<>(current, size);
        LambdaQueryWrapper<HazardReport> q = new LambdaQueryWrapper<>();
        if (userId != null) {
            q.eq(HazardReport::getUserId, userId);
        }
        q.orderByDesc(HazardReport::getCreateTime)
         .select(HazardReport::getId, HazardReport::getImageUrl,
                 HazardReport::getHazardCategory, HazardReport::getSeverity,
                 HazardReport::getDescription, HazardReport::getRectification,
                 HazardReport::getReportText, HazardReport::getCreateTime);
        return mapper.selectPage(page, q);
    }

    public HazardReport getById(Long id, Long userId) {
        LambdaQueryWrapper<HazardReport> q = new LambdaQueryWrapper<HazardReport>()
                .eq(HazardReport::getId, id);
        if (userId != null) {
            q.eq(HazardReport::getUserId, userId);
        }
        return mapper.selectOne(q);
    }

    /**
     * 删除报告：先删 MinIO 对象，再删数据库行。
     *
     * 顺序（见 spec §3.1）：查行 → 删对象 → 失败则「入队清理任务 + 删行」在同一事务里 → 删行。
     * 查不到（不存在或越权）时对象与行都不动。
     * 入队失败必须整体回滚：否则 image_key 随行一起丢失，对象就再也没人能删了。
     */
    public void delete(Long id, Long userId) {
        HazardReport row = getById(id, userId);
        if (row == null) {
            return;
        }
        String objectKey = row.getImageKey() != null && !row.getImageKey().isBlank()
                ? row.getImageKey()
                : objectKeyOf(row.getImageUrl());
        if (objectKey == null) {
            log.warn("报告 {} 无法定位图片对象，仅删除数据库行: image_key={} image_url={}",
                    id, row.getImageKey(), row.getImageUrl());
            mapper.deleteById(row.getId());
            return;
        }
        if (removeObjectQuietly(objectKey)) {
            mapper.deleteById(row.getId());
            if (fileAssetService != null) {
                fileAssetService.deleteByObjectKey(objectKey);
            }
            return;
        }
        cleanupTransaction.executeWithoutResult(status -> {
            cleanupOutboxService.enqueueObjectDelete(
                    fileUploadService.bucketName(), objectKey, REPORT_SOURCE_TABLE, row.getId());
            mapper.deleteById(row.getId());
            if (fileAssetService != null) {
                fileAssetService.deleteByObjectKey(objectKey);
            }
        });
    }

    /** 删对象；失败不抛异常，返回 false 让调用方转投清理任务。 */
    private boolean removeObjectQuietly(String objectKey) {
        try {
            fileUploadService.removeObject(objectKey);
            return true;
        } catch (RuntimeException e) {
            log.warn("图片对象删除失败，转为后台清理任务: object={} reason={}",
                    objectKey, e.getMessage());
            return false;
        }
    }

    /**
     * 从图片 URL 末段取对象名（前端只给 URL 时用）。解析不出返回 null。
     * 例：http://host:9100/safety-images/ab12.png -> ab12.png
     */
    static String objectKeyOf(String imageUrl) {
        if (imageUrl == null) {
            return null;
        }
        String trimmed = imageUrl.trim();
        if (trimmed.isEmpty()) {
            return null;
        }
        int slash = trimmed.lastIndexOf('/');
        if (slash < 0 || slash == trimmed.length() - 1) {
            return null;
        }
        String key = trimmed.substring(slash + 1);
        int query = key.indexOf('?');
        if (query >= 0) {
            key = key.substring(0, query);
        }
        if (key.isBlank() || key.length() > MAX_OBJECT_KEY_LENGTH) {
            return null;
        }
        return key;
    }
}


