# V3补充：real-ky phi5 完整三维平移/参考逆资格

## 新结果与限定

继phi0架构试验后，本批只将入射方位改为5°，在同一80-cell三维p2缩放几何、真实Si材料和2-cell空气缺口上检查真正非零的y Bloch相位。完整原始Maxwell算子、2048独立DoF（480内部DoF）、4个完整y块和全部532端口继续保留；没有二维/2.5D替换、n0 projection、材料平均或group averaging。

这次验证关闭了上批“y wrap=1”的具体缺口，**仅限本模型的real ky/phi5**。p4/p6、一般网格、复ky、物理精度及原尺寸50×25×140nm/2TB/48h能力仍未资格。72小时交付目标是workstation-ready大型验证方案，由用户在工作站执行；云端小型结果不保证该大型运行收敛，也不授权操作用户电脑。

## 真实Gate与原三维解

| 项目 | measured | 原门槛/结论 |
|---|---:|---|
| y Bloch phase | 0.5285127305553988+0.848925375778623i | 明确不等于1；真实ky |
| native translation cycle relative | 0 | T^Ny=phase_y I，通过1e-12 |
| canonical shift unitary / F shift-eigenvalue relative | 5.5511e-17 /4.9437e-16 | 1e-12，通过 |
| primal/dual pairing relative | 2.3875e-16 | Q^H dual/Q primal，通过 |
| native A0 covariance / modal off-block relative | 3.1047e-16 /4.5019e-16 | 1e-11，通过 |
| port C/D covariance maximum | 2.5870e-14 /2.5903e-14 | 1e-11，通过；532 ordered keys等于fresh generator |
| alias q0/q1/q2/q3 counts | 76/152/152/152 | n=1与-3均保留，不合并 |

| 系统/RHS | 原A full true residual | 同系统direct场相对差 | FGMRES步数 | 数据身份 |
|---|---:|---:|---:|---|
| 规则A0 generic all-q | 1.2029149204e-13 | 6.3878184856e-13 | reference inverse，无outer | measured |
| 规则A0 real incident | 8.7836991580e-15 | 9.4210148916e-13 | 同上 | measured |
| 三维notch generic all-q | 1.2852120097e-13 | 5.4956864537e-13 | 4 | measured |
| 三维notch real incident | 7.1414088848e-12 | 5.5650285428e-11 | 3 | measured |

notch真实入射解的非零q相对primal norm为5.5251873850e-5，由独立checker使用保存的F/R逆和完整场重算。原A残差门1e-10、direct场差门1e-9保持不变，物理源direct差较phi0更大但仍通过，不能省略该值。全部源augmented port closure≤1.0877e-16，恢复的532个端口和FE/原A residual identity同时通过。源和材料对比仍是缩放、低阶、Si弱对比，不将3/4步推广为大型鲁棒性。

## 环境、资源与证据

| 项目 | measured或状态 | 口径 |
|---|---|---|
| numerical source | ac1410ca1187352fbe398325c5f7aaa33bf0d0bd | clean own branch；末尾source unchanged |
| watchdog | COMPLETED，10.107636026 s | 独立parent+全部后代，1.5GiB/600s/threads1/zero-swap Gate |
| tree RSS /swap | 701,861,888 B /0 | 0.25s sampled simultaneous tree；非单rank或factor payload |
| cleanup | descendants cleared，status/identity全可读 | 无并发heavy case |
| factor inventory | 全4块16,785,408 B；无±q reuse | 小dense payload，不能外推稀疏MUMPS fill |
| 独立checker/tests | 12 residual/direct检查＋all-q/aliases/nonzero-q/augmented通过；4 tests passed | hash-bound原matrix/field；不是新的PDE |
| 冷构建/MPI2+/full pytest/Ruff/CI/rendered view | not_run | warm JIT；不作workstation时间承诺 |

[compact/full hash](records/y_orbit_phi5_pilot_v1.json)保存实际ABI、source、命令、每份original matrix/field/hash、history和资源权威。raw root为 `benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_p2_phi5_attempt1`。既有phi0失败attempt不删除，不追溯改判。

## 下一步

用户最新要求先审计远程库代码、文档和历史，避免重复工作。没有新PDE或p4实现/运行授权；已有p4 external adapter草稿保持未测试/未整合身份。后续方案须有冻结source/environment/config、one-command逐级资格和资源Gate、大型job、checkpoint/restart/fail-fast日志及明确未资格项；工作站由用户运行。完整数学与旧路线区别仍见[phi0详细结果](y_orbit_full3d_pilot_v1.md)。
