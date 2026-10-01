# Task40extra：独立云端 DtN 模式与局部投影诊断

## 直接结论

1. 调用原 `outgoing_port_modes_3d`，母体 q=1 的 M0/M1/M2/M3 确认为 **80/180/340/532** 个合法通道。旧键按 `(side,m,n,polarization)` 是新清单的有序子序列，但不是数组前缀；不得按前80项对齐。
2. 固定0.7nm增大周期时，自动包络分别成为 q=1.25 的 **(9,2)**、q=1.5 的 **(11,2)**。依 Review V2 的“自动包络+1/+2”增长规则，母体 M2 对应新通道 **588/700**，母体 M3 对应 **828/972**。直接沿用母体上限会错误理解新模型：q>1 时请求 M1=(7,1) 和 M2=(8,2) 实际产生同一集合。
3. 补查生产源码后确认：**已有随模式增大的高阶端口积分规则，不建议盲目改成16×16。** 默认 `degree=max(10,2*p+max_order+6)`，q=1的M0/M1为degree25、M2/M3为degree26/27；当前Basix默认分别对应13×13和14×14 Gauss。所测真实p6迹×M3模式投影在14×14相对48×48误差最大 **2.252e-10**，13×13为8.674e-9，32-vs48约5.38e-14。没有发现此次局部测试需要提高现有默认积分阶的证据。8×8误差1.942%仅说明不能随意把体积规则拿来替代端口规则。**未运行完整生产端口装配，也未检查运行时override，因此仍需正式任务记录实际规则与固定模式一致性。**
4. 没有求解全局 PDE，没有测量 M1→M2 场/功率变化；**本实验没有授予 DtN 截断精度或2TB容量资格**。

## 模式清单与物理方向

| q | 原请求M0 | 原请求M1 | 原请求M2 | 原请求M3 | Review增长：M2母体 | Review增长：M3母体 |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 80 | 180 | 340 | 532 | — | — |
| 1.25 | 136 | 380 | 380 | 532 | 588 | 828 |
| 1.5 | 192 | 460 | 460 | 644 | 700 | 972 |

- 波长、Si复折射率、1°掠入射来自母体 `.dat`；正确换算为相对-z轴89°。周期乘q，波长和材料不变。
- 全部所测清单出射根 Re(beta)、Im(beta) 非负；未裁剪的出射 Poynting 密度非负。重新由 E×conj(H) 算出的通道功率与生成器数值最大绝对差4.44e-16。
- 归一化非共轭横向条件 `|k·E|/(||k||||E||)` 最大2.382e-16，符合浮点舍入尺度。原始逐模式E/H/k/beta、色散误差、功率、ordered keys均保存。
- 最小切向电场范数平方7.54548e-5，出现在 bottom 零级p；最小 `|beta|/(k0|n|)` 约0.00868648。均无源码默认 `rayleigh_tol=1e-6` 告警，也未触发切向范数平方≤1e-30的排除条件。这些是代码定义；并非本实验新设的验收阈值。
- q=1 M3 有226个被分类为非传播、但带正出射功率的底部有损通道。不能按“倏逝”名称把它们的功率字段手工清零；这里没有审计完整R/T求和链路。

## 衰减只解释机制，不估计截断误差

空气均匀顶缓冲真实厚度 `z_max−grating_height=0.5185185185nm`。q=1 最弱所含空气倏逝阶 `(-7,±1)` 的 Im(beta)=2.60104nm⁻¹，穿过缓冲的单程幅度因子 `exp(-Im(beta)d)` 约 **0.25958**。这说明近场成分未必在端口前消失。

q=1.25 最弱所含阶 `(-7,±2)` 的固定母体缓冲因子约0.64629；按Review把实际缓冲也乘q后为0.57948。q=1.5最弱所含阶 `(-11,±1)` 相应为0.24695/0.12272。原始JSON同时保留两种厚度，避免混淆。

以上仅是已枚举单个平面波的传播衰减，不含激发振幅、所有未枚举模式、反射耦合及解对边界的敏感性，**不是遗漏尾部上界，不可替代 M1/M2/M3 PDE 比较**。

## 局部投影实验定义与限制

- Basix0.11.0，N1E hexahedron degree6、Legendre变体；全882维基函数在z=0/1面的真实切向限制，每面84个非零迹函数。按轴对齐仿射单元的协变Piola缩放和物理面积积分。
- 使用G0真实x区间 `[0,0.4277777778]`、`[0.8555555556,1.2962962963]` 和真实y区间 `[0,0.3240740741]`，两参考z面共4组。
- 使用原生成器 top 模式 `(9,3),(8,2),(7,1),(-7,1),(0,0),(-1,0)` 的s/p共12个通道，积分 `exp(i alpha x+i gamma y)` 乘迹与极化。测试底参考面是同一迹空间的局部限制，**未冒充底部有损模式或全局端口装配**。
- 相对误差为每个通道的84系数投影向量2范数误差，另保存逐系数最大绝对误差；不是逐个近零系数作相对除法。
- 48×48为高阶数值参照，32×32与它的最大相对差约5.38e-14。该自收敛性支持此小实验，但不声称解析精确解。
- 未覆盖全部矩形/模式/q增长、全局方向/约束映射或完整生产端口实现。没有使用P3的0.3%场变化目标当此积分误差阈值，也未发明新的生产PASS门槛。

## 对大电尺寸/2TB目标的意义

模式增长不能只按母体80维估算：端口耦合通常至少随实际通道数增长；若具体实现含稠密模式块，该部分还可能平方增长。这里未导入完整端口实现、未测其分配生命周期，故不外推出2TB可容纳尺寸。已有源码默认规则随模式增长；正式运行仍应冻结实际ordered keys与override身份，再做P3截断与端口内存分账。

## 生产规则补查

只读获取同一commit的 [dtn_port_3d.py L1583–1600](https://github.com/Rookie1234567/MyFEniCS/blob/c786e87d03976a52f57d1e7f69a3c63f992afe90/src/solvers/dtn_port_3d.py#L1583-L1600)。其主模式装配路径L2951调用该规则，L3464–3473传入四个切向分量装配器，L1157把它注入UFL表面form。已单独抽取且执行这个纯函数，并用Basix默认quadrilateral quadrature核验点数，避免导入DOLFINx/PETSc。

q=1.25 Review增长集合默认degree28/29，对应15×15；q=1.5默认degree30/31，对应16×16。运行时若设 `stage4_dtn_quadrature_degree` 可覆盖规则；原dat未见这个字段，但完整runner运行时状态未核验。源码片段/完整blob身份/结果见 `production_port_rule.json`。

## 可复现性与来源

源码固定到 `c786e87d03976a52f57d1e7f69a3c63f992afe90`，来自母任务branch `task40extra_0p7nm_engineering`；权威要求见 [Review V2](https://github.com/Rookie1234567/MyFEniCS/blob/c786e87d03976a52f57d1e7f69a3c63f992afe90/docs/task40extra_0p7nm_engineering/review_report_v2.md)。

**字节身份披露：** 下载的20个文件每个均比Git blob多恰好一个终端LF。删除且仅删除最后一个LF后，20/20 Git blob SHA与manifest一致；未修改下载文件。JSON记录原manifest、实际本地SHA256、两种Git验证状态。Python数值内容未变化，但不把本地字节说成原blob完全一致。

复现（工作目录为工作空间根）：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 task40extra_cloud/.venv/bin/python task40extra_cloud/experiments/dtn_modes/audit.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 task40extra_cloud/.venv/bin/python task40extra_cloud/experiments/dtn_modes/trace_quadrature.py
```

`audit.py` 的纯生成器运行约1.02秒、单进程历史峰值RSS约49.8MiB；`trace_quadrature.py`约4.18秒、峰值RSS约279.0MiB。二者串行；数字为 `getrusage(RUSAGE_SELF).ru_maxrss`，不是整机/cgroup峰值。BLAS/OMP单线程，没有安装依赖、没有修改母源码/用户电脑、没有启动PDE。

交付：`audit.py`、`mode_audit.json`（全通道原始数据，仅云端保留）、`trace_quadrature.py`、`trace_quadrature.json`、`audit_port_rule.py`、`production_port_rule.json`、`compact_summary.json`、本说明、`artifact_sha256.json`。这些是独立研究证据，不替代正式Task40extra运行产物。

### 源包布局

本脚本有意不修改仓库数值核心。复现目录ROOT下放 `source_manifest.json` 及按manifest原path布局的 `source/`（固定上述commit）；脚本放 `ROOT/experiments/dtn_modes/`。可从对应Git commit检出这些文件，不需要保留下载额外LF；audit脚本支持精确原blob或恰多一个LF。`audit_port_rule.py`另需将同commit `src/solvers/dtn_port_3d.py` 保存为同目录 `dtn_port_3d.pinned.py`，按production_port_rule.json的blob SHA校验。先运行audit.py，再trace_quadrature.py及audit_port_rule.py。原始14MB模式JSON不适合提交；compact_summary.json删除逐模式向量和清单，仅保留计数/极值/嵌套/来源与原始文件SHA256。发布后文件布局不同不代表原实验代码路径自动可用，请按本节建立新复现包。
