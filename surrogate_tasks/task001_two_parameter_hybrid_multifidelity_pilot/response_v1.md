# Task001 Codex Response V1

## 完成状态

Task001 已完成，等待 ChatGPT Review V1。任务止于有限元、多保真与局部可辨识性 pilot；
没有开始 Task002 的 49 点批量生成、代理训练或正式反演。

正式 PDE numerical source 为
`68f4f9bc92de6cd7ec2896755ef210fb182280a1`。此后只修改 order 提取、checker、compact
evidence 与文档，没有继续运行 PDE。最终 postprocessing/docs 身份由包含本文件的执行分支
HEAD 与 push 报告确定。

## 对用户变更的落实

- 将输入分为 DOE-controlled `configuration` 与 invertible `geometry`；
- geometry 仍只包含 Task001 的 height/width；
- user grazing 0.5--10°（不算 0°）、azimuth 0--90°、S/P；内部明确角度换算；
- HF 使用 global p6，无 adaptivity；
- Task001 不训练 surrogate，把模型训练留给 Task002；
- 选定 configuration bundle 为 10°/0°/S 与 10°/90°/S；
- 明确 P 和部分近掠射配置尚未资格化，未来 DOE 提议的新配置必须先过 FEM Gate；
- Docker 未使用，HF7P5 在资源预测 Gate 受控停止，未启动 PDE。

## 主要结果

- selected HF/LF：HF10 p6/h10/M120 与 LF4 p4/h10/M120；
- selected HF R+T：rank 2、cond 1.2208、rho -0.1479；
- reflection-only HF：rank 2、cond 1.3217、rho `1.82e-4`；
- 37 measured pass、5 failed candidate records；负结果和 log hash 保留；
- HF7P5 central/conservative 预测 10.793/14.788 GiB，PDE launched=false；
- Task002 冻结为 49 geometry x 2 configurations = 98 LF solves；全部后续预算写明 physical
  solve count。

## 后处理修正

有损基底可能出现 raw dispersion `propagating=false` 但仍有正 outward Poynting flux 的模式。
旧提取器会把它错误置 null。现在 compact `propagating/power_carrying` 使用正功率语义，另存
`dispersion_propagating`；真实 0.5° record 的 raw order sum 与端口 R/T 精确一致。原始 PDE
record 未改动。

## Review 入口

- `outcomes/summary.md`：总表、失败、边界和 selective merge；
- `outcomes/fidelity_qualification.md`：HF/LF、HF7P5 资源 Gate；
- `outcomes/illumination_identifiability.md`：LF/HF Fisher 与 recovery；
- `outcomes/task002_dataset_plan.md`：未执行的 Task002 冻结计划；
- `benchmarks/cases/110_surrogate_two_parameter_pilot/records/`：hash-bound compact evidence；
- `benchmarks/check_case110_task001.py`：从 raw artifact 独立重算。

请重点审阅：有损 order 的两种传播语义、P/近掠射失败边界、selected configuration bundle、
HF7P5 projection stop，以及 Task002 是否应先增加 configuration requalification 子阶段。
