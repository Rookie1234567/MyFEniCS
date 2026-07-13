# PML、Robin 与开放边界

## 1. 为什么需要截断

散射域在上下方向本来无界。有限元只能计算有限区域，必须用人工边界让向外传播的波尽量不反射。项目保留三类办法：PML、局部 Robin/阻抗、Fourier-DtN。

## 2. 复坐标 PML

以 z 向拉伸为例，令

$$\tilde z=\int_0^z s_z(\zeta)d\zeta,\qquad s_z=1+i\sigma(z)/k_0.$$

对 `exp(i*k_z*z)`，正虚部拉伸使出射波指数衰减。坐标变换 Jacobian `J=diag(1,1,s_z)` 给出

$$
\epsilon_{PML}=\det(J)J^{-1}\epsilon J^{-T},\qquad
\mu_{PML}=\det(J)J^{-1}\mu J^{-T}.
$$

3D `common/pml_3d.py::z_pml_tensors` 直接实现；`common_3d_forms` 在 curl 项使用 `mu_PML^{-1}`。2D TM 使用嵌入三维的同一变换，TE 标量弱式则使用

$$C=\det(J)J^{-1}J^{-T},\qquad \epsilon_{scaled}=\det(J)\epsilon.$$

对应 `common/pml.py`。

## 3. PML 不是材料吸收

PML 是坐标变换后的数值层，不能计入物理 `A_volume`。`rta_3d` 只积分 substrate/grating tag，并显式排除 air/PML。PML 中 total/background 场可能因解析延拓出现大模值；应检查 scattered/correction 场衰减和物理区反射，而不是单看 PML 内 `max|E_total|`。

## 4. Robin/阻抗边界

局部零阶出射近似把边界 traction 与切向场关联：

$$\mathbf n\times\mu_r^{-1}\nabla\times\mathbf E\approx -i k_0 n\,\mathbf E_t$$

（符号随外法向和弱式移项）。`common_3d_forms` 在上下表面增加 `i*k0*n <E_t,v_t>`；2D TE/TM 端口也有相应零阶 Robin 项和入射源。

Robin 只精确匹配一个局部平面波近似。周期光栅有多个横向衍射级时，各级纵向波数不同，因此不能把 zero-order Robin 当多模精确端口。

## 5. DtN 的位置

DtN 按每个 Fourier 模态使用自己的纵向波数和极化 admittance，是本项目 Stage 4 的正式开域路径。它无需 PML，但边界算子非局部。详见 `dtn_modal_ports_and_condensation.md`。

## 6. 三者比较

| 方法 | 优点 | 风险 | 当前用途 |
|---|---|---|---|
| PML | 保持体积分局部，适合复杂波 | 厚度/强度/网格/外边界误差 | 2D scattered、Stage 2B/C 诊断 |
| Robin0 | 稀疏、便宜 | 多模与斜入射近似差 | 历史/诊断 |
| Fourier-DtN | 均匀周期端口上逐模精确 | 非局部、Rayleigh 根号与增广耦合复杂 | 2D DtN、3D Stage 4 正式路径 |

## 7. 验证

PML 至少扫描厚度和 alpha；Robin 与 DtN 做平层解析对照；DtN 检查传播级、trace/auxiliary 一致性和 RTA。PML 原始思想见 Bérenger 论文 <https://doi.org/10.1006/jcph.1994.1159>，坐标拉伸解释可参见 <https://doi.org/10.1109/75.366461>。
