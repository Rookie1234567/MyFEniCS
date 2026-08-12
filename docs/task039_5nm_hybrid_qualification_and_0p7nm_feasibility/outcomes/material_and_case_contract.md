# Task39 T0：材料与算例合同

本文件冻结后续解析和资格化所使用的输入身份。它只定义一个可审计的有限
profile，不开放任意物理扫描；所有正式数值结论仍需后续阶段的独立 Gate。

## 1. 5 nm 固定物理合同

| 项目 | 冻结值 | 说明 |
| --- | --- | --- |
| wavelength | `5.0 nm` | dat 的公开输入；resolved config 必须保留单位和值 |
| x/y period | `period_x=50 nm`、`period_y=25 nm` | 一个周期单元为 `50 × 25 nm` |
| outer z coordinates | `z_min=-10 nm`、`z_max=130 nm`、`interface_z=0 nm` | 坐标身份必须保留，不能只写总厚度 |
| air/substrate geometry | `air_height=130 nm`、`substrate_thickness=10 nm` | 由 `interface_z=0` 与 outer z coordinates 对应 |
| grating geometry | `width_x=17 nm`、`width_y=25 nm`、`height=120 nm` | 真实 rectangular block grating 的参与物理尺寸 |
| derived axial extent | `z_max-z_min=140 nm` | `140 nm` 是派生总轴向尺寸，不替代 z 坐标身份 |
| Hybrid interfaces | `bottom=10 nm`、`top=110 nm` | 独立于 outer Stage4 interface；不能由旧 13.5 nm profile 覆盖 |
| discretization | `p=6`、`h=10 nm` | Phase A stress anchor；`h / wavelength = 2`，不是 5 nm 最终离散精度答案 |
| incidence | grazing `10°`，等价 `theta=80°`；`phi=0°`；polarization `S` | 入射幅度和角度派生值必须进入 resolved provenance |
| materials | `n_air=1`、`mu_r=1`；grating 与 substrate 使用同一个复材料 | 不把 material identity 简化成旧 preset 名称 |
| boundary | x/y dual Floquet；vertical DtN auto-propagating；无 PML | 动态 DtN mode selection 由波数、材料和边界条件决定 |

## 2. 材料输入与派生

正式 dat 的独立物理材料输入只有复折射率 `n`；`delta` 和 `beta` 是本合同中对该
`n` 的 provenance metadata，不是额外的独立 dat 键。`epsilon_r` 必须由 resolved
mapping 对 `n` 求平方得到，不能要求用户同时维护两份可能矛盾的材料常数。固定
provenance 数值为：

```math
\delta = 0.00603145547, \qquad \beta = 0.00435380777
```

```math
n = 1 - \delta + i\beta
  = 0.99396854453 + 0.00435380777i
```

```math
\epsilon_r = n^2
  = 0.9879545118729887 + 0.00865509594462061i
```

其中正虚部是输入材料的约定符号；不得为了让某个闭合或残差数值看起来更好而
翻转符号。后续 `resolved_config.json` 和 manifest 至少应同时保留：

| provenance 字段 | 要求 |
| --- | --- |
| `delta`、`beta` | 与选定 `n` 对应的 provenance metadata 及单位/标签，不作为第二份独立材料输入 |
| `n`、`epsilon_r` | 复值的输入与 `n²` 派生结果 |
| `wavelength_nm` | 与材料和波数使用同一单位 |
| material labels | air、grating、substrate 的角色；grating/substrate 同值但角色不丢失 |
| source/input/physical/resolved hashes | 绑定实际 dat、解析结果、源码和运行目录 |

## 3. 运行身份与可比较性

- 一个 dat 只描述一个 run；method、solver profile、MPI size、输出选择和资源门槛
  都来自文件，不能使用隐藏 CLI override 改变物理身份。
- `M120` 在文档中表示 Hybrid 中部 QEP/内部模态每个传播方向保留 120 个。它是
  一次显式算法压力锚点，不是 external DtN mode count、连续介质收敛、mode-count
  convergence 或 production default 的同义词。
- 所有 DtN order keys、传播/衰减判定、Rayleigh 或 near-cutoff warning 都必须
  来自动态枚举器；reporting bound 只能影响后处理报告，不能偷偷改变 outgoing PDE modes。
- 既有 Task37/37b/37c accepted path 的结果可作为继承证据，但不同材料、波长、
  角度、M 或 source SHA 的数值不能直接冒充 Task39 fresh authority。

## 4. 阶段与 0.7 nm 边界

| 阶段 | 允许的结论 | 明确不允许 |
| --- | --- | --- |
| Phase A | `p6/h10`、5 nm wavelength 下的 algorithmic stress anchor；重点是 profile、operator、provenance、residual 和资源接线 | 把 `h/lambda=2` 写成 5 nm 最终网格精度或 continuum convergence |
| Phase B | 只有在材料、解析、source/hash 和前一阶段 Gate 满足后，才进入条件化的 5 nm qualification | 省略失败的前置 Gate，或把历史 13.5 nm record 直接复用为 5 nm 结果 |
| 0.7 nm | 材料常数尚不完整时只允许 component-only feasibility；缺失标记为 `0P7NM_MATERIAL_INPUT_INCOMPLETE` | 完整 Maxwell PDE、Hybrid qualification、资源结论或 production claim |

后续第一次出现的 static condensation、matrix-free DtN、Woodbury 和 M120 均应沿用
上面的通俗边界：它们是降低系统存储/迭代成本的既有计算步骤或有限规模参数，
不是新物理、自动扫描器或可隐藏输入覆盖的机制；external DtN modes 仍由实际物理
动态枚举，significant channels 只用于报告。
