# Response V2：用户授权后的性能验证接线

本轮由主控明确授权继续执行原生 Linux native-capacity campaign。此前 `f124679e75915758076d9240bd4bef2f5c772752` 已提交的 p4 按行内核、p4/p6 curl 独立循环合并和 PSS 降频作为唯一性能实现；不新增求解算法、预条件器、子域法或参数扫描。旧的 13.5 nm screen 负结果和首次 mode 失败保留不变，新正式运行必须从零、冷缓存、clean source 开始。

## 生效合同

| case | 材料身份 | screen | solve 上限 / s | workflow 上限 / s | 其他固定项 |
|---|---|---:|---:|---:|---|
| 13.5 nm original | Si，`n=0.999002304859+0.00182649365i` | 128 步、7200 s | 43200 | 64800 | MPI1、线程1、restart32、max2048、zero start |
| 13.5 nm notch | Si，同上 | 不启用，不增加 screen | 43200 | 64800 | 同上 |
| 5 nm（后续解锁） | Si，`density=2.33`，`delta=0.00603145547`，`beta=0.00435380777`，`n=0.99396854453+0.00435380777i` | 既有 10800 s | 86400 | 129600 | 仅在 R1/R2 资格后按实际 channel/inventory 预检 |

5 nm 数值来自用户本轮权威输入；本轮不声称已独立核验数据库来源。它是复折射率 `n`，不是 epsilon；运行时由 `epsilon=n*n` 生成并记录。3 nm/2 nm 材料身份不在本轮自行推断。

## 当前状态

截至本澄清文件创建时，唯一执行 worktree 为 `/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity`，交接 HEAD 为 `0e8c06e1f817fda22b10e75b03987ae5a4cce4b9`，工作树 clean。现先完成预算接线、最小参数验证和提交；提交后的 clean SHA 才允许启动新的 13.5 nm original。运行期间保留 CPU23 worker / CPU9 supervisor 的实际占用证据；绑核只说明 affinity，不外推共享内存带宽或功耗无竞争。

## Original 13.5 nm native formal retry：own 结果与参考资格边界

用户已明确授权本次性能修复后从零验证，因此本次正式 run 不再受旧 §11 性能停止阻断。run 使用 clean source `9b1e8d4a1b2be9fca5b126a1ec3893e3af295e5e` 和唯一入口 `python scripts/run_case.py input/task39extra_para_workstation_capacity/original_13p5nm_p6h10.dat`，目录和 compact 记录见 [`r1_attempt3.json`](outcomes/records/r1_attempt3.json)。

本次 `iteration=550`、outer `matvec=567`、`PC=550`，terminal true residual=`9.998974191134654e-7`，solve=`11589.4608165932 s`，workflow=`12560.042750451947 s`；`exit=0`、`COMPLETED`、`descendants_cleared=true`。checker 的 `independent_output_gates_passed=true` 且 `gate_failures=[]`，但分类仍为 `BALANCED_OUTPUT_AUTHORITY_LIMITED`。80 通道 relative amplitude difference=`1.339354498931458e-9`，只是部分 modal/own-output 证据。

生命周期口径已按最终 watchdog 与 physical summary 固定：整树最终峰值 RSS=`3631751168 B`、swap=`0`、样本=`36437`；setup 峰值另为 `3404267520 B`，不能冒充最终峰值。释放前后 RSS 都是 `3078565888 B`，因此记录为无观测 RSS 回收，不虚构 allocator 回收。p4 assembly 当前 `491.016220843 s`，旧 `1818.610 s`，约 `3.703767661438x`、降低 `73.000466%`。

own 结果的 `A_balance/R/T/R00/A_volume` 和能量闭合均已保存，但 `matched_reference.full_field=WSL_FULL_FIELD_COMPARISON_PARTIAL`、`reference_authority=REFERENCE_AUTHORITY_LIMITED`。旧 native 62 步负结果与旧 WSL V5 original 564 步/notch 576 步成功历史保持分开；本次不重新运行原始 550 步，不继续寻找旧 WSL 64/128 checkpoint，也未启动 notch。

当前唯一下一 Gate 是沿既有路径完成一次 native direct matched reference：先做 symbolic preflight，再在独立 run 目录、无迭代进程重叠、授权 `21600 s` reference workflow、CPU23 worker/CPU9 parent 与整树 watchdog 下执行。若发现现有 public adapter/dat/field comparison 接线确有源码缺口，先提交最小文件列表和接线方案审核；不开发新 direct 算法、PC 或防御框架。
