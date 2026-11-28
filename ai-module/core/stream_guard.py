"""流式约束执行器：让受限产物既能逐句流出去，又不丢「格式底线由代码保证」。

为什么不必「先缓冲整篇再吐」：
  `？` 是句级特征（问号一定在句末），`###` 是行级特征（标题一定在行首）。
  两者都不需要看到整篇就能判定，所以约束可以放在流上做。

三个部件：
  drain         纯函数：吃进缓冲，吐出「已经能判定的整句」和剩余缓冲
  guard_stream  生成器：吃 token 流，按句/行过滤后逐块放出
  enforce       非流式：等价于把整段喂给 guard_stream 再拼起来

两个必须守住的点：
  1. 问号可能出现在句子中间（「这样对吗？请照做。」），所以必须等到句末符才放行，
     不能「看着目前没有就发」—— 代价是延迟一句话，这是必要的。
  2. 丢句是安全的，前提是上层有兜底（例如 emergency_guidance 的必含要点覆盖核对，
     覆盖不到会前置该类型的兜底句）。两个机制必须咬合，别单独拆掉一边。
"""

SENTENCE_ENDS = "。！!；;？?\n"
QUESTION_MARKS = ("？", "?")

QUESTION_DROP = "drop"      # 含问号的整句丢掉
QUESTION_DROP_LIKE = "drop_like"  # 含问号或明显疑问句式的整句丢掉
QUESTION_STRIP = "strip"    # 只去掉问号字符，句子留下
QUESTION_KEEP = "keep"      # 原样保留

_QUESTION_POLICIES = (QUESTION_DROP, QUESTION_DROP_LIKE, QUESTION_STRIP, QUESTION_KEEP)


def question_limiter(limit: int = 1):
    """返回「最多放行 limit 个问句」的判定函数：之后的问句只去掉问号、不丢整句。

    为什么需要它：初步报告要在同一段话里既给判断、又给一个追问（决策 b），
    而「一轮最多一个问句」是硬约束。计数必须跨句，所以放进闭包。
    为什么之后的问句只是去问号而不是丢整句：报告里「仍需确认」那段是内容，
    丢整句就等于制造误判（与这一档原来的 QUESTION_STRIP 取舍一致）。
    """
    remaining = [max(0, int(limit))]

    def policy(sentence: str) -> str:
        if not any(mark in sentence for mark in QUESTION_MARKS):
            return sentence
        if remaining[0] > 0:
            remaining[0] -= 1
            return sentence
        for mark in QUESTION_MARKS:
            sentence = sentence.replace(mark, "")
        return sentence

    return policy

_BLANK_CHARS = " \t"
_MAX_HEADING_HASHES = 6     # 对齐 Markdown 的 #{1,6}


def _heading_prefix_len(buf: str, start: int, final: bool):
    """行首 Markdown 井号前缀的长度（对齐 ^[ \\t]*#{1,6}[ \\t]*）。

    返回 (前缀长度, 是否要等更多输入)。只有「还不能判断」时才要等：
    行首只看到空格、或者井号还没结束 —— 多等几个字符，代价可以忽略。
    """
    n = len(buf)
    i = start
    while i < n and buf[i] in _BLANK_CHARS:
        i += 1
    if i >= n:
        return 0, not final          # 只有空格：后面可能跟着井号
    if buf[i] != "#":
        return 0, False
    hashes = i
    while hashes < n and buf[hashes] == "#" and hashes - i < _MAX_HEADING_HASHES:
        hashes += 1
    if hashes >= n and not final:
        return 0, True               # 井号还没结束（可能是 #### 的前半段）
    end = hashes
    while end < n and buf[end] in _BLANK_CHARS:
        end += 1
    return end - start, False


_QUESTION_START_WORDS = ("请问", "是否", "能不能", "可否", "要不要", "有没有", "是不是")


def _looks_like_question(sentence: str) -> bool:
    text = str(sentence or "").strip()
    if any(mark in text for mark in QUESTION_MARKS):
        return True
    core = text.rstrip("。！!；;\n ")
    if core.endswith(("吗", "呢")):
        return True
    return any(text.startswith(word) for word in _QUESTION_START_WORDS)


def _apply_questions(sentence: str, questions) -> str:
    """按策略处理一个整句里的问号。返回空串表示这一句被丢掉。

    questions 可以是三个字符串策略之一，也可以是 question_limiter() 返回的可调用对象 ——
    「一轮最多一个问句」要跨句计数，而 drain 本身是无状态的，所以计数放在闭包里。
    """
    if callable(questions):
        return questions(sentence)
    if questions == QUESTION_KEEP:
        return sentence
    if questions == QUESTION_STRIP:
        for mark in QUESTION_MARKS:
            sentence = sentence.replace(mark, "")
        return sentence
    if questions == QUESTION_DROP:
        # 问号不是排版问题，是「系统在问用户」的行为问题 —— 整句丢掉
        if any(mark in sentence for mark in QUESTION_MARKS):
            return ""
        return sentence
    if questions == QUESTION_DROP_LIKE:
        return "" if _looks_like_question(sentence) else sentence
    raise ValueError("未知的问号策略：%r（可选 %r）" % (questions, _QUESTION_POLICIES))


def drain(buf: str, line_start: bool, *, strip_headings: bool = True,
          questions: str = QUESTION_DROP, final: bool = False):
    """把缓冲里已经能判定的部分处理掉。

    返回 (chunks, rest, rest_line_start)。
    - 只在遇到句末符时放行整句；没有句末符的部分留在 rest —— 这就是「延迟一句话」
    - 行首的井号前缀零延迟剥掉，不必等整行
    - final=True：把剩余部分也当作最后一句判定，此时 rest 必为空
    """
    chunks = []
    i = 0
    n = len(buf)
    while i < n:
        if line_start and strip_headings:
            prefix_len, need_more = _heading_prefix_len(buf, i, final)
            if need_more:
                break
            if prefix_len:
                i += prefix_len
                if i >= n:
                    break
            line_start = False
        end = i
        while end < n and buf[end] not in SENTENCE_ENDS:
            end += 1
        if end >= n:
            if not final:
                break
            piece = _apply_questions(buf[i:], questions)
            if piece:
                chunks.append(piece)
            i = n
            break
        piece = _apply_questions(buf[i:end + 1], questions)
        if piece:
            chunks.append(piece)
        line_start = buf[end] == "\n"
        i = end + 1
    return chunks, buf[i:], line_start


def guard_stream(tokens, *, strip_headings: bool = True,
                 questions: str = QUESTION_DROP):
    """吃 token 流，按句/行过滤后逐块放出。

    首块不必等整篇生成完：一句到齐就放一句。句子边界被 token 切开的，
    会先攒着 —— 判定需要的信息到齐才放行。
    """
    buf = ""
    line_start = True
    for token in tokens:
        if not token:
            continue
        buf += token
        chunks, buf, line_start = drain(
            buf, line_start, strip_headings=strip_headings,
            questions=questions, final=False)
        for chunk in chunks:
            yield chunk
    chunks, buf, line_start = drain(
        buf, line_start, strip_headings=strip_headings,
        questions=questions, final=True)
    for chunk in chunks:
        yield chunk


def enforce(text: str, *, strip_headings: bool = True,
            questions: str = QUESTION_DROP) -> str:
    """非流式等价物：把整段一次性喂给 guard_stream 再拼起来。

    注意不额外 strip()：它必须和流式输出的拼接结果逐字一致，
    需要去掉首尾空白的调用方自己 strip。
    """
    return "".join(guard_stream([text], strip_headings=strip_headings,
                                questions=questions))