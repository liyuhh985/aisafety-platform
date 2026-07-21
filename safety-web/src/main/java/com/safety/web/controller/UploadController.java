package com.safety.web.controller;

import com.safety.common.result.R;
import com.safety.pojo.vo.FileUploadVO;
import com.safety.service.service.FileUploadService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/upload")
@RequiredArgsConstructor
public class UploadController {

    private final FileUploadService fileUploadService;

    @PostMapping("/image")
    public R<FileUploadVO> uploadImage(@RequestParam("file") MultipartFile file) {
        return R.ok(fileUploadService.upload(file));
    }
}
