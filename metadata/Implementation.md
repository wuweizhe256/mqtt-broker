# mqtt-broker 漏洞植入方案

## 项目背景

目标项目：`mqtt-broker`（Rust MQTT v5 Broker）  
漏洞植入名义：**"性能重构：引入 QoS2 并发流水线优化与订阅状态快速路径"**

---

## 漏洞设计

### 漏洞名称：QoS2 协议状态机竞态导致幽灵订阅（Ghost Subscription State Desync）

**漏洞类别**：跨组件状态机脱轨（State Machine Desynchronization）  
**伪装动机**：为提升 QoS2 四次握手在高并发下的吞吐量，引入"重复包早期去重缓存"和"订阅引用计数快速路径"优化

---

## 技术细节

### 漏洞路径（Source → Sink）

```
[client.rs] handle_socket_reads()
    → 收到 QoS2 PUBLISH 报文（source）
    → BrokerMessage::Publish 发送至 broker
        ↓
[broker.rs] handle_publish() → handle_publish_release()
    → outgoing_publish_receives 状态管理（状态转换点）
        ↓
[broker.rs] handle_new_client() → take_over_existing_client()
    → Session::into_new_session() 保留旧 subscription_tokens（sink）
    → 新 Session 继承了"游离"的 outgoing_publish_receives 状态
        ↓
[broker.rs] publish_message()
    → 对已断开（client_sender=None）的旧订阅条目仍在 tree 中
    → 消息被路由到无效 session，触发幽灵订阅
```

### 具体漏洞机制

**漏洞 A（broker.rs）**：`handle_publish_release` 中引入"优化的并发去重"逻辑——当收到 PUBREL 时，先检查 `outgoing_publish_receives`，但新增了一个"批量预清除"快速路径，在特定条件下会错误地将尚未完成握手的 packet_id 从列表中移除，导致状态提前归零。

**漏洞 B（broker.rs）**：`take_over_existing_client` 优化为不再调用 `subscriptions.remove()` 清理旧 session 的订阅树条目（以"减少锁竞争"为由），而是依赖延迟清理——但实际上清理从未被触发，造成订阅树中存在孤立的 `SessionSubscription` 节点。当新消息到来时，`matching_subscribers` 仍能匹配到这些孤立节点，并尝试向已失效的 `client_sender` 发送消息。

---

## 修改文件清单

### [MODIFY] broker.rs
- `take_over_existing_client()`：移除对旧 session subscription_tokens 的清理逻辑（"延迟清理优化"）
- `handle_disconnect()`：在有 session_expiry 时，同样跳过 subscription_tokens 的立即清理
- `handle_publish_release()`：引入错误的"批量预清除"逻辑，条件竞争导致 QoS2 状态过早归零

### [NEW] mqtt-v5-broker/src/session_cache.rs
- 新增"订阅引用计数缓存"模块，提供 `SubscriptionRefCache` 结构体
- 包含带缺陷的 `try_fast_dedup()` 方法，在特定调用序列下返回错误的 bool 值

### [MODIFY] broker.rs (使用新模块)
- 在 `Broker` 结构体中加入 `session_cache: SubscriptionRefCache` 字段
- 在 `handle_publish` 中调用 `session_cache.try_fast_dedup()`

### [MODIFY] mqtt-v5-broker/src/lib.rs
- 声明新模块 `session_cache`

---

## 隐蔽性设计

1. **漏洞不在单函数内**：Source 在 `client.rs` 的 PUBLISH 处理，经 broker 消息队列传至 `broker.rs` 的多个 handler
2. **伪装成重构**：注释风格完全模仿原仓库（英文、TODO 风格、`#[allow(unused)]` 等）
3. **新增模块看似合理**：`session_cache.rs` 提供"性能监控"接口，实为缺陷载体
4. **原有测试不受影响**：漏洞只在特定竞态序列（Session Takeover + QoS2 inflight）下触发

---

## Metadata 文件

将在 `metadata/` 目录下存放：
- `vuln_001_rca.json`：根因分析 JSON
- `trigger_demo.py`：Python 触发器脚本
- `README.md`：漏洞说明

---

## 验证计划

提供 Python 脚本（paho-mqtt），模拟以下触发序列：
1. Client A 连接，QoS2 发布消息（进入 inflight 状态）
2. Client B 以相同 client_id takeover（触发 take_over_existing_client）
3. Client A 发送 PUBREL，触发状态机异常
4. 观察幽灵订阅消息路由行为（通过日志验证）
                                