# D15-Y5-1 后 z 单轴细化静态计划（2026-10-21）

## 已有同策略 y 证据

Y5-1 `[6,14,6]` 是当前 13.5 nm 的 y 方向工程候选。相对它独立计算的 Y6-1、Y6-2，以及 Y6-1 与 Y6-2 的互比，三组都通过原三类比较门：总量绝对差 `<=1e-5`；全部 612 个共同通道（含有损 power-carrying 通道）的逐通道 R/T 绝对差 `<=1e-6`；不做整体相位拟合的边界复幅和同坐标复 E/H 相对 L2 差 `<=1e-4`。这是保存样本/有限 R13 口径，不外推全域、canonical 侧壁或完整 DtN。

| 比较 | 最大逐模 `|ΔR| / |ΔT|` 与 key | 边界复幅相对 L2 | 同坐标 E / H 相对 L2 | 三组门 |
|---|---|---:|---:|---|
| Y5-1 → Y6-1 | `5.0652e-8` top `(0,0,s)` / `7.0344e-9` bottom `(0,0,s)` | `1.1120e-7` | `1.1257e-6 / 8.2771e-6` | PASS |
| Y5-1 → Y6-2 | `8.9067e-9` top `(0,0,s)` / `1.1849e-9` bottom `(0,0,s)` | `1.9295e-8` | `5.5828e-7 / 4.1625e-6` | PASS |
| Y6-1 → Y6-2 | `4.1745e-8` top `(0,0,s)` / `5.8497e-9` bottom `(0,0,s)` | `9.1943e-8` | `1.2510e-6 / 9.2653e-6` | PASS |

逐级 R/T、所有通道分类、全局 R/T/A 与样本差值在[比较 JSON](records/d15_y5_1_y6_siblings_saved_output_comparison_20261021_v1.json)及[比较脚本](records/d15_y5_1_y6_siblings_saved_output_comparison_20261021_v1.py)。因此本计划停止继续加密 y，选 Y5-1 作工程候选；这些 y 对照不证明 z=6 格充分，也不构成连续网格收敛或 full-DtN 资格。

## 静态 z-only 候选

新候选内部标识为 `Y5_Z2`，展示为“D15-Y5-1 后 z 单轴细化”。父场是已完成的 Y5-1，而不是历史 H15-B/D15-Z2。候选只把 z 中段由 4 格改为 6 格；x/y 使用 Y5-1 实际保存的轴坐标，未从标量 h 重建。

| 轴 | 完整坐标（nm） | 材料段格数 | 各段步长（nm） | 轴 SHA256（little-endian float64） |
|---|---|---|---|---|
| x | `[0, 8.25, 16.5, 25, 33.5, 41.75, 50]` | `2/2/2` | `8.25 / 8.5 / 8.25` | `bb1d6be1e2cec153c7bd67a71e29f5967b3035b4928cd06f51ee2c0b6f2a5361` |
| y | `[0, 3.75, 7.5, 11.25, 15, 18.333333333333332, 21.666666666666668, 25, 28.333333333333336, 31.666666666666668, 35, 38.75, 42.5, 46.25, 50]` | `4/6/4` | `3.75 / 3.3333333333333335 / 3.75` | `c0961ba718983e4a2a1c376cd969324e57001f7147bb33d3ef35b06256c175b7` |
| z | `[-10, 0, 20, 40, 60, 80, 100, 120, 130]` | `1/6/1` | `10 / 20 / 10` | `82d51947444eb3e27d0678b92be099c1f86e7e42f5c5bfa5cefdb8ce4ea07d37` |

总计 `[6,14,8]` / `672` 个六面体。空气、基底、柱体材料面的 x/y/z 坐标均保留，端口 `z=-10/130 nm` 保留。独立按轴区间中点对几何分类得到静态 tag 计数 air/substrate/grating=`516/84/72`，总和为 672。z 新旧网格不嵌套：两者共同保留 60 nm，但旧 30/90 nm 节点未保留；因此这不是逐区间二分。静态几何步长比的最长/最短边比最大为 6，z 相邻步长比最大为 2；这些是轴算术，不是 live Jacobian、网格质量或容量证明。

父身份：Y5-1 run `20261021T115035.556208Z`，source `55c58972d230f53103f8ef6cb950ebb9417711cb`，input `362a796ebfabecffc675d338cd22f44fc959534bf2eb50895e24ab151a6fe4b5`，physical `1b2344a9a1fb010260e33982e3a64d0f7ccb874bda2e16c2a29c7446bd535ca1`，resolved `f34628a9487e6b16239fa747121cf8f5c78263106d46253e7f6ba377538801d3`。父 x/y/z 轴 SHA 分别为上表 x、y 及 `daf722948a31d19757622ba67544eeea6d49fdc2e433b979df9c11b2b450afb6`。候选 input `50347e8316620cc6070e003d01eb25d7a7b4d03e3da8431db069659e18249a99`、physical `60004a2f560019cab185432c622d2bbca47e375c42c0a5a37213014a0cf420ac`、resolved `7d3848846a24fbf54f989571bbdfc7b3a217a74a7ce0d2d0f22edd920dc3b777`；physical/resolved 身份随显式网格/route 改变，未声称与父哈希相同。

固定合同仍为 13.5 nm、p6 凝聚直接法、612 R13 modes（SHA `1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e`）、surface q28、volume q15/default、`scale_homogeneous_relative_only_v1`；单场凝聚/A6/能量门及比较三组门均不变。计划与输入见[静态 JSON](records/d15_y5_1_z_refinement_static_plan_v1.json)和[input dat](../../../input/task40para_phi90_mesh_modes_direct/d15_y5_z2_r13_p6_direct.dat)。

当前状态仅为 `STATIC_PLAN_ONLY_NOT_LIVE_MESH_OR_LAUNCH_AUTHORITY`：没有针对此 z 轴建立网格、运行 fresh 或启动 FE。后续须先审阅精确冻结包并重新核现场资源/锁/ABI；正式运行后仍须用 live 轴/hash、材料 tags、Jacobian、mode/q 与全部数值门验证。`FULL_DTN_NOT_VERIFIED` 和 canonical sidewall `NOT_MEASURED` 保持。
