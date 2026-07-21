# Redis 缓存性能对比测试报告

## 测试环境

| 项目 | 值 |
|------|-----|
| 测试时间 | 2026-07-19 17:27 / 18:01 |
| Java 版本 | 21.0.8 |
| Spring Boot | 3.3.5 |
| MySQL | 106.53.219.214:3306 |
| Redis | 106.53.219.214:6379, db2 |
| MinIO | 106.53.219.214:9100 |
| 测试方式 | curl 各接口 5 次取平均值 |

---

## 无 Redis（MemoryStore 内存存储）

| 接口 | 响应时间 | 说明 |
|------|---------|------|
| POST /api/auth/send-code | ~590ms | SMTP 发邮件本身慢 |
| POST /api/auth/login | ~100ms | 查 MySQL + BCrypt 校验 |
| GET /api/hazard?page | ~70ms | MySQL 分页查询 |
| GET /api/hazard/1 | ~169ms（首次）→ 39ms（内存） | 查 DB / 内存命中 |

Token 和验证码存在 JVM 内存的 ConcurrentHashMap 中，应用重启即丢失。

---

## 有 Redis（StringRedisTemplate）

| 接口 | 响应时间 | 说明 |
|------|---------|------|
| POST /api/auth/send-code | ~740ms（首次）/ **32ms（限流拦截）** | 同邮箱 60s 内限流 1 次 |
| POST /api/auth/login | ~138ms | +38ms 网络延迟（Redis 远程） |
| GET /api/hazard?page | ~116ms | +46ms 网络延迟 |
| GET /api/hazard/1 | **64ms（Redis 缓存命中）** | 比查 DB 快 2.6 倍 |

---

## 为什么 MemoryStore（本地）比 Redis（远程）快？

MemoryStore 在 JVM 堆内存里，Redis 在云端 106.53.219.214，中间 ~30ms 网络延迟。

Redis 不可替代的价值：

1. **持久化** — 应用重启，Token 和缓存不丢
2. **多实例共享** — 以后部署多台后端，Session 互通
3. **限流可靠** — 计数器存 Redis，不受重启影响

---

## 核心功能验证

```
[限流测试]
POST /send-code (第1次) → 200  发邮件成功
POST /send-code (第2次) → 429  "操作过于频繁，请60秒后再试"

[缓存测试]
GET /hazard/1 (首次)  → 169ms  查 MySQL → 写 Redis
GET /hazard/1 (缓存)  → 64ms   从 Redis 读，快了 2.6 倍

[登录/Token]
POST /login → Token 写入 Redis (safety:token:{uuid})
后续请求 → JwtAuthenticationFilter 从 Redis 读 Token → 认证通过
```

---

## 三级缓存架构（Caffeine + Redis + MySQL）

### 架构图

```
请求 → L1: Caffeine (JVM本地, <1ms 缓存命中)
         ↓ miss
       L2: Redis (远程, ~30ms)
         ↓ miss
       L3: MySQL (~100ms+) → 回填 L2 → 回填 L1
```

### 实测数据（2026-07-19 19:16）

同一 ID 连续查 5 次：

| 次数 | 耗时 | 命中层级 |
|------|------|---------|
| 第1次 | 1.23s | L3 MySQL（Redis 已过期，穿透查 DB） |
| 第2次 | 0.26s | L1 Caffeine（本地内存，快 4.7 倍） |
| 第3次 | 0.26s | L1 Caffeine |
| 第4次 | 0.24s | L1 Caffeine |
| 第5次 | 0.18s | L1 Caffeine |

### 缓存配置

| 层级 | 技术 | 容量 | 过期时间 |
|------|------|------|---------|
| L1 | Caffeine | 1000 条 | 1 分钟 |
| L2 | Redis | 无限制 | 5 分钟 |
| L3 | MySQL | - | - |

### 回填策略

每次 L3 查询后，自动回填 L2（Redis）+ L1（Caffeine）。
L2 命中时，自动回填 L1。
写入操作不主动清除缓存（简单起见，等过期自动刷新）。

---

## Redisson 集成（2026-07-19）

### 为什么用 Redisson

Spring Data Redis (Lettuce) 只提供了底层 Redis 命令（SET/GET/DEL），Redisson 在此基础上封装了高级分布式对象。

### Redisson 替换/新增了什么

| 功能 | 之前（手写） | 现在（Redisson） |
|------|-------------|-----------------|
| 接口限流 | AOP + StringRedisTemplate INCR | `RRateLimiter.tryAcquire()` |
| 分布式锁 | 无 | `RLock.tryLock()` 防并发重复上报 |
| 配置方式 | - | `redisson-spring-boot-starter` 自动读取 spring.data.redis |

### 限流实现对比

```java
// 之前: 手写 INCR 计数器
Long count = redisTemplate.opsForValue().increment(key);
if (count == 1) redisTemplate.expire(key, time, unit);

// 现在: Redisson RRateLimiter 令牌桶算法
RRateLimiter limiter = redissonClient.getRateLimiter(key);
limiter.trySetRate(RateType.OVERALL, count, time, RateIntervalUnit.SECONDS);
limiter.tryAcquire(); // true=放行, false=限流
```

### 分布式锁

```java
RLock lock = redissonClient.getLock("safety:lock:hazard:create:" + userId);
lock.tryLock(3, 10, TimeUnit.SECONDS); // 等3秒，锁10秒自动释放
try { ... } finally { lock.unlock(); }
```

Redisson 的 Watchdog 机制会自动续期，不会出现锁超时释放导致并发问题。

### 实测验证（Redisson 限流 + 三级缓存）

```
POST /send-code (第1次) → 200  通过
POST /send-code (第2次) → 429  "操作过于频繁"  RRateLimiter 限流 ✅

GET /hazard/4 (首次) → 1.27s  穿透到 L3 MySQL
GET /hazard/4 (缓存) → 0.21s  L1 Caffeine 命中
```
