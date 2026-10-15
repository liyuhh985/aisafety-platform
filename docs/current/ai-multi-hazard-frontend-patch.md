# 前端补丁：多条隐患 + 大类集合锁定（多选 / 上锁 / 会话内不能再换大类）

> 状态：current
> 最后核对：2026-10-14
> 适用文件：`HomeView.vue`（会话页）
> **依赖**：这批后端改动（`7d59ba5`）已改完并通过全部单测；**上线状态以线上为准** —— 前端联调前先确认云端 Python 已是该提交，否则大类锁定行为会与本文不一致。
> 一句话：后端现在**一条会话最多同时跟 3 条隐患**，且锁定的是**大类集合**。集合一旦锁定，
> **谁都改不了**（模型改不了、前端中途改选也会被后端忽略）—— 要换大类只能**新开一个对话**。

## 0. 现在的行为（先看这段，改起来不容易搞错）

| 时机 | 会发生什么 |
|------|-----------|
| 第 1 轮 | 前端选的大类（**可多选**）就是锁定集合；前端没选，则由模型按第一句话判定 —— **一句话涉及几个大类就锁几个** |
| 之后每轮 | 集合**不变**。用户口头说别的大类 → 后端只回一句通知，不改锁；模型自己判出别的大类也改不了 |
| 集合内换小类 | 只有用户**明确纠正**（"不是井盖，是路灯杆"）才换；不是纠正的（"旁边还有根路灯杆"）会作为**第二条隐患**记下来，追问时两条一起问 |
| 追问 | 多条隐患时后端把问句拼成**一句并列的**：「还想确认两件事：①…②…」，每条只问一个点 |

## 1. 大类选择器改多选（最多 3 个）

- 允许选 1~3 个大类（与后端 `MAX_ACTIVE_MAJORS = 3` 一致）。
- 「自动判断」仍是默认，必须发**空值**（不能发 `auto` / `unknown`）。
- 发送时把选中的 code 用**英文逗号**拼进原来那个字段，**不要**新增字段：

```js
// 单选时行为与现在完全一致；多选就是 fire,municipal
const majorCode = selectedMajorCodes.value.join(',')
if (majorCode) fd.append('selected_major_code', majorCode)
```

  Java 那一层不用改（原样转发字符串）。

## 2. 锁定后，选择器**硬上锁**（一直到这次对话结束）

- 判据：SSE `taxonomy` 事件里的 `locked_majors` **非空数组** = 已锁定。

```js
} else if (event.type === 'taxonomy') {
  const t = event.content || {}
  if (Array.isArray(t.locked_majors) && t.locked_majors.length) {
    majorLocked.value = true        // 之后一直为 true，直到新开对话
  }
}
```

- 上锁后的 UI：
  - 选择器**整体禁用**（置灰、点开也没得选）—— 不要只灰掉其它选项而留着"自动判断"；
  - 展示已锁定的大类（`locked_majors` → 中文名），固定一句提示：
    「大类已锁定（消防、市政）。要换大类请**新开一个对话**。」
  - 本次对话里**不再出现任何就地切换大类的入口**（下一节）。
- `majorLocked` 只在**新开对话**时复位（换 `session_id` + 清空消息）。
- 为什么必须做：**后端已经跟着硬锁了** —— 就算界面漏了、用户还能点，中途改选也**不生效**（后端会忽略并只留日志），
  用户只会觉得"点了没反应"。这一步是为了别让用户白点。

## 3. 「改报 XX」入口的语义要改（新界面若保留它）

> 现状（据 10/13 13:51 那次构建的线上产物 `/var/www/safety-platform/assets/HomeView-CM2I5ZIf.js`
> 与源码 `/home/ubuntu/aisafety-platform-frontend/src/views/HomeView.vue`）：**跨大类越界时**
> 会渲染一条「改报 XX」行动条（`suggested_major_code` 非空时出现），点了**就地切大类并重发上一句**。
> 现在这么做**没用**（后端忽略中途改选）。新界面若保留这个入口，按下面改；若干脆不做，跳过本节。

改成"**新开一个对话**"：

```js
async function switchByNewSession(targetMajorCode, msg) {
  const lastUserText = /* 该条助手消息前面最近的那条用户文本 */
  startNewSession()                              // 换 session_id（后端的锁随新会话重置）
  selectedMajorCodes.value = [targetMajorCode]   // 新会话的选择器是解锁的
  await executeStreamChat(lastUserText, null, null, false)
}
```

## 4. 状态条（可选，但建议做）

- `taxonomy.issues[]` 一次最多 3 条，元素形如 `{major_code, subcategory_code, ...}`；
- 主显示仍用 `locked_major` / `locked_subcategory`（= 焦点那一条，语义没变）；
- 建议加一句「已记录 N 件」，或把 N 条都列出来。

## 5. 契约速查（后端已经在发 / 已经在收）

| 字段 | 位置 | 说明 |
|------|------|------|
| `selected_major_code` | 请求 | 多个 code 用英文逗号拼；空 = 自动判断。**只在会话第一次判定时有效**，锁定后再发不生效 |
| `locked_major` | `taxonomy` 事件 | 集合的第一项（兼容旧前端） |
| `locked_majors` | `taxonomy` 事件 | 锁定的大类集合，**判"要不要上锁"看它** |
| `locked_subcategory` | `taxonomy` 事件 | 焦点那一条的小类 |
| `suggested_major_code` | `taxonomy` 事件 | 越界时模型认为的大类（用来渲染"改报"） |
| `issues[]` | `taxonomy` 事件 | 本轮活动隐患，最多 3 条，同属 `locked_majors` |

## 6. 验收清单

1. 不选大类直接聊，第一句话里有两个大类 → 追问把两条都点到（「还想确认两件事：①…②…」）。
2. 多选两个大类，但这句只讲其中一个 → 只跟那一条，不硬凑。
3. 对话进行中 → 选择器置灰，点不到切换。
4. 锁定后即使把 `selected_major_code` 硬发成别的大类 → **后端不改锁**（可以拿这条验证"忽略"生效）。
5. 「改报」→ 新开会话 + 选中该类 + 带回原话，能改成功。
6. 单条隐患的会话 → 与改动前**完全一致**。
