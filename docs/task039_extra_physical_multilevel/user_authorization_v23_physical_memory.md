# 用户授权 V23：原始 B 的物理内存压力策略

本文件逐字保存本轮用户明确授权，并作为旧 V22 一次性容量试验之后的独立
执行边界。旧 V21/V22 profile、checker、ledger、raw evidence 与负结果保持
不变；本轮使用独立 V23 profile、输入、ledger 和 `response_v24`。

## 用户授权原文

『那更改一下规则，除非计算达到物理内存，否则一定要给我算完』

## 适用范围与限制

- 只对同一个 990-cell original B 做一次 fresh 试验；不启动 A/C/notch，
  不改网格、p/mode/ordering/PC/BLR 或数值算法。
- 本授权取代 V22 的固定 6 GiB inventory、8 GiB tree、1 GiB temporary
  pool 与冻结 continuation ceiling 作为本次新试验的硬资源门槛；这些旧
  合同仍仅作为历史证据，不被改写。
- 新策略以 Linux effective RAM/cgroup 和实时 `MemAvailable`、真实 process
  tree RSS、zero-swap、watchdog 清场和数值/物理 Gate 为准；只保留可解释的
  小型 watchdog/evidence 写盘余量，不以 OS OOM 作为正常收口。
- 后端仍使用同一 CSR/ABI/合格 JIT，numeric quota 受已验证 ICNTL23=4687 MB
  上界及当场物理余量约束。future 对象账继续记录，但预测不足本身不等于
  物理内存已经耗尽。
- 正常路径只允许一场 fresh B；若出现真实实现 bug，沿既有 hash-bound
  implementation-bug replay 登记和最小修复规则处理，不新增重试框架。资源
  耗尽不自动提高额度、换后端或重跑。
