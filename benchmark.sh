#!/bin/bash
BASE="http://localhost:8080"
ROUNDS=20
EMAIL="btest_$(date +%s)@qq.com"

echo "=========================================="
echo "  城市安全隐患分析平台 - 接口性能测试"
echo "  测试轮数: ${ROUNDS} 次取平均"
echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
echo ""

bench() {
  local label="$1"
  local total=0
  local times=""
  for i in $(seq 1 $ROUNDS); do
    shift 2
    t=$(curl -s -o /dev/null -w "%{time_total}" "$@")
    times="$times $t"
  done
  local avg=$(echo "$times" | awk '{s=0; for(i=1;i<=NF;i++) s+=$i; printf "%.1f", s/NF*1000}')
  local max=$(echo "$times" | awk '{m=0; for(i=1;i<=NF;i++) if($i>m) m=$i; printf "%.1f", m*1000}')
  local min=$(echo "$times" | awk '{m=999; for(i=1;i<=NF;i++) if($i<m) m=$i; printf "%.1f", m*1000}')
  printf "  %-20s  平均: %6sms  最快: %6sms  最慢: %6sms\n" "$label" "$avg" "$min" "$max"
}

# 先拿 token
TOKEN=$(curl -s -X POST "$BASE/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"2155626284@qq.com","password":"123456"}' \
  | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

bench "发送验证码" -X POST "$BASE/api/auth/send-code" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\"}"

bench "登录" -X POST "$BASE/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"2155626284@qq.com","password":"123456"}'

bench "隐患列表(分页)" -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/hazard?current=1&size=10"

bench "隐患详情" -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/hazard/1"

echo ""
echo "========== 测试完成 =========="
