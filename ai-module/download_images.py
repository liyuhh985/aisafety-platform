"""
批量下载安全隐患图片。
来源：各地政府隐患曝光页面（遂宁、黎川、成都等）。
"""
import os
import requests

IMAGE_URLS = [
    # ====== 遂宁经开区 - 在建项目安全隐患曝光 (2026) ======
    ("suining_01_tunnel_dark", "https://snjkq.suining.gov.cn/UploadFiles/2026/05/16/68cad4aa-84e2-4d36-8554-e8fe4a7a947e.png"),
    ("suining_02_power_box", "https://snjkq.suining.gov.cn/UploadFiles/2026/05/16/aa477a09-6a5d-4bf3-9d67-65d99e8f0941.png"),
    ("suining_03_no_guardrail", "https://snjkq.suining.gov.cn/UploadFiles/2026/05/16/a2939bf9-a1c3-4cb7-b942-91a779916510.png"),
    ("suining_04_edge_gap", "https://snjkq.suining.gov.cn/UploadFiles/2026/05/16/a5e1277a-71c8-4389-a28d-ff0f49c0c17b.png"),
    ("suining_05_lighting_low", "https://snjkq.suining.gov.cn/UploadFiles/2026/05/16/b8b80882-c7b3-40cf-94ce-13d3afae4ac7.png"),
    ("suining_06_belt_issue", "https://snjkq.suining.gov.cn/UploadFiles/2026/05/16/55973618-eda8-4aae-b141-432d1cb56c96.png"),
    ("suining_07_no_fence", "https://snjkq.suining.gov.cn/UploadFiles/2026/05/16/670141ee-7d20-4272-9895-2204837b3ff7.png"),
    # ====== 遂宁河东新区 - 建筑工地隐患 (2026) ======
    ("suining_08_construction", "https://hdxq.suining.gov.cn/UploadFiles/2026/03/16/74d748cf-f502-4827-a2a2-acdf8e5c8676.jpeg"),
    ("suining_09_scaffold", "https://hdxq.suining.gov.cn/UploadFiles/2026/03/16/3f6ce798-8092-4a03-8d86-a00b9d98f27a.png"),
    ("suining_10_fire_hazard", "https://hdxq.suining.gov.cn/UploadFiles/2026/03/16/e82435fa-520a-46ba-afe2-ebb0c937b8d0.png"),
    ("suining_11_hole_open", "https://hdxq.suining.gov.cn/UploadFiles/2026/03/16/81699713-8f7b-443b-b443-a23b7cd8543d.png"),
    # ====== 黎川县 - 小区飞线充电/消防通道 (2024) ======
    ("lichuan_01_parking_chaos", "https://www.jxlcx.gov.cn/picture/0/138371cd3149428291bca3d31f49a72e.png"),
    ("lichuan_02_flying_wire", "https://www.jxlcx.gov.cn/picture/0/5b696770ea87470281190eb0ff2d42d3.png"),
    ("lichuan_03_fire_lane_blocked", "https://www.jxlcx.gov.cn/picture/0/4095d6ee5f2e4fa48400816cec0a9598.png"),
]

DOWNLOAD_DIR = "test_images"


def download_all():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    for filename, url in IMAGE_URLS:
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        if os.path.exists(filepath):
            print(f"[SKIP] {filename}")
            continue
        try:
            resp = requests.get(url, timeout=30,
                                headers={"User-Agent": "Mozilla/5.0 (compatible; SafetyBot/1.0)"})
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(resp.content)
            print(f"[OK] {filename} ({len(resp.content)} bytes)")
        except Exception as e:
            print(f"[FAIL] {filename}: {e}")


if __name__ == "__main__":
    download_all()
