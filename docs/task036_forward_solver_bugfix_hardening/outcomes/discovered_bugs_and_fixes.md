# Task036 V2 discovered bugs and fixes

## 1. V2 启动时的已知状态

完整 B01–B11 before/after 见 `bug_port_matrix.md` 和 `fix_report.md`。V2 启动时，
与全域扫描直接相关的开放项只有：

| ID | 现象 | 当前状态 | V2 处置 |
|---|---|---|---|
| V2-B01 | Hybrid-P 调用处仍把 `modal_rank_sufficient=False` 写死 | raw shard 已改为 `pending_actual_M_convergence`；aggregate analyzer pending | 用同点相邻 M 的真实响应、interface、dual、biorthogonality 和 projection 判定 |
| V2-B02 | one-shot repair 只联合最坏的一对 blocks，误差会移动到另一组 | code fixed；PDE regression pending | 一次规划全部同方向、近 beta、超 overlap 的 connected components；全部预检 size/condition 后批量 joint inverse，再检查完整 row norm |
| V2-B03 | P 在 M120 下 interface/modal rank 不足，接近 full rank 时历史 energy 仍失败 | unresolved mechanism | 按失败簇运行 M120→240→480→full-rank，先区分 truncation、coupling 与 ledger |
| V2-B04 | 正式 Hybrid watchdog 不支持 p5 或动态 phi/height/width/Ny4，可能误绑定中心几何 reference | code fixed；PDE regression pending | 新增显式 Task036 opt-in；outer/worker 双重绑定 raw Full3D source、hash、p/h/MPI/S-P/角度/几何/topology/backend/projection |

## 2. full-suite 收口

V2 开始前的 full-repository pytest 已经结束：

```text
803 passed, 41 skipped, 3 failed in 2935.37 s
```

三个 failure 都不是数值 PDE failure：

1. B08 后的旧 telemetry 文案断言；
2. clean worktree 没有 checkout-local `.venv` 链接导致 ABI 路径误判；
3. numerical-blob checker 漏登记 QEP explicit residual helper。

前后两个由 `5231282f21e799c62b3a10ac1ccb1a8226935dc6` 最小修正，中间一项在
正确链接同一资格化 `.venv` 的 clean worktree 中通过。最终定向回归为 `59 passed`，
没有重跑 PDE，也没有虚写 full suite 零失败。

## 3. V2 新发现项与处置

### 3.1 V2-B04：动态输入端口

```text
status = FIXED
source = 6d5e9781bcb1458ecac7a77af22fa2d420f0cd55
```

五个正式 configuration pair 覆盖 p5/p6、S/P、`azimuth=0/45/90°` 和
`grazing=0.5/10°`；实际几何均为中心点 `120/17 nm`。每个 Hybrid 均绑定同输入、同源码
的 Full3D watchdog hash，证明 p5 和动态照明入口不再静默回退到旧的固定 Task035c
身份。动态几何 identity 由 mutation/unit tests 覆盖，尚没有 actual PDE 几何邻点。

### 3.2 V2-B05：static recovery 使用了错误的 traction beta 来源

static-condensed Hybrid 的 field recovery 会重新装配局部 traction，但此前没有把 coupling
已选择的 discrete traction beta 传回重装配，而是重新使用 raw QEP beta。这个错误会使
solve 与 recovery 使用不同的离散导数，即使两组 beta 很接近也会破坏证据身份。

本轮在 `src/solvers/hybrid_static_field_recovery.py` 中显式传入
`beta_override=selected_coupling_traction_beta`，并补充单元回归。五个 actual M120
点的 exact traction 均为 `4.565e-13–2.169e-11`，说明该一致性错误已修复；但物理界面
跳跃仍为 `9.272e-5–1.822e-1`，所以它不是重复失败的完整根因。

```text
status = FIXED_BUT_NOT_ROOT_CLOSURE
```

### 3.3 V2-B06：`full3d_uniform_cg` middle-volume energy 使用了错误场模型

旧 ledger 用连续指数 surrogate 积分 middle volume，而实际传播模型是 scalar-CG cell
polynomial。修复后 energy 直接积分求解中使用的 cell polynomial，不再把另一个连续场
冒充物理体场。

修复是必要的，但五个 M120 点中只有 A049-P 的 energy closure 通过：

| point | energy closure | `1e-5` Gate |
|---|---:|---|
| A001-P | `7.606e-5` | fail |
| A004-P | `1.491e-5` | fail |
| A004-S | `1.533e-5` | fail |
| A049-P | `1.092e-6` | pass |
| D001-P | `1.307e-5` | fail |

因此 ledger bug 已修复，但 remaining energy/channel failure 不能再归因于这项积分公式。

```text
status = FIXED_BUT_NOT_ROOT_CLOSURE
```

### 3.4 V2-B07：五路 MPI8 的 OpenMPI 绑定覆盖外层 CPU lease

首次五路并发时，outer `taskset` 分配了五组互斥的八核 lease，但
`OMPI_MCA_hwloc_base_binding_policy=core` 与 slot mapping 令每个新的 `mpiexec`
都从自己的可见拓扑起点重新选择 CPU0–7。结果 40 个 worker 初期共享八个核：
数值和 process-tree memory 有效，wall time 被污染。

driver 改为：

```text
OMPI_MCA_hwloc_base_cpu_list=<explicit lease>
OMPI_MCA_hwloc_base_binding_policy=cpu-list:ordered
```

独立 MPI8 probe 证实 rank 0–7 分别只占用 lease 中一个不同 CPU。该修复不改变数值
kernel，所以没有重跑十条 PDE。

```text
status = FIXED
```

### 3.5 V2-B08：M120 投影约束没有消除 FE trace complement

五个同源 M120 点共同表现为：

- true residual：`3.103e-13–2.856e-11`，pass；
- algebraic interface E：`3.709e-13–1.936e-11`，pass；
- exact traction：pass；
- biorthogonality row norm：pass；
- recovered physical interface E jump：`9.272e-5–1.822e-1`；
- fixed channels：仅 `32/80–77/96`。

这些结果强烈支持：当前方程 `D_s g_s=L_s a` 约束了 M 个投影坐标，却没有消除
`q_s in ker(D_s)` 的界面分量。A049-P 的历史 M120→M492 漏斗又显示物理跳跃不随 M
消失，而 M492 峰值约 19.405 GiB，远高于约 10.161 GiB 的 Full3D。

Task036 不允许为此重建 Hybrid 架构。本轮关闭 M 扩张，并提出后续强迹子空间消元：

```text
g_s = R_s L_s a
M hard cap = 120
no dense R_s D_s
fail closed if M120 does not qualify
```

它必须同时重定义局部消元、Petrov flux row、Floquet/orientation closure、field recovery
和 constrained true residual，不能作为一个局部补丁冒充已修复。

```text
status = DEFERRED_ARCHITECTURE_REQUIRED
ordinary default = unchanged
```

## 4. 为什么没有继续 226 点全扫描

Review V2 要求“失败立即分类；同一问题在多个点重复出现时直接修复通用算法”。五个点已经
跨越 S/P、p5/p6 和三个方位角，并重复给出相同的投影通过/物理通道失败结构。继续跑其余
221 个点只会积累同一已知架构负结果，不会提高根因判别力。

因此当前 map 的未运行项不是跳过未知错误，而是：

```text
stopped_after_first_repeated_root = true
new production-qualified Hybrid region = none
M240/M480/M492 = not_run
next work = strong trace-subspace elimination under M120
```
