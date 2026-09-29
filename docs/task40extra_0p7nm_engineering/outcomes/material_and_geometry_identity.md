# Task40extra 材料与几何身份

## 材料：0.7 nm 硅

| 字段 | 值 | 来源与资格 |
|---|---:|---|
| 真空波长 | `0.7 nm` | 固定输入 |
| 光子能量 | `1771.2028347600037 eV` | 由 `hc/λ` 推导 |
| Si 密度 | `2329.1 kg/m³` | NIST 材料数据换算，不是本样品测量 |
| CXRO 光学常数约定 | `n = 1 - δ - iβ`；`δ=0.00011482963115036948`；`β=4.3236152269189515e-06` | 原始散射因子表插值 |
| 求解器折射率 | `0.9998851703688496 + 4.3236152269189515e-06i` | 对应 `exp(-iωt)` 被动损耗约定 |
| 求解器介电常数 | `0.9997703539048498 + 8.646237495554417e-06i` | 由上述折射率平方得到 |
| 输入文件 SHA256 | `8e00fb6495845902a8113d982242d39ad0f4999b563c2c8049ecc3750b82ac9c` | `input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4.dat` |
| runner physical-model SHA256 | `51854af3fb60c7ffebb166e1f06ff0a89e2e184dcbd9ba06ab4beb321b920661` | `.dat` runner 的输入物理身份摘要 |
| composite physical-identity SHA256 | `ec0bd05df3c4531ccaadc3475d96b48cb7eebc6dc5aaa4cfe6aac95ebcfcc292` | 将几何、材料与模式身份合并的另一哈希范围；不能与 runner hash 混用 |

硅数据来自公开元素散射因子文件 `records/raw/si.nff`，线性按光子能量在相邻表格点间插值。插值区间没有跨越记录的吸收边；源数据、引用链接、插值行号和精度限制见 [`records/material_identity.json`](records/material_identity.json)。独立原子模型不是样品专属测量；对原子尺度特征的适用性仍有限。

## 几何与尺度

缩放 `s=7/135 nm=0.05185185185185185 nm`。物理单胞周期为 x=`50s=2.5925925925925926 nm`、y=`25s=1.2962962962962963 nm`；z 平面为 `-10s, 0, 40s, 80s, 120s, 130s`。三维空气缺口为 x=`[25s,67s/2]`、y=`[25s/4,75s/4]`、z=`[40s,80s]`，转换为 nm 后为 `[1.2962962963,1.7370370370] × [0.3240740741,0.9722222222] × [2.0740740741,4.1481481481]`。因此材料边界同时在三个方向变化。

| 网格 | 每轴区间数 | cells | 计划 SHA256 | 实测构建状态 |
|---|---:|---:|---|---|
| G0 | `6×4×14` | 336 | `d621678ed8f144246133a98a71a2805bf55d09104d3aa6ceeb55e3f16fb864f1` | G0 attempt 2 实际建成 336 cells；随后在 cleanup 的 audit 字段访问处异常退出 |
| G1 | `10×4×22` | 880 | `2e7e0a76c2161bfc0651c89d8c5e6edfa2a1ed37d1e2b5a674e314c6c5f5c27d` | 仅为 derived plan，未构建 |

几何 identity 为 `29b5839216ec96e4cdaaf7ffcf2418a6d61a0a61c731f387be2e4e3e33ec4d12`；G0 实际网格统计支持缺口平面与标签准备，但不能用它替代 G0 的完整物理求解。几何计划的坐标与分段逐项列于 [`records/geometry_plan.json`](records/geometry_plan.json)。

## 外部端口与有序模式

| 项目 | 值 | 资格边界 |
|---|---:|---|
| 水平入射 | 1° grazing、azimuth 0°、s polarization | 固定输入 |
| 两端口有序 keys | 上端 40、下端 40，共 80 | actual mode API 生成；G0 manifest SHA=`c3ff9c0cf35e2d183f44ed3fb7448d4aa586bb6fdf7f9dc9ba78dc25011c693a` |
| 每侧候选 lattice orders | 45 | derived/inventory |
| 每侧传播阶数 | 20 | 模式身份记录 |
| cutoff 警告 | 0（当前筛选候选） | 不等同截断收敛 |
| 截断收敛 | `CHANNEL_TRUNCATION_UNQUALIFIED` | 未做独立 cutoff study |

模式身份 SHA256=`40e80da12f352c80bf941aa5736c8910e69ea39e230afcf87737b2fbd92b8a78`。完整 ordered keys、上下端口统计及生成器见 [`records/mode_inventory.json`](records/mode_inventory.json)。

## 身份摘要

| 记录 | SHA256 |
|---|---|
| input `.dat` | `8e00fb6495845902a8113d982242d39ad0f4999b563c2c8049ecc3750b82ac9c` |
| material identity record | `5faedf276aba2918cc399c018936964b059127f135e24ea2bf2ba493e3d9876b` |
| geometry plan record | `6a6d56c894b2f15a96f0ac545f62df75ae63fb77a97525dbbb7c17f7702ebd87` |
| mode inventory record | `4d2223697dc302ef772279fabbc07dca09fbe5909ad09c64bfcfd037c6be7f3c` |
| N2 diagnostic record | `250060a0995be44c6918bc98bf7863870c0f046dad2d1dfb5876861e109c18ae` |
