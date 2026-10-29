# V21 轻量证据入口

T1/T2 是不同测试批次；S 是实际空间审计；F1 保存原包但独立 A6 失败。C、F2、E 未运行。

各阶段 artifact_index.json 绑定 ignored 原件路径、字节数和 SHA256。复制文件保留原字节；带 excerpt 的 JSON 明确列来源及 hash，不冒称原文件。大型 NPZ、完整资源流、trace 和源码快照留在工作站。

F1/root_numerical_stop.json 是主控标量/表级复核；F1/primary_byte_inventory.json 是纯字节读取，未在监控外复算场数组范数。A6 数值来自正式 worker 的原数组审计。共享缓存监测为空，worker 成功结束快照未到达，均保留限制。

root_review_scripts/ 仅记录本轮已执行的标准库复核脚本，不建立新 runner 或授权层。
