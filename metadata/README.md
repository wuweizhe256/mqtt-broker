# mqtt-broker 漏洞数据集说明

## 项目信息

- **项目名称**：mqtt-broker（MQTT v5 Broker，Rust 实现）
- **漏洞编号**：VUL-001
- **植入日期**：2026-04-02
- **植入动机（伪装）**：QoS2 并发流水线性能优化重构

## 数据集用途

本目录仅用于大创项目的漏洞检测测试数据集构建，不对外发布，不影响原始开源仓库。
所有漏洞均为人工植入的逻辑缺陷，不包含任何具有实际破坏性的攻击代码。

## 目录结构

```
metadata/
├── README.md           # 本文件
├── vuln_001_rca.json   # VUL-001 根因分析（真值标签）
└── trigger_demo.py     # Python 触发器脚本
```

## 关联源文件

| 文件 | 角色 |
|------|------|
| `mqtt-v5-broker/src/session_cache.rs` | 新增模块，初始化缺陷（threshold=1） |
| `mqtt-v5-broker/src/broker.rs`        | handle_publish_release 快速路径跳过清理 |
| `mqtt-v5-broker/src/lib.rs`           | 声明新模块 |
