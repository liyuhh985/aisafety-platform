# 手动冒烟脚本（不参与 CI）

> 状态：current
> 最后核对：2026-10-11

这些脚本**不是自动化单测**：它们需要真实环境（MySQL / 模型 API / 本地图片）才能跑通。
它们原先散在 `ai-module/` 根目录，和 `tests/` 里的单测混在一起；又因为路径不在
`testpaths` 里，实际上既不会被 CI 跑到、也没有任何地方引用。

移到这里的目的：**保留"当时手工验过"的凭据**，同时让 `pytest tests` 的行为确定。

| 脚本 | 外部依赖 | 怎么跑 |
|------|----------|--------|
| `test_agent_cancellation.py` | 无（HTTP 被 mock） | `cd ai-module && python -m pytest tests/manual/test_agent_cancellation.py` |
| `test_assistant_tools.py` | 真实 MySQL（`tb_hazard_case` / `tb_regulation`） | `cd ai-module && python -m pytest tests/manual/test_assistant_tools.py` |
| `test_vision.py` | MiMo 模型 API 可达 | `cd ai-module && python tests/manual/test_vision.py [图片路径]` |

## 已删除的脚本

- `test_server_upload_validation.py`：它断言 `/api/ai` 上传会对超大图片返回 413。
  该像素上限校验现在已经不在 `server.py` 里（`_save_upload` 只负责落盘），
  脚本长期处于"收集不到、也没人跑"的状态。保留一个断言已删除行为的脚本
  比删掉它更危险，所以直接删除。

## 收集规则

`conftest.py` 里的 `collect_ignore_glob = ["*.py"]` 只挡 **自动收集**；
显式把文件路径交给 pytest（上表命令）仍然会执行。
