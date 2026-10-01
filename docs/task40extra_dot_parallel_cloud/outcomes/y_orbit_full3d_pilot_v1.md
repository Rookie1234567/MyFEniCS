# V3：完整三维 y-orbit 参考逆的小型资格

## 结论与作用

本批真实小型三维 Maxwell 系统通过了全空间参考逆和非可分三维缺口外层求解。其方法把规则线光栅沿 y 重复的单元编号转换到四个离散频率块，对每块保留完整向量、电场边/面/单元内部基函数和全部端口别名。它只改变预条件器中的线性代数，并且仍由完整原始三维算子裁决残差；没有把问题替换成二维或 2.5D，也没有只保留 n=0。

**这是按 7/135 缩小几何、p2 的架构试验，不是原尺寸 50×25×140 nm 的解、物理精度或 2 TB/48小时资格。** 规则参考保留真实 x-z Si/air 光栅，不做材料平均。随后在同一三维网格开两单元空气缺口，真实入射场产生非零横向块，证明不会在缺口情形悄悄丢弃 y 模式。Si 的折射率差仍很小，不能从这一次 3/4 步推断强扰动或更大电尺寸鲁棒性。

## 实际系统与数学身份

| 项目 | 实际内容 | 数据身份/边界 |
|---|---|---|
| 物理 | λ=0.7 nm；真实 Si 指数 0.9998851703688496+4.3236152269189515e-6j；1° grazing，phi=0，S | inherited physical parameters；几何缩放为 7/135 |
| 网格/空间 | 4×4×5=80 三维 hexahedra；N1curl p2；2394 storage/2048 independent DoF | measured；其中 edge544、face1024、cell-interior480 |
| 原始端口 | manual m=-9…9、n=-3…3，共532；与 production generator ordered(side,m,n,pol)完全一致 | measured；不是端口截断精度资格 |
| y 块 | 4 个完整512行 FE块；端口 q0/q1/q2/q3 分别76/152/152/152 | measured；n=1 与 n=-3 在同q内仍各自保留 |
| 缺口 | scaled x25…33.5、y6.25…18.75、z40…80；实际改变2 cells | measured；不同 q 的 ΔA 耦合范数比例0.7062105515 |
| 几何精度 | 四个实际 y width 的十六进制表示相同；没有 metric roundkey/group averaging | measured；不推广到其他网格 |

采用 full-FE canonical orientation map R、全 y cell-index DFT F，以及 Q=RF。模态矩阵由完整原三维 FFCx/MPC volume matrix 加全部实际 streaming-DtN rank contributions直接转换得出。D的carrier值已经共轭一次；不能再共轭，也不能假设C=D的共轭转置。

```math
\widehat A_0=Q^H A_0 Q,\qquad \widehat b=Q^H b,
\qquad B_0b=Q\operatorname{diag}(\widehat A_{0,q}^{-1})Q^H b.
```

Q的原始moment部分不先验假设Euclidean unitary。原始几何平移按 `(Tu)(y)=u(y+h)`，绕回乘 `exp(i ky Ly)`；本批检查native `T^H A0 T=A0`、canonical shift unitary、translation cycle和primal/dual pairing。当前phi0的y wrap=1，非零ky未测。

每个物理端口n只按n mod Ny归入其离散块，块内保留实际gamma_n和所有高阶通道，不能把q解释成唯一连续Fourier阶次。真实增广系统使用 `[V C; -D H]`，并独立检查恢复的全部532端口闭合及其FE residual与完整原A residual一致。

## 数值结果

| 完整原三维系统/RHS | 方法 | 原A full true residual | 与同系统direct场相对差 | outer iterations | 数据身份 |
|---|---|---:|---:|---:|---|
| 规则A0 / generic complex、所有q和内部DoF | 4块完整参考逆 | 3.4914012131e-14 | 9.5480881508e-14 | 无outer | measured |
| 规则A0 / 真实incident | 同上 | 8.2936615906e-15 | 1.4738017675e-13 | 无outer | measured |
| 三维notch / generic all-q | full原A FGMRES，右PC为规则A0逆 | 5.2744404628e-15 | 9.4050585086e-14 | 4 | measured |
| 三维notch / 真实incident | 同上 | 5.8468972752e-13 | 5.0375542095e-13 | 3 | measured |

真实incident在规则A0的非零q只有roundoff；在notch场中q1和q3各约6.8875e-7，全部非零q相对primal norm为1.4217027193e-5。独立checker从保存的sparse F/R逆及完整场重新计算该比例，确认不是n0 projection。generic RHS四块dual norm为31.7009/32.2721/32.5534/31.3355；480个内部DoF明确保留。

| 实现身份Gate | 实际值 | 限值 | 结果 |
|---|---:|---:|---|
| regular/notch assembled matrix vs独立原FFCx form-action | 7.1248e-16 / 6.9607e-16 | 1e-11 | pass |
| native form covariance / modal off-block relative | 2.9662e-16 / 2.3539e-16 | 1e-11 | pass |
| modal off-block absolute maximum | 4.0247e-13 | diagnostic | 相对门及原A/direct控制同时通过 |
| port C/D别名off-q relative maximum | 1.1431e-14 / 1.1424e-14 | 1e-11 | pass |
| port C/D covariance maximum | 1.8801e-14 / 1.8789e-14 | 1e-11 | pass |
| 全部源augmented port closure maximum | 1.0698e-16 | 1e-10 | pass |
| primal/dual pairing / Fourier unitarity | 3.4375e-16 / 1.3559e-16 | 1e-12 | pass |
| 独立hash-bound checker | 12矩阵/direct residual检查＋all-q/aliases/nonzero-q | 原矩阵1e-10、场差1e-9 | pass |

## 资源、失败与测试

| attempt / 数据身份 | 终态 | whole-tree sampled RSS / swap | wall | 解释 |
|---|---|---|---|---|
| attempt1；source72b7ff523405411f5927031c5391cd3c47b784f5 | WORKER_FAILED | 695,042,048 B /0 | 20.436735303 s | regular inverse已完成；notch FGMRES的PC callback对PETSc readonly锁Vec请求可写array，API错误；不是数值负结果 |
| attempt2；source18d7d0a27f73705366f8cb747c11cb9e68cc0ef6 | COMPLETED | 638,885,888 B /0 | 8.839025935 s | 复用attempt1 JIT cache；不可称cold成功或端到端加速 |
| full dense A0 direct factor payload | measured | 67,117,056 B；不是RSS | factor+两源0.42 s左右 | 小型dense oracle |
| 全4块dense factor payload | measured | 16,785,408 B；不是RSS | setup0.935125355 s | 含完整转换/审计；更慢的prototype setup不掩盖 |
| sparse Q payload | measured | 178,756 B | — | 无dense Q；无±q factor reuse |

watchdog独立监督parent及全部后代、0.25 s采样，1.5 GiB/600 s/zero-swap/threads1；预算不是性能承诺。两attempt后代全部清场，source clean unchanged。最初一个source-string unit assertion错误单独提交修正；所有失败历史保留。最终focused含实际证据3 passed，compileall通过；full pytest、MPI2+、Ruff、CI、GitHub rendered view均not_run。每份original matrix、R/F/Q、RHS、direct/candidate vector的完整hash绑定raw report，compact保留轻量身份。

## 历史区别、容量路线与未解决项

旧Task040 corrected full-spectrum为人工上下接口的analytic TE/TM substrate符号加传播sweep，真实screen no-signal，不是规则异质x-z全三维离散A0的精确逆。相关B1背景逆已探索过：它将air/grating按17/50与33/50平均，使用双横向非均匀topological-orbit近似，并显式丢弃off-block coupling；formal S3停在shape/token/layer implementation Gate。故本批是已探索背景逆家族的结构性纠正/扩展，不宣称思想从未出现，也不把旧失败改判。

新路线只沿真正均匀y对角化，保留x-z异质结构及所有p内部通道，首先直接验证完整A0逆，再验证同配置非可分notch。历史入口为不可变[Task040 full-spectrum源码](https://github.com/Rookie1234567/MyFEniCS/blob/50897c0c62d1f35abed5b196ae17997b2e7521cc/src/solvers/hybrid_full_spectrum_screen.py)和[B1 config](https://github.com/Rookie1234567/MyFEniCS/blob/50897c0c62d1f35abed5b196ae17997b2e7521cc/src/solvers/floquet_background_hcurl_s3_pilot.py)。H(curl) orientation/非纯permutation背景见[Basix官方说明](https://docs.fenicsproject.org/basix/v0.10.0/python/demo/demo_dof_transformations.py.html)。

| 后续问题 | 现在能说什么 | 尚需什么 |
|---|---|---|
| 全3D能力 | 小scaled p2原算子＋nonseparable notch＋all-q真实通过 | 原尺寸、p/h/电尺寸压力证据 |
| 非零y Bloch | not_run | 同小网格phi5有界独立测试 |
| p4/p6 | not_run；不能把p2资格提升 | 真实高阶全原A残差、每块fill及总库存 |
| representative-y-cell生成 | not_implemented；当前先形成完整小A0再转换 | 对full-period C/D/H normalization和所有gamma_n alias逐块证明 |
| 稀疏factor容量 | 小dense payload降低约4倍仅属该oracle | 不能用于预测MUMPS3D fill；总factor=sum全部q，工作向量/局部cache/ports仍是full3D |
| 2 TB /48h | unknown；没有目标解或保证 | 新block fill/setup/backsolve、outer iterations、完整同时库存和物理精度 |

完整周期x/y、open-z均匀p空间的DoF为Nx Ny p²(3Nz p+2)；凝聚trace每y块为Nx[3Nz p(2p−1)+2p²]，再加入全部端口aliases。该式可校准历史G0 p4的7248×4+80=29072与G1的18800×4+80=75280，但没有证明未来所有blockfactor在2TB内。理想固定p/规则稀疏grid下，分块可能把3D因子成长改成2D-like总库存；真实DtN密集front、高阶bands和非均匀网格会改变该模型。

## 文件、复现与合并边界

- [compact记录](records/y_orbit_full3d_pilot_v1.json)绑定所有source、输入、raw hash、参数和失败
- [case计划/复现](../../../benchmarks/cases/task40extra_dot_parallel_cloud/y_orbit_reference/README.md)
- research core：src/solvers/task40extra_y_orbit_reference.py；runner/checker/test保持独立
- raw：benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_p2_attempt1/2；矩阵/完整场不入Git
- 只操作本独占分支；无raw git push、PR、merge、production default或用户电脑操作
- 下一步只有计划与独立审阅，不自动启动p4/p6/phi5或目标尺度计算
