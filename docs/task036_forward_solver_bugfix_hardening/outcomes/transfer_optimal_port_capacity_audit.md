# Task036 T0a：transfer-optimal port 精确离散定义

状态：`design_frozen / T0b_not_run`。这里只冻结离散设计，不含capacity结果、实现或forward PDE。权威为 [`review_report_v5.md`](../review_report_v5.md)、[`exact_cauchy_port_operator_audit.md`](exact_cauchy_port_operator_audit.md)、[`one_cell_discrete_bloch_audit.md`](one_cell_discrete_bloch_audit.md) 与 [`a004_exact_cauchy_port_audit_v1.json`](../../../benchmarks/cases/099_strong_trace_hybrid_fixture/records/a004_exact_cauchy_port_audit_v1.json)。

## 1. 身份与区域

V5事实：actual core-facing ports为`z=10/110 nm`，physical/external DtN faces为`z=-10/130 nm`，material interface为`z=0`，M120 core跨`[10,110]`的100 nm。T0a只取bottom `Omega_b=[-10,40]`（`Gamma_phys=-10, Gamma_H=10, Gamma_cut=40`）和top `Omega_t=[80,130]`（`Gamma_cut=80, Gamma_H=110, Gamma_phys=130`）。`40/80`只是冻结的oversampling cut/failed-I2负对照，不是actual interface；不扫描、不退回`30/90`。

Floquet identification、frozen 13.5 nm wavelength/material、`p5/h10/Ny4`及actual `(6,4,14)` mesh identity继承one-cell authority与compact record。one-cell的`zeta in [0,10]`不是global z。每端面有1250个original rows、Floquet独立`N_Gamma=1200` active rows；两种编号不得混用。所有T0b量当前均为`not_run`。

## 2. Source、actual auxiliary DtN与线性map

双z-face Dirichlet会与横向Floquet形成闭周期腔，故撤销为主方案。每侧保留actual auxiliary DtN，source固定为两个不同face/坐标的Hilbert直和

```math
s=(\eta_{cut},a_{in})\in\mathbb C^{1200}\oplus\mathbb C^{48}.
```

`eta_cut`是`Gamma_cut`完整Floquet-active weak-conormal dual load，cut不另加E Dirichlet。`a_in`是`Gamma_phys`上与现有48个external DtN channels配对的incoming Maxwell companion amplitudes；bottom即使actual A004全零也覆盖48维，top也不缩成唯一入射。physical face只施加“DtN + incoming load”，不施加Dirichlet；固定incident affine项提升为`a_in`坐标，零source对应零RHS，constant offset不得进入SVD。

按 `src/solvers/hybrid_local_dtn.py` 冻结FE/auxiliary块：

```math
\mathcal A_s=\begin{bmatrix}K_s&-T_s\\-P_s&D_s\end{bmatrix},\qquad
\mathcal B_s=\begin{bmatrix}L_{cut}&F_{in}-T_sP_{in}\\0&0\end{bmatrix}.
```

`F_in`为incoming weak traction，`P_in`为incoming E trace到auxiliary total-coordinate的投影。令实际送入active求解坐标的净incoming load为

```math
L_{in,s}:=R_{ext,s}(F_{in,s}-T_sP_{in,s})\in\mathbb C^{1200\times48},
```

其中`R_ext`含同一Floquet/orientation及right-Schur active-row restriction。`mathcal B_s`的full-FE列与`L_in,s`是同一净载荷的不同坐标表示；`L_cut`和全部incoming列均遵守`reduce_surface_vector(role="load_column")`。当前helper只实现actual plane wave；48个companion columns须在T0b构造，仍为`not_run`。

```math
G_{S,s}=(A_\Gamma|E_{ref}|^2)^{-1}\operatorname{diag}
\left(k_0^{-2}M_{cut}^{-1},\ k_0^{-2}L_{in,s}^HM_{ext}^{-1}L_{in,s}\right).
```

inverse只作SPD solve/action。T0b须证明incoming Gram为SPD并whiten；失败即T0 fail，无fallback。

## 3. Joint-Cauchy output、conormal与方向

输出`y=(e,q)`：`e`为target切向E active系数；`q`为同一harmonic state在**物理endcap侧**的one-sided Schur row，不是整个oversampling系统在内部target的零总residual：

将actual physical endcap按target `H`与其余`c`分块；对48个incoming RHS columns，

```math
S_H=A_{HH}-A_{Hc}A_{cc}^{-1}A_{cH},\qquad
f_{H,in}=B_{H,in}-A_{Hc}A_{cc}^{-1}B_{c,in},\qquad
q=S_He-f_{H,in}a_{in}.
```

cut load只经oversampled solve改变`e`，其physical-endcap direct block为零；零source仍给出零RHS。bottom/top及canonical orientation遵守下述同一合同。令`x=\mathcal A_s^{-1}\mathcal B_s s`，并令`E_Hs`的electric block为零、traction block仅为`-f_{H,in}a_{in}`，则完整线性transfer为

```math
y=C_Hx+E_Hs,\qquad
\mathcal T_s=C_H\mathcal A_s^{-1}\mathcal B_s+E_H.
```

`C_H`的electric row提取`e`，traction row包含`S_He`；source依赖不得藏入`C_H`。

```math
\tau=(\mu_r^{-1}\operatorname{curl}E)\times n_{local},\qquad
v^Hq=\int_{\Gamma_H}\tau\cdot\overline{v_t}\,ds .
```

代码当前返回`curl(E) x n_local`；A004的`mu_r=1`与通式等价。bottom取`[-10,10]`在z=10的outward `+z`，top取`[110,130]`在z=110的outward `-z`；若统一到`+z` canonical方向，top q显式翻转，row/orientation map完成后才可比较。

`q`是积分后的dual load。定义Riesz代表`t_h=M_Gamma^{-1}q`；在`exp(-i omega t)`下

```math
t_h/k_0=i\Pi_h(H_{norm}\times n_{local})=-i\Pi_h(n_{local}\times H_{norm}),\qquad
t_{h,SI}/k_{0,SI}=i\eta_0\Pi_h(H_{SI}\times n_{local}).
```

## 4. 3D mass、metric与解析fixture

T0a选择3D端面mass，不直接复用恰为1250维的2D canonical mass：

```math
B_\Gamma[i,j]=\int_\Gamma\phi_{j,t}\cdot\overline{\phi_{i,t}}\,ds,\quad
C_\Gamma\in\mathbb C^{1250\times1200},\quad M_\Gamma=C_\Gamma^HB_\Gamma C_\Gamma .
```

`B_Gamma`按frozen p5 affine face/qdeg14在1250个original H(curl) rows装配；`C_Gamma`为`TraceConstraintMap.expansion_by_original`限制到端面的稀疏Floquet expansion。未来复用2D mass须另有有向DoF map `J` fixture；本设计不作该选择。

```math
G_C=(A_\Gamma|E_{ref}|^2)^{-1}
\begin{bmatrix}M_\Gamma&0\\0&k_0^{-2}M_\Gamma^{-1}\end{bmatrix}.
```

`A_Gamma=1250 nm^2=1.25e-15 m^2`，`k0=0.46542113386515455 nm^-1`，`eta0=376.730313668 ohm`，`E_ref,code=1`，`E_ref,SI=1 V/m`。该缩放来自Maxwell E/H阻抗与Riesz关系，不是经验权重或旧electric/traction Frobenius归一；inverse不得显式形成。

T0b必须先通过：mass identity/Hermitian/SPD；homogeneous S/P Schur-q及bottom/top sign；incoming direct term；nm↔m与Eref重标不变；含`E_H`的完整weighted-adjoint identity；DtN+incoming/cut-load无重复BC且harmonic residual/solve backward error闭合。任一失败即T0 fail，当前均`not_run`。

## 5. 可执行adjoint、singular pair与decoder

lossy/non-Hermitian adjoint用完整增广块：

```math
\mathcal A_s^Hz=C_H^HG_Cy,\qquad
\mathcal T_s^*y=G_{S,s}^{-1}\left(\mathcal B_s^Hz+E_H^HG_Cy\right) .
```

每个`z_i`是同一`T/T*` singular pair的volume adjoint field，其target adjoint Cauchy trace形成`W`；不得另选heuristic left modes或用right共轭。归一化为

```math
\mathcal T V=U\Sigma,\quad \mathcal T^*U=V\Sigma,\quad
V^HG_SV=I,\quad U^HG_CU=I.
```

未白化bases按同一pair双边whiten：

```math
W^HG_CR=U_w\Sigma_wV_w^H;\quad
R\leftarrow RV_w\Sigma_w^{-1/2},\quad W\leftarrow WU_w\Sigma_w^{-1/2}.
```

随后检查`W^HG_CR=I`、inf-sup及joint-Cauchy decoder

```math
D_C=(W_C^HG_CR_C)^{-1}W_C^HG_C,
```

白化后`D_C=W_C^HG_C`，必须有`D_CR_C-I=0`至冻结容差。现有electric-only decoder只能另记`D_E`，不得混称`D_C`；left/Petrov不增加primal列数。

## 6. M120 complement与local Schur

每port joint state为`2N_Gamma=2400`。M120 primal space为120 forward加120 reciprocal-backward Cauchy columns，即240列，不是120或480。既有two-end/global directional basis为240列、`rcond=1e-10`下秩240；T0b须在最终`G_C`下分别重测bottom/top rank、Gram、whitening，不把历史重放写成capacity结果。

```math
H_c=R_c^HG_CR_c,\quad \Pi_{core}^C=R_cH_c^{-1}R_c^HG_C,\quad
\mathcal T_\perp=(I-\Pi_{core}^C)\mathcal T_{buffer}.
```

这里`\mathcal T_{buffer}`是第3节每侧完整的`\mathcal T_s=C_H\mathcal A_s^{-1}\mathcal B_s+E_H`，不是只含第一项。`H_c`只用稳定solve；correctors只补M120遗漏方向，不替换、重选或重新传播scalar-CG core。令`a`为actual retained/core unknown，`c`为端部local corrector：

```math
K_{eff}=K_{aa}-K_{ac}K_{cc}^{-1}K_{ca},\qquad
\Delta K=-K_{ac}K_{cc}^{-1}K_{ca}.
```

## 7. Native→common比较、working set与停止语义

对`m in {candidate,30/90,40/80}`冻结

```math
\mathcal T_m^{common}=Q_m\mathcal T_m^{native}J_m .
```

共同source为physical 48 incoming加frozen 40/80 cut dual loads；共同output为actual 10/110 joint-Cauchy canonical坐标。`J_m/Q_m`只能由qualified one-cell Schur、scalar-CG propagation、orientation maps组成，不插值、不直接相减异坐标矩阵。candidate必须是`M120+r`经local Schur后的effective operator，不是raw `T_buffer`；30/90用frozen one-cell/M120段延伸到共同40/80 cut，40/80使用native cut。任一map不可构造、非满秩或metric不一致即T0 fail；T0b record只绑定现有authority identity，不另建hash framework。

anti-equivalence使用两个probe空间：retained/core metric白化的`X_a`检查`||Delta K X_a||`；共同`G_S`白化的`X_s`检查`||(T_candidate^common-T_40/80^common)X_s||_C`及dominance。两者分别计算solve/estimator uncertainty；上述量须高于各自uncertainty，且candidate exact action/Cauchy error须以高于uncertainty的margin严格小于30/90和40/80，否则`TRANSFER_OPTIMAL_PORT_CAPACITY_FAIL`。

谱审计只用`G_S`-whitened blocked randomized range/adjoint action及独立holdout概率误差界；fixed seed、block size、failure probability写入T0b record，不形成full transfer matrix或框架。瞬态`O(N_Gamma b)`，small dense至多`O((2M+r)^2)`；禁止`O(N_Gamma^2)` square、production常驻`N_Gamma x r`及跨100 nm global corrector。分别求tail`<=1e-8`的最小`r_b/r_t`，production固定`r=max(r_b,r_t)`；`r`在PDE前冻结，actual后不得调参。

T0b完整报告：bottom/top singular values、cumulative energy及`1e-6/1e-8/1e-10` ranks；endpoint和11 planes的electric/traction/joint max+aggregate；exact/core-facing action；Gram/inf-sup；localization/decay depth；rows/NNZ/peak及阶段耗时。未测值不得写pass。

只有V5全部Gate通过才进入T1：tail、frozen A004 joint-Cauchy max residual及action error均`<=1e-8`；解析fixture、`D_CR_C-I`、Petrov、orientation、Gram/inf-sup通过；current M120、same-dimension QEP reselection、M120+r三者比较及共同坐标dominance通过；rank预冻结；无global corrector/full square/resident大块；预计rows`<26256`、NNZ`<16512096`、peak`<=0.85*Full3D`且zero-swap。任一失败统一记

```text
TRANSFER_OPTIMAL_PORT_CAPACITY_FAIL
```

随后停止：不写正式solver、不跑A004-S、不改变rank/metric/buffer、不扫描或自动换路线。
