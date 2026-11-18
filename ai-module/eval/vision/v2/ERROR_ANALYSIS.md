# 视觉评估错误分析

> 标签来源：model_consensus。该文档分析模型共识伪标签下的跨模型错误，不代表人工 gold。
> annotation_mode: `model_consensus`
> test_total: 80

### Baseline

| bucket | count | example files |
|---|---:|---|
| false_positive | 12 | NEGVEH08.jpg, NEGMAN01.jpg, NEGROA02.jpg, NEGILL04.jpg, NEGSTR07.jpg |
| false_negative | 2 | ELE0006.jpg, ELE0005.jpg |
| major_confusion | 2 | WAL0020.jpg, DIS0079.jpg |
| invalid_output | 0 | - |
| review_required | 6 | WAL0020.jpg, NEGVEH08.jpg, NEGROA02.jpg, NEGILL04.jpg, NEGGAS01.jpg |

### Final

| bucket | count | example files |
|---|---:|---|
| false_positive | 3 | NEGMAN01.jpg, NEGGAS08.jpg, NEGELE03.jpg |
| false_negative | 3 | WAL0020.jpg, ELE0006.jpg, ELE0005.jpg |
| major_confusion | 1 | DIS0079.jpg |
| invalid_output | 0 | - |
| review_required | 2 | NEGILL04.jpg, NEGDIS08.jpg |

## 解读边界

- 错误桶用于定位模型行为，不代表标签一定正确。
- 由于评估集本身是模型共识伪标签，错误分析只能作为诊断证据。
- 低置信度样本应进入人工复核，不应自动形成正式工单。

## 典型错误案例

### 1. NEGMAN01：把施工动作误判成施工隐患

画面是工作人员用井盖钩开启一个完好井盖。baseline 和 final 都判成 `construction/no_warning`，属于硬负样本误报。模型把“打开了井盖”这个动作理解成“缺少警示”，但没有确认井盖本身是否破损或是否真的存在施工隐患。

面试讲法：这不是“模型没看见井盖”，而是模型把**动作风险**和**设施状态风险**混为一谈。

### 2. WAL0020：轻微外立面损伤被 final prompt 过滤掉

画面中围墙端部抹灰破损、墙皮脱落。baseline 判成 `environment_other/other` 大类混淆；final 直接判无隐患，成为漏报。final 的精度优先规则在减少误报的同时，对局部、轻微的外立面损伤更保守。

面试讲法：FPR 降低不是免费的。final 通过对不确定场景不报警降低了误报，但也牺牲了部分真实弱隐患的召回。

### 3. DIS0079：场景语境压过了设施类型

画面是配电设备旁地面存在杂乱插排和私拉电线。baseline 和 final 都判成 `construction/temporary_power`，但 gold 是 `utility/wire_fault`。模型被施工/设备场景带偏，忽略了“线路私拉乱接”的电气设施属性。

面试讲法：这说明大类分类不是简单的二分类后处理，同一视觉证据可能落在不同业务大类，需要明确“按设施本体还是按使用场景分类”。

## 错误分析结论

- 主要误报类型：把“施工/维护动作”当成隐患证据。
- 主要漏报类型：局部、轻微、需要领域知识才能确认的设施损伤。
- 主要混淆：`construction/temporary_power` 与 `utility/wire_fault`。
- 这些问题的产品含义是：低置信度必须转人工复核，不能直接自动建单。
