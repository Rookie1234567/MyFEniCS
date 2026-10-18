# Task41extra Response v1：P0 收口与 B0 当前状态

## 当前结论

新物理在 0.7 nm 已实际进入 Task41 B0：50×50 nm 周期、居中 17×20×120 nm Si 主体、掠角 1°、方位 90°、S 偏振；p6、10×200×14 网格、MPI1。端口库存为 64,120 个模式，q_count=200；143 个 q 有模式、57 个 q 为空。端口载体（carrier）保存各衍射模式与有限元边界未知量之间的耦合数据，供后续边界作用使用；它并非求出的电磁场。carrier 已写完 64,120/64,120 模式，但数值流程在 assembly 阶段遭遇 RESOURCE_CONTROLLED_STOP。没有完整 0.7 nm 场、KSP/FGMRES、独立 A6 或 official R/T/A；2 TB 和 48 h 目标仍未资格化。

13.5 nm 的 A1 完整直接场和 A2 同离散迭代比较/保存场 checker-only retry3 已通过 A 出口。A1 独立原 A6 为 1.7449656226232747e-10，R/T/A_volume 为 0.25137919146306575 / 0.05712971752020276 / 0.6914910910199371。A2 对照的 E/scaled-curl 相对差为 6.83819901978217e-09 / 6.845781370112187e-09，R/T/A/A_volume 绝对差为 2.9661779699097224e-09 / 3.04267534778635e-10 / 3.2704455810161903e-09 / 6.763047344371387e-09。历史 attempt7 原 worker 的 WORKER_FAILED 仍保留；A 出口 PASS 不等于 0.7 nm 通过。

## B0 停止与边界

冻结源码为 c52d0d3c0ec6b46c52c3bcf464ee53164308f1c5，input SHA a0c45d0475bd2b41d2d19589831086468a62f39fdca5b74734b62751df1485c1，物理 SHA 0e272beec0cbbd946d62220f1947f60e11e61411b1fec32e62a9979ec922145d。固定执行合同 SHA 5657d456d67f2b9e3b94aa19a0666a1b011dece6e7b6c7043eb929b45d711f5d，window SHA 87dd4ec560a208122e9959987a392bf878162793c61582877969206686d922e6。本次完整工作流 62,890.80 s，时间门没有超限；process-tree RSS 峰为 1,271,718,285,312 B，task cgroup peak 为 1,580,571,795,456 B（limit 1,649,267,441,664 B），task swap 为 0 B。未完成 B0 action/FE 组装、q CSR/factor、KSP/FGMRES、场或物理输出。

这次受控停止的直接触发条件是 generic watchdog 在分域 reserve 下仍无条件比较 effective_available_bytes < reserve_bytes。触发样本中 host available 为 854,915,547,136 B，扣除 64 GiB host reserve 后仍有 786,196,070,400 B；task-cgroup remaining 为 68,698,267,648 B，而 task-cgroup 自身 reserve 是 0 B。因为 effective available 取两域较小值，它比 host reserve 少 21,209,088 B，于是误触发。主机 reserve 本身没有耗尽。此处要修正分域 stop predicate 并加定向测试，同时保留 64 GiB host reserve、1.5 TiB task cap 和 0 B task-cgroup reserve；不能靠放宽门限继续。

持久 checkpoint 有 64,120/64,120 模式，大小 363,791,051,840 B；原 watchdog summary 在当时清场检查记 descendants_cleared=false。稍后于 2026-10-18T04:16:04.696333+00:00 单独核对旧 PID 已全退出且旧 cgroup 消失，这项 later-cleanup evidence 没有回写旧 summary。虽然载荷完整保留，本次 cache_metadata_stable=false，且现有 checkpoint 身份绑定 producer source/input/window/contract，因此没有声称它已经可以由修复后的新 source 复用。

## 已记录的构建成本

完整 carrier 构建父阶段实测 28,042.209265 s（约 7小时47分），CPU 27,759.194920 s；其内 component 作用累计 4,482.765038 s，积分、MPC回拉、筛选分别记录 1,697.727167 / 1,472.905536 / 1,305.622877 s。这些子计时不与父计时相加，也不靠差额推定未计时部分。规范化、slave检查和暂存释放没有独立计时，保留 UNKNOWN。后续装配未记录内部游标；源码中的约181.895亿个B/D行值项逐项转换是候选瓶颈，尚不是实测热点定位。

## 下一步审查项

1. 修复 generic watchdog 的 split-domain reserve predicate；对 split 分支分别判断 host 可用量和 task-cgroup 自身 reserve，保留原 cap/reserve。
2. 改造 carrier→P6 action 接口，去掉逐项 Python 展开和完整重复 backing。调用点现在没有传 bounded_direct_term_build；即使启用现有分块分支，仍有逐行 Python 映射和按源规模分配的 direct 输出数组。已有 one-mode iterator/provider 可作为基础，但未在本 B0 checkpoint 上资格化。
3. 将 checkpoint 数学身份与执行 provenance 分离：保留原 producer source/window/contract 不可变；只有输入、模式顺序、网格/dofmap/MPC、积分/相位/归一化和 carrier schema 等数学身份完全一致，且文件及 manifest 稳定性验过，才能让新 consumer 重开。

停止证据及原始资源行哈希见 [B0 compact](outcomes/b0_resource_controlled_stop_20261018.json)、[run index](outcomes/run_index.json) 和 [outcomes summary](outcomes/summary.md)。本次收口只修改证据文档，没有重跑 FE/PDE 或改变科学源码。主控已独立核对停止前后精确资源行、原始摘要及相关源码 hash；保留旧负分类，集中提交同一任务分支。资源谓词及库存优化尚未实现，续作前仍须定向验证和冻结源码。
