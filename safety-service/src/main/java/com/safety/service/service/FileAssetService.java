package com.safety.service.service;

import com.safety.common.exception.BusinessException;
import com.safety.pojo.entity.FileAsset;
import com.safety.service.mapper.FileAssetMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;

@Service
@RequiredArgsConstructor
public class FileAssetService {

    public static final String STATUS_TEMP = "TEMP";
    public static final String STATUS_ATTACHED = "ATTACHED";
    public static final String STATUS_DELETING = "DELETING";
    public static final String VISIBILITY_AUTHENTICATED = "AUTHENTICATED";
    public static final String VISIBILITY_PRIVATE = "PRIVATE";

    private final FileAssetMapper mapper;

    @Value("${minio.bucket}")
    private String bucket;

    public FileAsset register(Long userId, String objectKey, String originalName,
                              String contentType, long sizeBytes) {
        FileAsset asset = new FileAsset();
        asset.setUserId(userId);
        asset.setBucket(bucket);
        asset.setObjectKey(objectKey);
        asset.setOriginalName(originalName);
        asset.setContentType(contentType);
        asset.setSizeBytes(sizeBytes);
        asset.setStatus(STATUS_TEMP);
        asset.setExpiresAt(LocalDateTime.now().plusHours(24));
        mapper.insert(asset);
        return asset;
    }

    public FileAsset requireOwned(Long fileId, Long userId) {
        if (fileId == null) {
            throw new BusinessException(400, "缺少图片文件标识");
        }
        FileAsset asset = mapper.selectOwned(fileId, userId);
        if (asset == null) {
            throw new BusinessException(404, "图片不存在");
        }
        if (STATUS_TEMP.equals(asset.getStatus())
                && asset.getExpiresAt() != null
                && asset.getExpiresAt().isBefore(LocalDateTime.now())) {
            throw new BusinessException(410, "图片已过期，请重新上传");
        }
        return asset;
    }

    public FileAsset requireReadable(Long fileId, Long userId) {
        return requireReadable(fileId, userId, false);
    }

    /** 临时图仅上传者；公开业务附件允许登录用户；私有报告附件仅所有者/管理员。 */
    public FileAsset requireReadable(Long fileId, Long userId, boolean admin) {
        FileAsset asset = mapper.selectById(fileId);
        if (asset == null || STATUS_DELETING.equals(asset.getStatus())) {
            throw new BusinessException(404, "图片不存在");
        }
        if (STATUS_ATTACHED.equals(asset.getStatus())) {
            if (VISIBILITY_PRIVATE.equals(asset.getVisibility()) && !admin
                    && !userId.equals(asset.getUserId())) {
                throw new BusinessException(404, "图片不存在");
            }
            return asset;
        }
        if (!STATUS_TEMP.equals(asset.getStatus()) || !userId.equals(asset.getUserId())) {
            throw new BusinessException(404, "图片不存在");
        }
        if (asset.getExpiresAt() != null && asset.getExpiresAt().isBefore(LocalDateTime.now())) {
            throw new BusinessException(410, "图片已过期，请重新上传");
        }
        return asset;
    }

    public void markAttached(Long fileId, Long userId) {
        markAttached(fileId, userId, VISIBILITY_AUTHENTICATED);
    }

    public void markAttached(Long fileId, Long userId, String visibility) {
        if (mapper.markAttached(fileId, userId, visibility) != 1) {
            throw new BusinessException(409, "图片状态已变化，请重新上传");
        }
    }

    /** 数据库只保存稳定访问路径；浏览器读取时仍必须携带登录凭证。 */
    public String accessPath(FileAsset asset) {
        return "/api/files/" + asset.getId();
    }

    public void deleteByObjectKey(String objectKey) {
        if (objectKey != null && !objectKey.isBlank()) {
            mapper.deleteByObjectKey(objectKey);
        }
    }

    public List<FileAsset> findExpiredTemps(int limit) {
        return mapper.findExpiredTemps(Math.max(1, Math.min(limit, 200)));
    }

    public boolean claimExpiredTemp(Long id, String claimToken) {
        return mapper.claimExpiredTemp(id, claimToken) == 1;
    }

    public boolean releaseCleanupFailure(Long id, String claimToken) {
        return mapper.releaseCleanupFailure(id, claimToken) == 1;
    }

    public boolean deleteClaimedTemp(Long id, String claimToken) {
        return mapper.deleteClaimedTemp(id, claimToken) == 1;
    }
}


