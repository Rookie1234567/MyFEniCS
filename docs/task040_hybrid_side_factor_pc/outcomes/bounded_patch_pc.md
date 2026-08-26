# T40-4 bounded patch PC

## Review V5 当前状态

`not_run_by_route_c_no_signal_and_resource_authority_gate`。Route C 的 no-signal stop 与
resource-authority gap 未授权 bounded patch 或 Level B；不是 patch 算法失败。

## Review V4 历史状态

T40-4 原计划把人工截面 oracle 收缩为真正有固定局部行数上限的 patch/class factor，并
测试 owner routing。T40-3 的 mandatory rho 已失败（最小也为 14.24201480051629，最大为
28.316064601533686），所以该阶段没有运行，也没有产生 `max_local_rows`、局部 factor
容量或 patch residual 结果。

这不是 bounded local PC 已失败的证据；Task40 只证明冻结的 T40-3 transmission mechanism
不稳定。不得把该阶段写成算法负结果或据此要求 coarse space。

## V1-8 收口

V1-2 资源硬停止发生在合格的 exact interface audit 之前，因此 bounded-patch 与 Level-B
capacity 仍为 `not_run_by_gate`。没有新的 `max_local_rows`、local-factor、residual 或资源
结果；这不能证明 bounded local PC 或 coarse information 必须存在，也不能证明它们不可能。

## V2-G 收口

V2-D bounded patch Level B 为 `not_run_by_gate`：V2-B2 projected-transmission 的五源
数值 Gate 已触发真实负结果，按决策树不进入 Level B。本状态不等于 bounded patch 算法
失败。

## V3-5 gate status

`not_run_by_v3_2_numerical_gate`。V3-2 full-span coupled consumer 的五源 true residual
未通过，未进入 bounded local patch；本阶段没有新的 `max_local_rows`、factor、RSS 或 residual
测量，不能把未运行写成 bounded patch 数值失败。

## Review V4 历史收口

`not_run_by_v4_1_identity_gate`。V4-7 bounded patch/Level B 在构造 system、裸 `F`、interface
mass、PETSc Vec 和 factor 之前停止；没有生成 `max_local_rows`、局部 factor、patch residual、
rank、DoF、RSS 或 wall 数据。原因是冻结 exact spool 没有能把旧 raw row 绑定到当前物理自由度的
canonical source-row bridge（通俗地说，就是缺少“文件行号对应哪个物理未知量”的地图），不是
bounded patch 算法失败。V4-2 至 V4-10 均由该身份门阻止，见
[V4-1 compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v4_1_exact_authority_compatibility_v1.json)。

## Review V5 当前收口

bounded local patch 与 Level B 没有运行，状态为
`not_run_by_route_c_no_signal_and_resource_authority_gate`。Route C 两源均无正信号，且
resource authority 因中段 live-unreadable process-tree rows 不完整；没有
`max_local_rows`、patch factor、rank、residual、RSS 或 wall 新数据。不能把这个未运行状态
写成 patch 算法失败。
