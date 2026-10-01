# dot 云端并行研究：首批结果

## 面向 0.7 nm / 2 TB 的结论

局部矩阵生成有正信号，但它只解决装配的一部分工作。完整求解仍受全域 p4 因子、每步纠错成本和实际端口/工作向量库存影响；本批没有目标模型解，也没有 2 TB 或 48 小时达标证明。结构化几何的精确共享比逐单元最坏情形有利，不能把 15–17 TB 假设写成不可避免。

| 实验/分析 | 实际结果 | 数据身份、单位与范围 | 证据 |
|---|---|---|---|
| p6 六参考积分复用 | 14 组矩阵最大相对差 3.5810e-16；作用 4.3008e-16；5 组 Schur 最大差 5.6901e-15；补充 G1 恢复残差 1.4651e-11 | measured；无量纲；局部 882/450/432 维，非完整 PDE | [tensor findings](../../../benchmarks/cases/task40extra_dot_parallel_cloud/tensor_reuse/findings_zh.md) |
| 同批局部生成成本 | 含共享构造器及模板准备后候选 1.4009 s / 原核 5.1446 s，约 3.67 倍；六实模板 35.61 MiB | measured；6 次配对、云端调度噪声；不是完整求解提速 | 同上 results.json 与 provenance.json |
| DtN 模式 | 母体 M0/M1/M2/M3 = 80/180/340/532；增长 M2 母体 q1.25/q1.5 = 588/700 | measured generator；通道数；按键是子序列，非前缀 | [DtN findings](../../../benchmarks/cases/task40extra_dot_parallel_cloud/dtn_modes/findings_zh.md) |
| 实际生产端口默认规则 | M3 degree27 对应 14×14；局部投影对 48×48 相对差最大 2.252e-10 | measured component；未查全局装配/运行时 override；无需据此盲改默认 | 同上 production_port_rule.json、trace_quadrature.json |
| 原 G1 时间分账 | KSP 占 76.523%；即删除全部 setup，其他不变也最多 1.28464 倍 | derived from parent measured；不是新云端 PDE | [容量与优先级](capacity_assessment_zh.md) |
| 精确几何计数 | G0/G1/E1/E2 原始材料+metric 类型 33/30/156/156；假设恢复带缺口尺寸有 1,369,452 cells、211 原始类型 | derived metadata；orientation/factor 实际类型 unknown | [compact inventory](records/exact_metric_inventory_compact.json) |

## 含义与保留边界

参考积分复用是把单元基函数积分预先做成六张表，随后用每个单元真实几何组合矩阵，避免重复积分；它不合并近似几何、不共享不同局部 LU，也不减少全域 p4 因子。当前比较共享 Basix 基础，缺独立编译 FFCx oracle、真实方向/Floquet/MPC、非零端口 RHS 和完整原 A6 资格。

DtN 实验检查开放边界通道的编号、物理方向和局部投影积分。它没有测量增加通道后的全局场/功率变化，因此不能授予截断资格。8×8 的 1.942% 误差仅是人为低阶负对照，生产已采用更高且自适应的规则。

| 负结果/未执行项 | 实际状态与原因 | 下一步 |
|---|---|---|
| 原构造器在新 UFL 测试 | cellname 方法/属性 API 不兼容，原测试真实失败；实验副本一行适配后通过 | 保留错误日志，不改父源码或声称原 ABI 通过 |
| 完整 PDE、official R/T/A、截断/连续精度 | not_run；本支线是组件诊断 | 正式任务需原环境完整验证 |
| 目标 2 TB / 48 h | unknown；实际目标几何和全面库存尚不足 | 优先弄清全域 p4 与每步纠错成本，不再只优化装配 |
| CI / 全库 pytest / MPI | not_run | 只陈述本批实际检查 |
| GitHub 视觉渲染 | 未验证；源码表格/链接结构检查完成 | 不把提交成功等同渲染 Gate 通过 |

## 身份、检查与合并边界

基线 c786e87d03976a52f57d1e7f69a3c63f992afe90；云端下载 20 文件各多一个末尾 LF，去掉恰好该 LF 后 blob 匹配，实际字节 SHA256 均保留。新 research 核心位于 src，未接入生产。portable 脚本仅改源/输出路径，保留实际计时版本；发布前在独立云端布局复跑六个 portable 脚本均 exit 0，数值检查通过，未用复跑挑性能样本。详见 [复现入口](../../../benchmarks/cases/task40extra_dot_parallel_cloud/README.md)。

| 依赖组 | 本批变化 | 建议 |
|---|---|---|
| production numerical/core | 无生产接线、无默认变化 | 不授予生产资格 |
| research-only | src/solvers/task40extra_reference_metric_component.py | 保持 opt-in；下一步独立 oracle/方向检查 |
| checker/benchmark | 两类组件 runner、计数脚本与 compact records | 仅其明示范围 |
| compact evidence/docs | 本目录、benchmark findings、项目回顾 | 可独立审阅 |
| do-not-merge | 整体研究分支、raw/模板/cache | 未开 PR、未 merge；仅更新 dot 独占分支 |

## V2：真实三维G0 p4算子数据

| 范围 | 实际状态与数据 | 证据 |
|---|---|---|
| 小型真实三维p4装配/导出 | measured；336 cells，29,072 rows、10,912,592 NNZ、80端口；complex128/int32 CSR 218,368,132 B | [V2详细结果](real_p4_probe_preparation_v2.md) |
| 独立内容/资源核验 | 全1,486 arrays核验；同时树RSS峰1,199,104,000 B，136.742秒，swap0；无global factor/solve | [compact记录](records/real_p4_probe_preparation_v2.json) |
| 失败/ABI边界 | 两次collection失败、一次mode-hash失败保留；危险历史private-FFI未运行；新环境小型资格单独记录 | 同上 |
| 最终目标 | 完整三维原尺寸50×25×140 nm、无缺口规则基线、0.7 nm、约2 TB/≤48小时；未来三维缺口能力保留；截至2026-10-04 10:07:14 UTC的72小时研究窗口 | 当前目标能力unknown；不以二维/2.5D替代 |
| 下一步 | 准备公共backend128reference+完整原A4 residual screen；尚未运行；64在其通过后再决定 | [Response V2](../response_v2.md) |
