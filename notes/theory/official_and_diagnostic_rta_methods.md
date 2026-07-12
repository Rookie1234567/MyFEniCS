# Official 与 Diagnostic R/T/A

## 1. 功率定义

时间平均 Poynting 向量：

$$\langle\mathbf S\rangle=\frac12\operatorname{Re}(\mathbf E\times\overline{\mathbf H}).$$

以入射功率 `P_inc>0` 归一化：

$$R=P_{ref}/P_{inc},\qquad T=P_{trn}/P_{inc}.$$

有损材料体吸收：

$$P_{abs}=\frac{\omega\epsilon_0}{2}\int_{\Omega_{loss}}\operatorname{Im}(\epsilon_r)|E|^2dV,
\qquad A_{volume}=P_{abs}/P_{inc}.$$

代码单位中公共常数消去，3D 使用 `0.5*k0*Im(epsilon_r)*|E|^2`。只积分 substrate/grating 物理 tag，不积分 PML 或空气。

## 2. 两个吸收量

$$A_{balance}=1-R-T,$$

来自端口功率余量；`A_volume` 来自独立材料体积分。理想离散下

$$R+T+A_{volume}=1,\qquad A_{balance}-A_{volume}=0.$$

前式通过不代表网格收敛，因为同一离散误差可能在守恒式中相消；仍需跨 h 比较 R/T/A 和场量。

## 3. 方法等级

| 方法 | 来源 | 当前角色 | 主要风险 |
|---|---|---|---|
| DtN auxiliary modal amplitudes | 增广未知量 a | 3D Stage 4 official R/T | 模态法向、归一化、order 集 |
| DtN boundary trace projection | FE 边界迹 | independent check | 投影积分与边界 orientation |
| E-only Fourier | E 采样系数 | diagnostic | 方向分离不足 |
| E/H modal fit | 平面采样最小二乘 | diagnostic | 条件数、探针位置、采样 alias |
| sampled net flux | 平面 E/H Poynting | conservation diagnostic | 含混合向上/向下分量 |
| volume absorption | 损耗体积分 | official A | 必须使用 total field 与正确材料 tag |

2D `power_metrics.py` 同时输出多套量；3D `dtn_port_3d._port_power_metrics` 形成 port official，`rta_3d.compute_volume_absorption_3d` 形成 official A，`diffraction_3d` 的采样方法保留为诊断。

## 4. 衍射级功率

传播级的纵向 beta 具有可传输实功率；倏逝级平均法向功率为零。总 R/T 是所有传播 order 和极化功率求和，不是只取 `(0,0)`，除非物理/周期保证其余级截止。Rayleigh 附近功率因子趋于零且分类敏感，记录必须保存 tolerance 和 order 表。

## 5. total field 与 scattered field

- 顶端：total field 包含已知入射波，反射振幅必须扣除入射分量。
- 底端：通常 total field 的向下分量是透射波；若背景分解不同，必须跟随该 formulation 的定义。
- `A_volume` 永远用 total field；scattered field 单独积分会漏掉背景与干涉吸收。

## 6. 法向和符号

top 外法向 `+z`，bottom 外法向 `-z`。代码将“离开计算域”的 top-up 与 bottom-down 都转成正 R/T 功率。若直接对两个平面用同一个坐标方向，会把底端透射记成负值或伪造全反射。

有耗端口还多一条规则：传播模态的 `beta` 本来就是复数，不能用 `Im(beta)=0` 作为传播判据。代码用 `Re(beta)>0` 与 `Re(beta^2)` 区分有耗传播级和截止倏逝级。功率必须使用**实际端口平面上的 Fourier 系数**；把底端系数乘复传播因子反向搬回界面会人为去掉有限基座中的衰减，并与 `A_volume` 重复计数。

## 7. 输出审计

读取一个结果时按顺序检查：

1. `power_source` 与 `role`；
2. 入射功率是否正且非零；
3. order/polarization 列表；
4. R、T、`A_balance`、`A_volume_total`；
5. `energy_closure_error_port_volume`；
6. auxiliary 与 trace 差；
7. probe/flux 仅作解释，不覆盖 official。

## 8. 特殊案例

| 案例 | 预期 |
|---|---|
| 零对比、无损 | `R≈0,T≈1,A≈0` |
| 无损平界面 | 数值 R/T 对 Fresnel 且 `R+T≈1` |
| 复材料平层 | `A_balance≈A_volume>0` |
| 有损光栅 | `R+T+A_volume≈1`，并报告光栅/基座分项 |

旧文档 `reflection_transmission_metrics.md` 和 `THEORY_RTA_AND_VOLUME_ABSORPTION.md` 保存更早推导；本文件是当前字段口径。
