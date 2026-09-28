# 特化：只做「城市基础设施隐患」实施计划

> 日期：2026-09-07
> 背景：项目当前覆盖 8 类隐患（占道/危房/消防通道/高空坠物/井盖道路/电气/施工/其他），范围过散，导致检索覆盖不足、槽位泛化、判别不稳、业务难做深。
> 目标：**深度特化为「城市基础设施隐患」**，只保留 4 类，删掉另外 4 类。

---

## 特化范围

**保留（基础设施/出行/办事属性强）**：
- `占道`
- `井盖/道路`
- `消防通道`
- `施工`

**删除（法规散/专业性强/难做深）**：
- `危房`
- `高空坠物`
- `电气`
- `其他`

---

## 涉及文件

| 文件 | 改动 |
|---|---|
| `core/assistant_graph.py` | `CATEGORIES`/`SLOT_SCHEMAS`/`CATEGORY_PRIORITY`/`_CATEGORY_KEYWORDS`/`_VISION_CATEGORY_MAP` 删掉 4 类 |
| `tests/test_multi_hazard.py` | 改引用危房/高空坠物的用例 |
| `tests/test_adaptive_slots.py` | 改引用危房的用例 |
| `tests/test_memory_store.py` | 若引用「其他」类别则调整（检查） |
| `test_orchestrator_no_hazard.py`（根目录） | 检查/调整 |

---

### Task 1: 清理 `assistant_graph.py` 的类别定义

**Files:** `core/assistant_graph.py`

- [ ] **Step 1: 改 `CATEGORIES`**（只保留 4 类）

```python
CATEGORIES = ("占道", "井盖/道路", "消防通道", "施工")
```

- [ ] **Step 2: 改 `SLOT_SCHEMAS`**（删除危房/高空坠物/电气/其他，保留 4 类）

```python
SLOT_SCHEMAS: dict[str, list[Slot]] = {
    "占道": [
        Slot("behavior", "具体是什么占道？摆摊、还是车辆停放？"),
        Slot("persistence", "是长期占压还是临时停放？"),
        Slot("blocked", "是完全堵死还是部分占用？"),
    ],
    "消防通道": [
        Slot("blocker", "被什么东西占用了？"),
        Slot("persistence", "是长期还是临时？"),
        Slot("impact", "是否影响消防车或人员通行？", critical=False),
    ],
    "井盖/道路": [
        Slot("defect", "井盖是缺失、破损还是松动？"),
        Slot("traffic", "是否影响行人或车辆通行？"),
    ],
    "施工": [
        Slot("site", "施工区域是否做了围挡？"),
        Slot("safety", "有无安全警示或防护？"),
        Slot("impact", "是否影响行人或车辆通行？", critical=False),
    ],
}
```

- [ ] **Step 3: 改 `CATEGORY_PRIORITY`**（删 4 类，重新排）

```python
CATEGORY_PRIORITY = {
    "消防通道": 1, "施工": 4, "占道": 5, "井盖/道路": 6,
}
```

- [ ] **Step 4: 改 `_CATEGORY_KEYWORDS`**（删 4 类）

```python
_CATEGORY_KEYWORDS = {
    "占道": ("占道", "摆摊", "摊位", "车占", "停车", "挡盲道", "占盲道", "盲道"),
    "消防通道": ("消防通道", "消防车", "消防", "救援通道"),
    "井盖/道路": ("井盖", "窨井", "路面", "坑", "破损", "塌陷"),
    "施工": ("施工", "工地", "开挖", "脚手架", "围挡"),
}
```

- [ ] **Step 5: 改 `_VISION_CATEGORY_MAP`**（删"建筑结构→危房"、"高空坠物→高空坠物"、"用电安全→电气"、"电气→电气"，保留基础设施相关的）

```python
_VISION_CATEGORY_MAP = {
    "建筑施工": "施工", "占道经营": "占道", "道路交通": "井盖/道路",
    "消防": "消防通道", "施工": "施工", "占道": "占道",
}
```

- [ ] **Step 6: 跑 AST + 导入检查**

Run: `cd E:\java\newProject\ai-module; python -c "import ast; ast.parse(open('core/assistant_graph.py',encoding='utf-8').read()); print('AST OK')"; python -c "from core.assistant_graph import CATEGORIES; print(CATEGORIES)"`
Expected: `AST OK` 且 `CATEGORIES == ('占道','井盖/道路','消防通道','施工')`

- [ ] **Step 7: 提交**

```bash
cd E:\java\newProject
git add ai-module/core/assistant_graph.py
git commit -m "refactor(categories): specialize to urban infrastructure (drop 危房/高空坠物/电气/其他)"
```

---

### Task 2: 清理测试中的旧类别引用

**Files:** `tests/test_multi_hazard.py`、`tests/test_adaptive_slots.py`、`tests/test_memory_store.py`（检查）、`test_orchestrator_no_hazard.py`（根目录）

- [ ] **Step 1: `test_multi_hazard.py` 改危房/高空坠物引用**

`test_merge_categories_dedupe_and_sort`（L26-27）用了危房，改成用保留类别：
```python
def test_merge_categories_dedupe_and_sort():
    merged = ag._merge_categories(["占道", "消防通道"], ["占道", "井盖/道路"])
    assert merged[0] == "消防通道"      # 优先级最小的保留类
    assert merged.count("占道") == 1
    assert merged[-1] == "占道"
```
`test_critical_flag_present`（L32）用了高空坠物，改成用消防通道（impact critical=False）：
```python
def test_critical_flag_present():
    slots = ag.SLOT_SCHEMAS["消防通道"]
    d = {s.key: s.critical for s in slots}
    assert d["blocker"] is True and d["persistence"] is True and d["impact"] is False
```

- [ ] **Step 2: `test_adaptive_slots.py` 改危房引用**

`test_infer_categories_weifang_no_llm`、`test_pick_keyword_category` 用了危房，改成用保留类（占道/井盖道路）：
```python
def test_infer_categories_zhandao_no_llm(monkeypatch):
    monkeypatch.setattr(ag, "_llm_classify", lambda t: (_ for _ in ()).throw(AssertionError("清晰场景不应调 LLM")))
    cats = _infer_categories("长期占着盲道完全堵死")
    assert "占道" in cats

def test_pick_keyword_category():
    kw = _pick_keyword("占道", {"blocked": "完全堵死"})
    assert "占道" in kw and "完全堵死" in kw
```

- [ ] **Step 3: `test_memory_store.py` 检查**

若第 33 行 `"description": "这个描述-xxx"` 里的类别是抽象描述，不涉及具体被删类别，保留；若引用"电气/其他"，删掉或改。

- [ ] **Step 4: `test_orchestrator_no_hazard.py`（根目录）检查**

读它，若引用危房等被删类别，改成保留类或调整。

- [ ] **Step 5: 跑全量测试**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/test_multi_hazard.py tests/test_adaptive_slots.py tests/test_memory_store.py -q`
Expected: 全绿（改掉引用旧类的用例后）

- [ ] **Step 6: 提交**

```bash
cd E:\java\newProject
git add ai-module/tests/ ai-module/test_orchestrator_no_hazard.py
git commit -m "test(categories): update specs to urban infrastructure"
```

---

## 自检清单

- [ ] `CATEGORIES` 只剩占道/井盖道路/消防通道/施工。
- [ ] 四个定义块（CATEGORIES/SLOT_SCHEMAS/CATEGORY_PRIORITY/_CATEGORY_KEYWORDS/_VISION_CATEGORY_MAP）同步删除 4 类。
- [ ] `_infer_categories`/`_find_negated`/`_detect_other_cats` 等遍历 CATEGORIES 的自动跟随新集合。
- [ ] 测试里旧类别引用改成保留类。
- [ ] 全量测试通过。
- [ ] 后续业务（AI 上报→整改闭环）聚焦这 4 类基础设施。