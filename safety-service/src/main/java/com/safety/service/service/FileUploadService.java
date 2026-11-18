package com.safety.service.service;

import com.safety.common.exception.BusinessException;
import com.safety.pojo.entity.FileAsset;
import com.safety.pojo.vo.FileUploadVO;
import io.minio.GetObjectArgs;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import io.minio.RemoveObjectArgs;
import io.minio.errors.ErrorResponseException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.stream.ImageInputStream;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.UUID;

@Slf4j
@Service
public class FileUploadService {

    private static final long MAX_SIZE = 10 * 1024 * 1024L;
    private static final long MAX_PIXELS = 24_000_000L;
    private static final int MAX_DIMENSION = 8000;
    private static final String ERROR_NO_SUCH_KEY = "NoSuchKey";
    private static final String ERROR_NO_SUCH_BUCKET = "NoSuchBucket";

    private final MinioClient minioClient;
    private final FileAssetService fileAssetService;

    @Value("${minio.bucket}")
    private String bucket;

    @Autowired
    public FileUploadService(
            @Value("${minio.endpoint}") String endpoint,
            @Value("${minio.access-key}") String accessKey,
            @Value("${minio.secret-key}") String secretKey,
            FileAssetService fileAssetService) {
        this.minioClient = MinioClient.builder()
                .endpoint(endpoint)
                .credentials(accessKey, secretKey)
                .build();
        this.fileAssetService = fileAssetService;
    }

    FileUploadService(MinioClient minioClient, String bucket) {
        this(minioClient, bucket, null);
    }

    FileUploadService(MinioClient minioClient, String bucket, FileAssetService fileAssetService) {
        this.minioClient = minioClient;
        this.bucket = bucket;
        this.fileAssetService = fileAssetService;
    }

    public String bucketName() {
        return bucket;
    }

    public FileUploadVO upload(Long userId, MultipartFile file) {
        if (userId == null) {
            throw new BusinessException(401, "未登录");
        }
        if (file == null || file.isEmpty()) {
            throw new BusinessException(400, "文件不能为空");
        }
        if (file.getSize() > MAX_SIZE) {
            throw new BusinessException(400, "文件大小不能超过10MB");
        }

        byte[] bytes;
        try {
            bytes = file.getBytes();
        } catch (Exception e) {
            throw new BusinessException(400, "读取图片失败");
        }
        ImageType type = detectType(bytes);
        validateDecodedImage(bytes, type);

        String filename = UUID.randomUUID().toString().replace("-", "") + type.suffix();
        try {
            minioClient.putObject(PutObjectArgs.builder()
                    .bucket(bucket)
                    .object(filename)
                    .stream(new ByteArrayInputStream(bytes), bytes.length, -1)
                    .contentType(type.contentType())
                    .build());
        } catch (Exception e) {
            log.error("MinIO上传失败", e);
            throw new BusinessException(500, "文件上传失败，请重试");
        }

        try {
            FileAsset asset = fileAssetService.register(
                    userId, filename, file.getOriginalFilename(), type.contentType(), bytes.length);
            return FileUploadVO.builder()
                    .fileId(asset.getId())
                    .objectKey(asset.getObjectKey())
                    .url(fileAssetService.accessPath(asset))
                    .filename(filename)
                    .build();
        } catch (RuntimeException e) {
            try {
                removeObject(filename);
            } catch (Exception cleanupError) {
                log.error("上传元数据失败后清理 MinIO 失败: object={}", filename, cleanupError);
            }
            throw e;
        }
    }

    public InputStream openObject(String bucketName, String objectKey) {
        String target = (bucketName == null || bucketName.isBlank()) ? bucket : bucketName;
        try {
            return minioClient.getObject(GetObjectArgs.builder()
                    .bucket(target)
                    .object(objectKey)
                    .build());
        } catch (Exception e) {
            log.error("MinIO 读取对象失败: bucket={} object={}", target, objectKey, e);
            throw new BusinessException(404, "图片不存在");
        }
    }

    public void removeObject(String objectKey) {
        removeObject(bucket, objectKey);
    }

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

    private static ImageType detectType(byte[] bytes) {
        if (bytes.length >= 3 && (bytes[0] & 0xff) == 0xff
                && (bytes[1] & 0xff) == 0xd8 && (bytes[2] & 0xff) == 0xff) {
            return new ImageType("image/jpeg", ".jpg");
        }
        if (bytes.length >= 8 && (bytes[0] & 0xff) == 0x89
                && bytes[1] == 0x50 && bytes[2] == 0x4e && bytes[3] == 0x47
                && bytes[4] == 0x0d && bytes[5] == 0x0a && bytes[6] == 0x1a && bytes[7] == 0x0a) {
            return new ImageType("image/png", ".png");
        }
        if (bytes.length >= 6
                && (ascii(bytes, 0, 6).equals("GIF87a")
                    || ascii(bytes, 0, 6).equals("GIF89a"))) {
            return new ImageType("image/gif", ".gif");
        }
        throw new BusinessException(400, "仅支持真实的 jpg/png/gif 图片");
    }

    private static void validateDecodedImage(byte[] bytes, ImageType type) {
        try (ImageInputStream input = ImageIO.createImageInputStream(new ByteArrayInputStream(bytes))) {
            if (input == null) {
                throw new BusinessException(400, "图片内容无法解析");
            }
            Iterator<ImageReader> readers = ImageIO.getImageReaders(input);
            if (!readers.hasNext()) {
                throw new BusinessException(400, "图片内容无法解析");
            }
            ImageReader reader = readers.next();
            try {
                reader.setInput(input, true, true);
                int width = reader.getWidth(0);
                int height = reader.getHeight(0);
                if (width > MAX_DIMENSION || height > MAX_DIMENSION
                        || (long) width * height > MAX_PIXELS) {
                    throw new BusinessException(400, "图片尺寸过大");
                }
                BufferedImage image = reader.read(0);
                if (image == null) {
                    throw new BusinessException(400, "图片内容无法解析");
                }
            } finally {
                reader.dispose();
            }
        } catch (BusinessException e) {
            throw e;
        } catch (Exception e) {
            throw new BusinessException(400, "图片内容无法解析");
        }
    }

    private static String ascii(byte[] bytes, int start, int length) {
        return new String(bytes, start, length, StandardCharsets.US_ASCII);
    }

    private record ImageType(String contentType, String suffix) {}
}

