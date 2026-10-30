# D07C G3 M8/N96：静态准备与审核包

## 范围

本记录准备一个新的有限模态完整场候选 `D07C-G3-M8-N96`。它沿用已完成 G3 网格与同一 0.7 nm 物理，只把负 `n` 下界从 `-64` 扩到 `-96`；不改变 `m` 范围、网格、材料、角度、偏振、q81 表面积分、q15/default 体积分、relative-only cutoff 或 p6 凝聚直接法。旧 G3 M8/N64 输入、结果和包均保留原样。

本轮只做了 formal loader / production mode inventory / manifest-worker 静态检查与定向测试。没有启动 FE，也没有建立新网格、carrier、矩阵、factor 或 solve。新场仍需主审包审核、之后的独立 fresh PASS 和一次 systemd 标准入口；当前并行邻任务未获例外，若仍活动，fresh production guard 应保持拒绝并等待其自然清场。

## 身份与生产枚举

| case | 网格 | 有符号矩形 | 通道数 | 传播 / power-carrying | 模态 SHA256 | 身份与证据 |
|---|---:|---|---:|---:|---|---|
| 已完成 G3 M8/N64 | `[6,100,8]` / 4,800 cells | `m=-8…8,n=-64…1` | 4,488 | 4,360 / 4,426 | `e4cef2ecadaab2563a46592dfe31df04aa47bc113f3a69e1ac0ecd70cebf2ef0` | run `20261030T132407.592584Z`；source `3a0676dd47c7729fa279d74b114aaf2125ec8072`；[terminal manifest](../../../results/si_block_phi90_50x50_17x20_h120/task40para_phi90_0p7_D07C_G3_M8_N64_p6_direct_v1__full3d_direct__mpi1__Mna/20261030T132407.592584Z/run_manifest.json) 与 [direct summary](../../../results/si_block_phi90_50x50_17x20_h120/task40para_phi90_0p7_D07C_G3_M8_N64_p6_direct_v1__full3d_direct__mpi1__Mna/20261030T132407.592584Z/p6_condensed_direct_summary.json) |
| 新候选 G3 M8/N96 | `[6,100,8]` / 4,800 cells | `m=-8…8,n=-96…1` | 6,664 | 6,536 / 6,602 | `f044d5183d9f106bfff3e9d312e6aef9e7a205ab42b961655c4415a6afab949d` | input `d07c_g3_m8_nminus96_to1_p6_direct.dat`；physical SHA `8614e125acda5e11c6c00ef4152e944cd3af09a14760e1d4338f4e1bf87b0631`；resolved SHA `49368696418a6e6a52ced944bfb8006aebf869b6ecbb5fa5468cd9baa0d9940f`；静态计划见[JSON](records/d07c_g3_m8_n96_static_case_plan_v1.json) |

两份输入经 production `load_and_resolve` 解析后，physical model SHA 相同。两份清单都用 Task40 production `build_dynamic_mode_inventory`，绑定各自 runner profile 的 `explicit_signed_rectangle`、`boundary_magnitude_scaled_r5_v1` 归一与 q81。N64 的 4,488 个有序 signed keys 是 N96 清单的有序子序列；新增恰为 2,176 个 `n=-96…-65` 通道，覆盖上下端口和 s/p。此次新增 key 均被 production inventory 分类为传播且 power-carrying。

N96 仍是有限窗口，不是 full DtN。它相对同网格 M8/N143 有限集合仍少 3,196 个模式，其中 3,128 个传播、3,162 个 power-carrying；相对 production 自动传播清单 64,120 个模式，N96 仅含 6,536 个传播模式，省略 57,584 个传播模式（高 `|m|` 级仍在窗口外）。不要把 163,020 个包围矩形候选键数写成自动传播库存量。资格状态保持 `FULL_DTN_NOT_VERIFIED`，canonical 方柱侧壁保持 `NOT_MEASURED`。

## 原 G3/N64 终态

原 G3/N64 run 为自然 `finished/exit0`，`descendants_cleared=true`、`remaining_child_pids=[]`；其 p6 direct summary `passed=true`。原场凝聚相对残差 `7.0197e-12`、活动 M8/N64 算子独立 A6 相对残差 `3.6552e-9`，均分别在原 `1e-9` / `1e-6` 门内；q81 surface、q15/default volume。整树采样 RSS 峰为 `378,244,096,000 B`，task swap 峰为0，elapsed `20,069.343 s`。这些数值仅描述原 N64 场，不预测扩到 N96 后的内存、耗时或精度。

## 比较合同与限制

N64→N96 只允许按同一 G3 网格做有限截断对照。比较仍使用既定三组门：global `R/T/A_balance/A_volume` 绝对差 `<=1e-5`；逐 signed 通道 `R/T` 绝对差 `<=1e-6`，覆盖全部共同/新增与 power-carrying 通道；boundary 复振幅及同坐标复 E/H 相对 L2 `<=1e-4`，不做整体相位拟合。新增通道对 N64 缺项需按比较器的明示缺项规则列出，不把缺失值写成实测零。

N96 尚未运行，所以全部比较量为 `not_run`。即使该有限比较通过，也只支持此 G3 网格、两种有限窗口之间的观察，不能证明完整传播 inventory、全 DtN、RCWA 精度或网格收敛。单场残差和能量门与截断比较门分别报告。

## 定向检查

在 Task40 qualified PORD64 activation 下，N96 formal loader / runner profile / production mode inventory / manifest-worker 贯通及既有 D07C finite-mode、manifest-worker、host-floor、M8 refinement 定向测试共 `25 passed in 39.39 s`；新增 N96 模块 Ruff 通过、相关文件 compileall 和 `git diff --check` 通过。没有运行全仓测试或 FE。

新 case 的 review package/sidecar 在源码 clean freeze 后绑定。当前 profile 明确 `concurrent_neighbor_authorized=false`，host-floor 为 64 GiB available，无固定 RSS cap；fresh 使用 canonical 锁和生产 active/unknown solver 扫描，CPU9 parent / CPU24 worker、MPI1/math1、NUMA interleave0-1、PSS/USS关闭、swap observe-only。独立 systemd `Restart=no`，只允许 review+fresh PASS 后提交一次；不做 direct FE exec 或自动 retry。
