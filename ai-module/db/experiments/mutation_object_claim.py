# -*- coding: utf-8 -*-
"""变异实验：把否决条件改成恒 False，新用例必须复现漏放（否则测试是空的）。"""
import hashlib, io, os, subprocess, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
PATH = os.path.join("core", "scope_policy.py")
original = open(PATH, "rb").read()
hash_before = hashlib.sha256(original).hexdigest()
text = original.decode("utf-8")
old = "        if unbacked:"
assert text.count(old) == 1
mutated = text.replace(old, "        if False and unbacked:", 1)
try:
    open(PATH, "w", encoding="utf-8", newline="\n").write(mutated)
    proc = subprocess.run([sys.executable, "-m", "pytest", "tests/test_scope_policy.py",
                           "-k", "unbacked or catch_all or object_claim or evidence",
                           "-q"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print((proc.stdout or "")[-1200:])
    print("变异态退出码=%d" % proc.returncode)
finally:
    open(PATH, "wb").write(original)
    assert hashlib.sha256(open(PATH, "rb").read()).hexdigest() == hash_before, "restore failed!"
    print("已恢复，sha=%s" % hash_before[:8])
