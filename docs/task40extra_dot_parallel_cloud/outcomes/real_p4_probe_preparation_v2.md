# V2：真实三维 G0 p4 算子导出完成

## 结论与用户最新目标

**已在 dot 独占云端分支生成并独立核验真实三维 G0 的 p4 凝聚矩阵、真实80端口、入射RHS及完整恢复映射。未执行全局因子、完整场求解或official功率。** 新数据可以支持后续全局因子研究，不再需要用人工矩阵或单单元代理猜测它的行为。

用户最终要求保留完整三维求解器，包括未来三维缺口能力；不接受二维/2.5D替代交付。近期基线是原尺寸50×25×140 nm的规则无缺口结构、波长0.7 nm，整机物理内存约2 TB、每次求解≤48小时；72小时研究窗口截至2026-10-04 10:07:14 UTC。本轮G0是较小、有三维缺口的真实三维算子诊断，不能把它冒充原尺寸目标成功。

## 方法和实际矩阵

单元凝聚先消去每个单元内部的未知量，只解相邻单元共享边界和开放边界端口，再恢复完整场，以局部缓存换取较小全局系统。新research入口调用原mesh/MPC、FFCx、DtN、RHS和恢复算法，没有修改原production数值文件或ordinary default。

| 对象 | 实际结果 | 数据身份/边界 |
|---|---:|---|
| 三维网格 | 336 cells，真实双Floquet，三维材料缺口 | measured；G0小系统，不是目标尺寸 |
| p4局部尺寸/缓存 | 300=108内部+192迹；33原始材料/几何类，67方向类 | measured；不是p6的450/432维 |
| 凝聚矩阵 | 29,072×29,072；10,912,592 stored NNZ | measured；28,992独立迹+80端口 |
| 原p4场存储 | 69,856 rows | measured；不是全局因子行数 |
| 原CSR载荷 | 218,368,132 B；complex128值+int32列索引/行指针 | measured array sizes；262,134,792 B仅是int64口径派生量 |
| RHS | 原p4物理入射RHS norm=1.2111002092943222；凝聚RHS另存 | measured；不是保存的BAL_H粗修正RHS |
| 恢复与端口 | 67局部恢复类、336单元映射；完整Bi/Di/XiB、MPC与DtN carrier导出 | measured；共1,486 arrays、301,167,184 B |
| 矩阵内容身份 | 2753cbe26f4e88127a26d03f521d8b67589eee9913b5b67c92d2e18d9066ceea | PETSc owned-row streaming SHA256；非稠密gather |
| 独立导出核验 | 全1,486个文件hash/dtype/shape通过；CSR严格排序、无重复、全值有限；exact-zero entries=0 | measured；没有进行零删除或近似截断 |
| 同时树RSS峰/实际cap | 1,199,104,000 B / 4,020,740,096 B | measured；独立subreaper parent+全后代，非对象累计 |
| 全流程时间/swap | 136.742108491 s / 0 B | measured；含监督内JIT/装配/导出/清理；后代全部清场 |
| 全局solve、原A4残差、official R/T/A | not_run | 没有全局因子或完整场；不能填假通过 |

实际source为c619854a371fdb3330d21747a53a440dd1d427ae；输入SHA为6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e。采用exact mesh-width cache，不能宣称与历史legacy-rounded p4 CSR逐字节相同。真实体积规则由p6 UFL符号空间分析得到15/15；没有构造p6 DOLFINx空间、action、KSP或factor。真实DtN表面积分degree25。

## 模式身份：保留一次真实失败，不冒充历史hash

第一次命名装配在80-mode full-manifest hash Gate停止。其336-cell mesh/MPC和p4 action已创建，但没有生成凝聚矩阵。RSS699,330,560 B、24.55900122秒、swap0；错误分类保留为WORKER_FAILED。

历史PDE报告的c3ff9c0cf35e2d183f44ed3fb7448d4aa586bb6fdf7f9dc9ba78dc25011c693a背后的完整raw manifest不在当前云端，因此两hash差异原因unknown，不能武断称为平台末位浮点差异。新完整manifest为de0e4b79e8ec0741db4e4b08f2f2ce97e78026d18e1c6795da7d6ddd5f3d9ed8，采用原fullspace_dtn_action的ASCII、sorted keys、compact JSON、complex={real,imag}完整schema/profile/count/modes序列化。

| 独立模式Gate | 实际结果 |
|---|---|
| 80个(side,m,n,polarization)、顺序、整数index、传播/Rayleigh flags | exact match |
| 对已hash-bound的独立M0 raw审计：alpha/gamma/beta/E/H/k、切向norm、power | 每项最大absolute/scaled差均0 |
| 预先批准的generator-roundoff限值 | 64×float64 epsilon=1.4210854715202004e-14，scale=max(1,abs(reference),abs(actual))；所有比较值必须有限 |
| 历史full-manifest身份 | unverified；没有宣称新hash等于历史hash，也没有改变原A4/物理Gate |

独立M0原始审计SHA为db66609fa75765a5c5089653fe79f54f44b7beb376de5e2b95d1b9c085ec2354；只保存80模式的小型参考文件，未提交大矩阵或场数组。修正仅显式冻结新环境身份并增加独立数学比较，没有删除key、NaN或hash Gate。

## 环境资格、失败与危险ABI

| 检查/尝试 | 结果 | 同时树RSS峰/时间/swap |
|---|---|---|
| 纯标准库Gate tests | 6 passed；含input/hash、allocation、receipt及oldhash/reorder/NaN/key/numeric拒绝 | 非PDE测量 |
| watchdog benign-child self-test | completed，完整identity/status，后代清场 | 29,519,872 B；1.780 s；0 B |
| fixture attempt1 | collection failed：旧utility提前加载缺少PyVista | 237,559,808 B；2.271 s；0 B |
| fixture attempt2 | collection failed：实际DtN依赖也提前加载PyVista | 241,655,808 B；2.375 s；0 B |
| historical private-FFI ports fixture | NOT_RUN_ABI_INCOMPATIBLE；没有执行unsafe helper | 不适用 |
| compatible fixture attempt3 | 三个实际p2 FFCx/MPC/恢复/DtN测试通过 | 535,728,128 B；15.648 s；0 B |
| patched-source fixture attempt4 | 三个测试再次通过；实际analytical G0新mode gate也通过 | 507,879,424 B；3.280 s；0 B |
| named assembly attempt1 | mode full-manifest Gate真实失败，未凝聚 | 699,330,560 B；24.559 s；0 B |
| named assembly attempt2 | 真三维p4装配/导出通过，仍无factor/solve | 1,199,104,000 B；136.742 s；0 B |

新云端为DOLFINx0.10.0、Basix0.10.0、UFL2025.2.1、PETSc3.25.6 complex128/int32、MPICH5.0.1、SciPy1.18.1，MPI1、数学线程1。官方PyVista/VTK/Matplotlib安装后，130个原conda包和核心loaded-library hash未变。它与历史0.10.0.post2/PETSc3.24环境分开记录，不宣称历史ABI或数值等价。

原private ctypes MUMPS helper的MatFactorInfo仅88 B，新PETSc3.25头文件增加两个PetscBool，布局派生96 B，soname也不同。没有建立别名或运行不安全helper；云端独立fixture用版本匹配的公开petsc4py KSP/preonly/LU真实因子，沿用真实MPC/非零内部+端口RHS及独立oracle断言。它不是对原private-FFI fixture的同一ABI重跑。

最终环境回执SHA007a5f794c3b1f4f7431917f15700cd1cfef5606f3601b07c429135ec5270e96；patched-source资格回执SHA943bc9ddeff9cc8b11a3751ff8090f5c24cbf731113553b83c640d9e4f523631。导出manifest SHA0694682ff5e3477f50432a022d4fb9db142e58e3d651d3c53ebd3b0e3811b656；独立导出审计SHA12797a7f9c16518a66c5a79dfbc2d131a52976328b9e1160b1d4e011a8b9efaf。命令、负结果原输出、资源authority与全部内容hash见[compact记录](records/real_p4_probe_preparation_v2.json)。

## 可复现方式与下一步

环境不进入Git。按当前官方DOLFINx0.10 complex/MPI1栈建立隔离prefix，保留所有ABI包/loaded-library身份与manifest；配置OMP/BLAS=1、UCX_TLS=self、HWLOC_COMPONENTS=-linux、MPI4PY_RC_THREAD_LEVEL=single。实际activation由独立云端资格脚本完成，必须在与命令相同的shell中source；不能使用硬编码WSL/PETSc3.19 activation或伪造cloud qualification marker。

先在clean committed own branch运行所列实际fixture并保存hash-bound receipt，再执行python -m benchmarks.run_real_p4_probe --assemble-export，传入准确HEAD、receipt路径/hash和新的ignored run目录。默认无参数只输出NOT_RUN_PLAN_ONLY。入口禁止扩展case/degree/MPI，要求零swap、≤6 GiB显式同时树cap再取动态envelope较小值、900秒及投影allocation Gate。

下一个有界实验是complex128 reference-factor及恢复后独立原A4残差screen；只有该控制通过后才讨论complex64。公共SciPy splu没有独立symbolic-only估计，不能编造。numeric前必须按新worker的实际RSS、声明的backend新增预算、未来vector/recovery余量及128 MiB证据reserve计算admission，并保留外部hard watchdog。现有数据没有exact-zero，默认不改变结构。原A4≤1e-10才算本真实物理RHS的严格screen通过；仅凝聚残差不够。它仍不是BAL_H、原尺寸目标或2 TB/48小时资格。

只提交本独占分支的新research代码、fixture、compact证据和文档；大型CSR/RHS/LU/mapping仍在ignored artifact。没有PR/merge，agent author为dot (AI assistant) <dot@localhost>。全库pytest/CI未运行；GitHub视觉渲染未验证。
