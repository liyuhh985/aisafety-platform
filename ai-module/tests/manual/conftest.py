"""手动冒烟脚本目录：默认不参与 pytest 自动收集。

本目录里的脚本需要真实环境（MySQL / 模型 API / 图片文件）才能跑通，
属于人工验证凭据，不是 CI 单测。因此用 collect_ignore_glob 挡住自动收集，
避免在没有数据库的机器上整批报错。需要跑时见 README.md 的单文件命令。
"""

collect_ignore_glob = ["*.py"]
