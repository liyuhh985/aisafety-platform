# -*- coding: utf-8 -*-
"""域锚覆盖率测量：现实口吻的本领域表述里，有多少条**不含**任何 DOMAIN_KEYWORDS 词。

用途：判断「模型声称 hazard 时必须由原文域锚核对」这条规则会不会误伤真隐患。
只读，不改任何东西。
"""
import io, os, sys
sys.path.insert(0, os.getcwd())
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.scope_policy import DOMAIN_KEYWORDS

# 现实口吻的本领域表述（8 大类覆盖；故意用用户会说的话，不用官方措辞）
IN_DOMAIN_USER_STYLE = [
    ("traffic", "小区门口全是摆摊的，路都走不通"),
    ("traffic", "人行道上停了一排车"),
    ("traffic", "盲道上停着电动车"),
    ("traffic", "路边的交通标志牌和护栏坏了"),
    ("traffic", "路口的信号灯不亮了"),
    ("traffic", "道路中间的护栏被撞断了"),
    ("traffic", "路上的交通标线看不清了"),
    ("traffic", "交通标线磨损掉色了"),
    ("municipal", "路上的井盖没了，晚上很危险"),
    ("municipal", "路边一滩积水，好几天了"),
    ("municipal", "路面塌下去一块"),
    ("municipal", "巷子里的路灯不亮了"),
    ("fire", "楼道里堆了很多纸箱，消防通道被堵住了"),
    ("fire", "消防通道常年被私家车占用"),
    ("fire", "消火栓打开没有水"),
    ("fire", "灭火器过期了压力表指针在红区"),
    ("building", "我们楼外墙的瓷砖掉下来了"),
    ("building", "房子墙上有很长的裂缝，还往下掉灰"),
    ("building", "楼下有人在楼顶搭了个铁皮房"),
    ("building", "楼上老是往下扔东西"),
    ("building", "外立面的墙皮一块块往下掉"),
    ("building", "旁边那栋老楼看着要塌了"),
    ("utility", "楼道里闻到很浓的煤气味"),
    ("utility", "墙上有一截裸露的电线"),
    ("utility", "配电柜的门开着，旁边全是杂物"),
    ("utility", "有人从家里拉电线出来给电动车充电"),
    ("utility", "厨房的燃气管子老化了"),
    ("construction", "工地围挡倒了一半，没有警示牌"),
    ("construction", "施工的深基坑旁边没有护栏"),
    ("construction", "小区里挖了个大坑，晚上没有灯"),
    ("elevator", "电梯把人困在里面了"),
    ("elevator", "电梯停了半个月没人修"),
    ("env_other", "楼下垃圾堆成山了，好几天没人清"),
    ("env_other", "下水道返味，臭得受不了"),
    ("municipal", "我们家楼下的窨井盖是破的"),
    ("municipal", "一下雨就积水，排水口堵了"),
    ("traffic", "有人把共享单车堆在路口"),
    ("fire", "楼道的防火门被锁死了"),
    ("building", "商铺招牌快掉下来了"),
    ("utility", "小区里的变压器一直在响"),
]

missing = []
for major, text in IN_DOMAIN_USER_STYLE:
    hits = [w for w in DOMAIN_KEYWORDS if w in text]
    if not hits:
        missing.append((major, text))

print("本领域现实口吻探针：%d 条" % len(IN_DOMAIN_USER_STYLE))
print("含域锚（DOMAIN_KEYWORDS 命中）：%d 条" % (len(IN_DOMAIN_USER_STYLE) - len(missing)))
print("不含任何域锚：%d 条" % len(missing))
print("--- 不含域锚的明细（这些会被『必须由原文域锚核对』这条规则降级）---")
for major, text in missing:
    print("  [%s] %s" % (major, text))
print()
print("--- 参考：已知越界探针的锚命中情况 ---")
OFF = ["红烧肉怎么做好吃", "今天天气怎么样", "帮我写一篇八百字的周记",
       "推荐一款性价比高的手机", "Python 列表如何去重",
       "商场里的指示牌歪了", "楼层指示牌挂得太低了",
       "Excel 表格怎么加标线", "图纸上的标线怎么画",
       "路口的指示牌歪了", "地上的标线看不清"]
for text in OFF:
    hits = [w for w in DOMAIN_KEYWORDS if w in text]
    print("  %-22s -> %s" % (text, hits or "（无）"))
