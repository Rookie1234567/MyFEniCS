# D15-Y3-2 结果与 Y4 同层分配（2026-10-21）

## 统一展示名

本轮用户将三个同为 12 层 y 分配的 D15 case 统一命名为 Y4-1/2/3。内部 profile、input、run_id 与已冻结身份保持不变：Y4-1=`Y3_3`（3/6/3），Y4-2=`Y3_4`（2/8/2），Y4-3=`Y4_4_4`（4/4/4）。后续报告、总账、比较表均以 Y4-1/2/3 为展示名，并同时保留内部 case/run_id 供溯源；别名表见 `records/d15_y4_display_name_map_20261021.json`。

## Y3-2 单场终态

Run：`results/si_block_phi90_50x50_17x20_h120/task40_phi90_13p5_D15_Y3_2_p6_direct_v1__full3d_direct__mpi1__Mna/20261021T084703.634131Z`。source `a0d67b7f7052d80eff4bd5c9488384a2cd5a9864`，input `968f47485f8e14bfac81da30e711b0fd4963be8402139d7560315d823142b01c`，physical `e962e48e909bd882ca5eddc619fbf378e488e583f1e34b7fd2d2e545ea4062e9`，resolved `4f499719c78021b4414394901cd8863ab7e1698ab207bebc4ac290cf3301f0da`。自然 exit 0、descendants cleared、`AUTHORITY_LIMITED`、`FULL_DTN_NOT_VERIFIED`。

本场实际 mesh `[6,10,6]`/360 cells，axis SHA x `bb1d6be1…f2a5361`、y `9adb867e…af04b21a6`、z `daf72294…b450afb6`，tags air/substrate/grating `252/60/48`；612 mode SHA `1987a2b3…7e522e`，surface q28，volume q15/default。单场 condensed residual `2.7871714331e-12`、独立 A6 residual `9.6275055795e-11`、energy closure `-1.9635404414e-12` 均通过各自既定门；一次同因子校正、numeric 1 / solve 2 / symbolic 1。elapsed `1798.406 s`，采样树 RSS peak `15,895,467,984 B`，task swap peak 0、PSS disabled。全机 WSL swap 的 +1 pswpin 仅作全局观察，不归因到本任务。终态 receipt：`tmp/task40_d15_y3_2_launch_v1/terminal_receipt.json`，SHA `607a7f35ed7676f9bc9a374d918e1c9cd5abe4dd185f0c68ec54da9415d8aae4`。

## Y2/Y3/Y3-2 比较

比较采用保存的612模态记录和同坐标 sample NPZ；没有 FE、插值或相位拟合。Y2 y 分段为 `2/4/2`，Y3 为 `3/4/3`，Y3-2 为 `2/6/2`；三者 x/z、mode SHA、q28/q15 和 relative-only 截断身份一致。

- Y2→Y3-2：总 R/T/A_balance/A_volume 差均在 `1e-5` 内；全612 T 最大差 `1.4986e-7` 通过，但全612 R 最大差 `1.0804674384e-6` 出现在 `top/outgoing_up/(0,0,s)`，略超 `1e-6`，故逐通道门失败。边界复幅相对差 `2.3733e-6`、E/H 相对差 `5.9884e-6 / 3.7368e-5` 通过。
- Y3↔Y3-2：总量、全通道 R/T、边界复幅和同坐标 E/H 三组比较门均失败；例如总 R 差 `1.8391e-4`、最大逐模 R 差 `1.8391e-4`、边界相对差 `4.0680e-4`。

完整 all-612 / power-carrying / propagating 分类和每模结果保存在比较 CSV。JSON v1 SHA `72212711a3543e3095a3ccd5514a08294bc52205f4dca6754bfda0bed90d736c` 保留；v2 SHA `046b0d90add2d9ccd226cb44a1f4c61c7a2898a0a300edb602ddbe6dd531d4e5` 只将差值条目的固定 `Y2/Y3` 标签改为真实 `reference_case/candidate_case`，没有重算数值。

## 同父、同规模 y 分配

以下三个备选均是 Y3-2 `[2,6,2]` 的兄弟方案，均 `[6,12,6]`/432 cells，不累计。y 材料区间为 `[0,15] / [15,35] / [35,50] nm`；固定 x/y/z 材料断点及 B 的 x/z 轴。

| case | y 每段 cell | y 坐标 nm | y SHA256 (little-endian f64) | 预期 air/substrate/grating tags |
|---|---|---|---|---|
| 展示名 | 内部 case | y 每段 cell | y 坐标 nm | y SHA256 (little-endian f64) | 预期 air/substrate/grating tags |
|---|---|---|---|---|---|
| Y4-1 | Y3_3 | 3/6/3 | 0, 5, 10, 15, 18.333333333333332, 21.666666666666668, 25, 28.333333333333336, 31.666666666666668, 35, 40, 45, 50 | `ceb0f46c…e76162ec` | 312/72/48 |
| Y4-2 | Y3_4 | 2/8/2 | 0, 7.5, 15, 17.5, 20, 22.5, 25, 27.5, 30, 32.5, 35, 42.5, 50 | `cd6ef7bb…739109e` | 296/72/64 |
| Y4-3 | Y4_4_4 | 4/4/4 | 0, 3.75, 7.5, 11.25, 15, 20, 25, 30, 35, 38.75, 42.5, 46.25, 50 | `025e4039…61b6ed0` | 328/72/32 |

主控更正了早期 Y4 tag 算术；保留坐标与材料几何时，中点分类为 `2 x-center × 4 y-center × 4 z-interior = 32` grating、`6 x × 12 y × 1 bottom-z = 72` substrate、剩余 328 air。静态计划 v1 只列 Y3-3/Y3-4，SHA `d8c90a6bfb603fa835450e3a30f8922de4adaf40ab11c7a72d915a90f855317a`；v2 加入独立 Y4_4_4 标签并保留该更正，SHA `9ad27c53e6668aeace605dbcbf47053aeccecc1102a383fb3864861811aa22fd`。这只是轴/hash/tag 规划；实际 mesh QA 必须由每场运行验证。

定向 Task40 D15 planner/profile/mesh QA/manifest→worker tests：`25 passed / 1.20 s`。测试经 Task40 PORD64 activation，无 mesh/FE 计算。后续按 Y4-1、Y4-2、Y4-3 顺序运行；每场比较共同父 Y3-2及其他已完成 sibling，使用三组原门。每场运行前重新 fresh，不并发。canonical sidewall 仍 `NOT_MEASURED`，有限 R13 rectangle 仍不构成 full-DtN qualification。
