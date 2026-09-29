package com.safety.service.service;

import com.safety.common.exception.BusinessException;
import com.safety.pojo.vo.FileUploadVO;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import io.minio.RemoveObjectArgs;
import io.minio.errors.ErrorResponseException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.util.Set;
import java.util.UUID;

@Slf4j
@Service
public class FileUploadService {

    private static final Set<String> ALLOWED_TYPES = Set.of(
            "image/jpeg", "image/png", "image/gif", "image/webp");
    private static final long MAX_SIZE = 10 * 1024 * 1024; // 10MB
    private static final String ERROR_NO_SUCH_KEY = "NoSuchKey";
    private static final String ERROR_NO_SUCH_BUCKET = "NoSuchBucket";

    private final MinioClient minioClient;

    @Value("${minio.bucket}")
    private String bucket;

    @Value("${minio.base-url}")
    private String baseUrl;

    @Autowired
    public FileUploadService(
            @Value("${minio.endpoint}") String endpoint,
            @Value("${minio.access-key}") String accessKey,
            @Value("${minio.secret-key}") String secretKey) {
        this.minioClient = MinioClient.builder()
                .endpoint(endpoint)
                .credentials(accessKey, secretKey)
                .build();
    }

    /** 供单元测试注入假客户端与桶名；Spring 走上面那个构造器。 */
    FileUploadService(MinioClient minioClient, String bucket) {
        this.minioClient = minioClient;
        this.bucket = bucket;
    }

    /** 当前配置的桶名（对象清理任务需要把它一起落库）。 */
    public String bucketName() {
        return bucket;
    }

    public FileUploadVO upload(MultipartFile file) {
        if (file.isEmpty()) {
            throw new BusinessException(400, "文件不能为空");
        }
        if (file.getSize() > MAX_SIZE) {
            throw new BusinessException(400, "文件大小不能超过10MB");
        }
        String contentType = file.getContentType();
        if (contentType == null || !ALLOWED_TYPES.contains(contentType)) {
            throw new BusinessException(400, "仅支持 jpg/png/gif/webp 格式");
        }

        String originalName = file.getOriginalFilename();
        String suffix = "";
        if (originalName != null && originalName.contains(".")) {
            suffix = originalName.substring(originalName.lastIndexOf("."));
        }
        String filename = UUID.randomUUID().toString().replace("-", "") + suffix;

        try {
            minioClient.putObject(PutObjectArgs.builder()
                    .bucket(bucket)
                    .object(filename)
                    .stream(file.getInputStream(), file.getSize(), -1)
                    .contentType(contentType)
                    .build());
        } catch (Exception e) {
            log.error("MinIO上传失败", e);
            throw new BusinessException(500, "文件上传失败，请重试");
        }

        String url = baseUrl + "/" + bucket + "/" + filename;
        return FileUploadVO.builder()
                .url(url)
                .filename(filename)
                .build();
    }

    /**
     * 删除 MinIO 对象（用当前配置的桶）。
     * 对象不存在视为成功（幂等）；真实失败抛 500 业务异常，由调用方决定是否转清理任务。
     */
    public void removeObject(String objectKey) {
        removeObject(bucket, objectKey);
    }

    /**
     * 删除指定桶里的对象。bucket 为空时退回当前配置的桶。
     * NoSuchKey / NoSuchBucket 视为成功（对象已经不在，重复删不报错）。
     */
    public void removeObject(String bucketName, String objectKey) {
        String target = (bucketName == null || bucketName.isBlank()) ? bucket : bucketName;
        if (target == null || target.isBlank() || objectKey == null || objectKey.isBlank()) {
            throw new BusinessException(500, "图片删除失败：桶名或对象名为空");
        }
        try {
            minioClient.removeObject(RemoveObjectArgs.builder()
                    .bucket(target)
                    .object(objectKey)
                    .build());
        } catch (ErrorResponseException e) {
            String code = e.errorResponse() == null ? null : e.errorResponse().code();
            if (ERROR_NO_SUCH_KEY.equals(code) || ERROR_NO_SUCH_BUCKET.equals(code)) {
                log.info("MinIO 对象已不存在，视为删除成功: bucket={} object={}", target, objectKey);
                return;
            }
            log.error("MinIO 删除对象失败: bucket={} object={}", target, objectKey, e);
            throw new BusinessException(500, "图片删除失败，请重试");
        } catch (Exception e) {
            log.error("MinIO 删除对象失败: bucket={} object={}", target, objectKey, e);
            throw new BusinessException(500, "图片删除失败，请重试");
        }
    }
}
