# 方法与论文映射

网络输出连续坐标场，再用有限元的完整积分矩把它变成离散电场。这样残差审核仍针对原有限元方程，网络负责限制可达的系数集合。Riesz 度量用正定 H(curl) 内积衡量残差，代价是另一个稀疏辅助系统的因子与求解；直接优化 FE 系数的 FREE 对照用于区分度量收益与网络收益。

| 论文/合同概念 | 本轮实现 | 边界 |
|---|---|---|
| [兼容 FEINN 论文](https://arxiv.org/html/2411.04591v2) §2.2.1、2.3–2.5 | 坐标网络经完整 Nédélec 矩插值；原 FE 残差 | 同一 p3 全测试空间；不是论文低阶 refined test 的复刻 |
| §2.7、2.9、3.1、3.2.2 | 对偶残差思想和有界优化/梯度验证 | 论文正定模型及 Dirichlet 问题与此处复数不定开放散射不同 |
| 初始化 | 隐层固定seed、最后一层零 | 不采用目标 FEM 拟合或监督 teacher |
| 全矩 | 每cell边36、面72、内部36；Piola及方向变换 | 所有独立系数有唯一owner，内部矩由网络产生 |
| 周期 | 原双Floquet MPC的复相位展开一次 | 不给网络额外每DOF embedding |
| 背景 | 已知 layered 解析背景的原FE仿射换元 | 非目标准确解；不把开放边界改成零Dirichlet |
| 端口 | 原块为 `[V B; -D H]`，H为正对角表面归一化 | 只消去端口；没有体内物理恢复或p4逆 |
| Riesz | 材料无关 mass +25 nm² curl-curl；一次MPC投影 | RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR；不声称无全局因子 |
| 网络架构 | 3→64→64→64→6，tanh，8966实参数 | 固定单seed；不扩容、加carrier或扫描 |
| 微分 | 原 Aᴴ作用后按最多8cell重算图的实参数VJP | 无全Jacobian，无伴随方程求逆 |
| 研究判断 | EUC、DUAL、FREE同预算、同原方程/场/功率Gate | loss数值不能直接跨度量比较 |

```math
\alpha=\mathrm{solve}(H,g_p+Dc),\quad A=V+B\mathrm{solve}(H,D),\quad f=g-B\mathrm{solve}(H,g_p).
```

```math
L_E=\frac{r^*r}{2f^*f},\quad Gq=r,\quad L_D=\frac{r^*q}{2f^*G^{-1}f},\quad r=Ac-f.
```

候选只存原局部未凝聚张量、稀疏约束展开及完整端口作用，不存 global A CSR，不形成 AᴴA。准确 Maxwell 因子只允许在全部候选冻结后的独立参考阶段；参考不得反馈训练。小型 M5 的成功或失败均不能直接推断目标尺寸5 nm或0.7 nm资格。
