# Assistant Front-End Changes Outline

Companion to `2026-09-25-assistant-sse-interrupt-contract.md` (that one covers the task-confirmation event; this one covers the single-active-hazard change).

## 1. The major-category picker

| requirement | detail |
|---|---|
| "自动判断" must send an **empty or absent** `selected_major_code` | Never send `"auto"`, `"unknown"` or similar. The backend reads any non-empty value as a real major, takes it as the authoritative scope for the whole conversation, and would then block every re-lock. |
| The picker may be changed **mid-conversation** | Re-send the full conversation with the new `selected_major_code`. The backend sees a changed major as an explicit user action and re-locks. No backend call is needed to "reset" anything. |
| History does **not** need clearing when the picker changes | Nothing was locked under the old major, so the switch is clean. If a hazard *was* already locked and reported, its record already exists independently. |
| Keep the in-product rule visible | "换隐患就新开一个对话" — this is the primary path; the backend notice is only a fallback. |

## 2. New fields on the `taxonomy` event

```json
{"type": "taxonomy",
 "content": {"selected_major_code": "fire",
             "major_mismatch": false,
             "issues": [...],
             "locked_major": "fire",
             "locked_subcategory": "fire_lane_blocked",
             "suggested_major_code": "",
             "immediate_danger": false}}
```

| field | use |
|---|---|
| `locked_major` / `locked_subcategory` | Render a persistent status strip: "本对话正在记录：消防通道占用". Gives the user a way to notice they are in the wrong conversation before they get confused. |
| `suggested_major_code` | **Non-empty means the user drifted out of scope.** Render a one-tap "改报 XX" action next to the notice text. Tapping it sets the picker to that major and resends with the new `selected_major_code`. This is what turns the backend notice into an action instead of friction. |
| `immediate_danger` | Optional: a stronger visual treatment for safety guidance. |

**Timing changed, do not assume issues is non-empty.** The event used to fire only when a hazard was recognised. It now also fires when nothing was recognised but a lock exists or a major is suggested — that is exactly the out-of-scope case, and it is the case where the front end most needs `suggested_major_code`.

## 3. What the front end receives in the out-of-scope case

The notice arrives as ordinary reply text (`chunk`), and the same turn carries the structured signal in `taxonomy`. There is no question in that turn, so the message stream ends after the notice.

Notice text (from the backend, for reference — do not hard-code-match on it):

```text
（这是「消防安全」范围的对话，刚才那句更像是「市政设施」类的问题。
如果确实是这一类，建议另开一个对话并选择对应大类；如果还是「消防通道占用」的问题，直接继续补充就行。）
```

## 4. Do not do these

- **Do not decide on the front end whether the user is correcting.** The backend reads `intent=correction` from the model. "另外还有一栋危房" is an addition and must not re-lock anything.
- **Do not switch the major automatically.** Only a user action may change it (picking a different major, or tapping "改报 XX"). This is the whole point of the design.
- **Do not treat an empty `issues` as "something failed".** It is a valid outcome: the message belongs to another major, or no category could be matched yet.

## 5. Acceptance for the front end

1. Picker set to "自动判断" → the first description classifies freely and everything works as before.
2. Picker set to 消防, user writes about a manhole → the reply carries the notice **and** the UI offers "改报市政设施"; tapping it re-sends with `selected_major_code="municipal"` and the manhole is then handled normally.
3. Same conversation, user adds "旁边还有一栋危房" → the status strip still says 消防通道占用, the notice appears, and the UI does **not** silently switch.
4. Same conversation, user says "其实是消防设施坏了" → the status strip updates to 消防设施故障, with no notice.
5. The task-confirmation flow still works through the `interrupt` event (see the other document).
