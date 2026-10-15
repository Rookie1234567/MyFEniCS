# BAL H restart512 中断恢复受限诊断

运行与独立复核日期：2026-10-14 UTC。已绑定终审、六点saved Ax独立重算与最终费用账v83。整理发布日期：2026-10-15 UTC。

## 1 本轮结论

恢复attempt02已完成364个outer步，KSP reason=−3，原独立预算148+364=512已耗尽。末native真相对残差0.00042532834087187054，saved真相对残差0.0004253285659505867；相对恢复x0的saved值降低37.36%，相对本次中断continuation起点降低38.69%，但native 1e−11及saved 1e−9原门仍失败。reason=−3表示迭代预算耗尽，不单凭这个码判断数值发散。六点saved独立Ax均与现场记录一致，末独立值0.00042532856596657254；“重算一致”不表示原精度门通过。本报告将原 continuation 的中断、第一次恢复的启动失败，以及第二次恢复分别记录。恢复从已独立复核的 durable128 迭代向量重新建立 Krylov 空间和因子，不能称为一个未中断的512步 Krylov 周期；所有结论只适用于此次受限诊断。

[前一份报告](https://github.com/Rookie1234567/MyFEniCS/blob/96a3aa18202ed2c482ed0f1919867d1c6402f8e2/docs/task40extra_dot_parallel_cloud/reports/hp_reference_free/2026-10-13_uniform36p6_progress/balh108_restart512_cgsrefine_20261014_zh.md)已确认，同一起点的512步对照中，CGS refinement=always 将 saved 真相对残差从 no-refine 的0.0050624655565降至0.00069376979996，消除了该对照中观察到的晚段 native 真残差与递推报告范数偏离。该结果未使 native 1e−11或saved 1e−9原验收门通过，也没有证明原restart32平台的全部根因。

## 2 中断及恢复边界

原 continuation 从前一轮 refined512终点继续，仍为108单元、fine p6、24,056维、原 A/p4/H3/BAL_H、右FGMRES、restart512、CGS refinement=always。其持久化记录包含147个完成的outer步和第148步的一次在途调用；按148步保守计费。末次可用持久化点为本段128步，路径标签7296，saved独立重算相对残差0.0006789835175850782。64步相应值为0.0006918131163599204。

中断段没有正式终态：退出码、完整墙钟、全程峰值及清场均未知。最后资源记录仅给出221.44093053002143秒下界。针对已知stdout/stderr文件inode的观察没有发现打开的写者，此结论只覆盖这两份已知日志，不能写成系统级清场，也不证明hard600触发。

恢复只使用durable128的解向量；没有复用Krylov基、递推状态或数值因子。128之后19个完成步加1个在途步共20步仍收费，不因未保留而返还。因此恢复入场时原独立512预算仅剩364步，新的hard600监护不代表取得一个新的512步预算。旧历史10,000步及前两轮独立512步诊断继续保留原账。最终三个独立诊断共收费1,536步，含历史账共11,536步；路径标签7660只标明当前迭代来源，不能当作累计已收费步数。

恢复的saved向量身份与durable128一致；但经T(Qx)映回native后的typed SHA与原producer不同。现场native初始残差绝对值、相对值、RHS范数三项差均为0，这只是观察记录，不是native字节相同证明或新增匹配验收门。没有新缩放或归一化，saved/native哈希不能互换。

## 3 已定位的启动接线错误与修复

恢复attempt01在科学导入前被旧metadata校验器拒绝：实际restart=512、max_it=segment_max_it=364，早期launcher却调用要求三者都为512的旧入口。此次1.760522142983973秒、0 outer，exit1，清场已验证。此前源码审查只覆盖较晚的producer512绑定，未覆盖这条完整launcher前缀，因此此前“可直接运行”的审查结论不成立；失败和旧回执均保留。

attempt02给live364建立单独、精确的恢复校验分支，仍绑定原中断审计、durable128身份、paired残差元数据、148已收费及364剩余；旧512来源校验保持。修复未把live命令伪装为512，也未改数学算子或验收标准。81项纯测试通过，新增实际完整launcher在科学入口前的集成检查。该预检没有执行科学导入、实际AS安装或数值准入；实际科学准入由本次运行及终审另行核验。

唯一恢复命令SHA-256：361bd2589a5d27aba2ce2cf7f066fbbce2e7d8c2b8b46f0467aa3b78a8f96b5f。

## 4 恢复段结果与复核范围

实际KSP view确认right FGMRES、UNPRECONDITIONED norm、非零初猜、CGS refinement=always、restart512、max_it364及24,056维。下表为运行内保存的paired Ax；原native/saved RHS范数分别0.68914155431206和0.6891415543120595。

| 恢复步数 | native真相对残差 | saved真相对残差 | KSP报告除native RHS |
|---|---:|---:|---:|
| 64 | 0.00067872968572739 | 0.00067872961064121 | 0.00067872968584881 |
| 128 | 0.00067794579526644 | 0.00067794571090543 | 0.00067794579526947 |
| 192 | 0.00064719768533794 | 0.00064719773847456 | 0.00064719768534037 |
| 256 | 0.00059417199457766 | 0.00059417216830993 | 0.00059417199461 |
| 320 | 0.00049549462848251 | 0.00049549489955437 | 0.00049549462850122 |
| 364 | 0.00042532834087187 | 0.00042532856595059 | 0.00042532834092273 |

64至364步六个采样点的两空间真残差均下降。128步出现STAGNATION_FLAG：此前128步两空间各自改善均不足1%，但此项只提示，不触发硬停；之后192至364步继续下降。没有触发增长/递推gap硬停，未调用条件性复核。

末native真残差绝对范数0.00029311143392141056，递推报告0.0002931114339564588，二者范数差绝对值约3.505e−14；六点最大为约8.367e−14。这是同一native空间的范数差，不是残差向量差。另一方面，末saved/native残差映射相对误差仍为1.6930677393715145e−5，较小的native递推gap不能消除这项坐标失配。

只观测364个完成PC调用的输入列，没有完成V512，也没有V513。最终Gram最大非对角2.5221584383996997e−16、最大对角缺陷1.4210854715202004e−14、Frobenius缺陷8.067549167085234e−14。V/完整Gram未持久化，未事后重算；观测没有新增PC/Mat调用。六份独立命名的saved向量（64、128、192、256、320及末364）均是未合格的迭代向量。独立审计共享一次原CSR流，对六个向量分别做saved Ax，核验文件/payload/typed身份、有限性及读取前后稳定性；六点均匹配且均未过1e−9门。latest364 payload与独立末364副本一致。复核未重做native Ax、FE、factor或solve。


## 5 费用与计数

恢复attempt02科学墙钟428.34152204799466秒，采样tree峰值2,632,814,592 B，共1,696样本。exit1源于原真残差验收失败，supervisor清场=true、remaining为空；当前句柄归零及PC销毁也有回执，但不等于全部隐藏native owner的显式销毁证明，更不能补写原中断段清场。build92.14612200300326秒、KSP setup0.0005420890229288489秒、solve330.83509553800104秒，以及复制0.12520990983466618秒、Gram0.5242645760299638秒均已包含在此墙钟内。

独立终审重核1,029个source pins、20项最终描述、1,696个外部资源样本、422次内部准入及2,376个事件。最低host available6,767,292,416 B、disk free12,923,994,112 B，swap为0；最大projected AS6,305,903,528 B、projected tree6,436,676,552 B，输出普通文件24,435,146 B。准入投影与实测RSS分开，未减小原full512 Krylov或被动观测预约。

本段364次outer PC，另有1次setup资格PC；合计365次BAL_H、730次逻辑粗调用、1,058次factor solve，其中328次额外修正。最大返回native粗相对残差9.99837720558437e−11，原1e−10门保留。

本次中断与恢复三段科学时间合计至少651.542974721秒：原中断≥221.440930530秒、恢复启动失败1.760522143秒、恢复02为428.341522048秒；中断最终墙钟未知。v83的项目已知终态科学时长合计22,786.32009754608秒，加入所有既有中断下界后至少30,921.753310919084秒。这些均不是端到端精确总耗时。

只读独审另列：本轮六点stream Ax27.933186139009194秒、峰值53,080,064 B；标量终审0.13222959599806927秒、峰值42,336,256 B。原中断64/128两点Ax复核12.495145977998618秒也保留，不并入科学stage或再叠加到已含的墙钟。

build、setup、solve、被动复制及Gram计时若已在科学墙钟内，不重复相加。独立复核单独列出，准备/等待时长不完整而非零；中断段保持下界，项目总和不宣称精确。内存峰值不相加。hard600、6 GiB AS、8 GiB tree RSS、host≥1 GiB、disk≥4 GiB、zero swap和输出512 MiB原限制保持。

## 6 止点与未解决问题

本次恢复仍有下降，采样native递推gap没有重新出现，但这不是未经中断的完整512周期对照，也不是“加步数即可达到原门”的证明。不把saved检查点称为合格场，不据此宣布hp收敛。既有raw失配、saved/native PC及prediction raw失败、非零port压力资格失败继续保留。原restart32平台为何停滞仍须依证据区分，不因一项启动校验修复或长周期重正交改善而宣称全部解决。

此报告不授权额外outer或自动restart32。下一项仅为same checkpoint6656、restart32、CGS always、max200、hard600独立对照的源码准备，尚未批准数值执行；没有续跑长周期。后续数值仍须单独准入。本次只发布本报告与小JSON，代码、CSR、NPY、ELF、Krylov基和大数组均不上传。

## 7 固定证据

证据路径相对hp_resume_20261013；摘要含SHA-256，完整科学数据留在本地。

- `phase4_restart512_continuation01_incomplete_review.json`：35968 B，SHA-256 `bd50d0763d62f6b4cf5d17f72808ac81634797c05518a0dbc91ea5773aad93ea`。
- `phase4_restart512_continuation01_checkpoint_ax_review.json`：11027 B，SHA-256 `599850b9a4089b35d215a52c6d1010f2b693ea76381c75e2b81c4f393b574923`。
- `phase4_restart512_recovery01_startup_failure_review.json`：7696 B，SHA-256 `241ba39d0987c5568c378847256d43589937ee8d4ca207fcf5bb2e53c12e80f3`。
- `restart512_recovery02_independent_review/independent_source_review.json`：23886 B，SHA-256 `3086193ea5699c313f422e67af866eb5b39113b894ff74ed9125c140867bf9a5`。
- `phase4_restart512_recovery02_terminal_review.json`：113768 B，SHA-256 `207d748f5859d8efcecd95af611304547486f9071e591e7b01e624c14284dc63`。
- `phase4_restart512_recovery02_checkpoint_ax_review.json`：19266 B，SHA-256 `aedeec8b75fd42f949f8026f82a4f36f6a4f88d22c7acc53b6f4d5bbea9e8b5d`。
- `phase4_execution_ledger_v83.json`：69179 B，SHA-256 `e0589f91f2f3ced8ad2dbe3ada6a5937faaae1db527af5c1f2e7cec08f159e57`。
- `phase4_balh108_restart512_recovery_attempt02/summary.json`：2216 B，SHA-256 `9e1695f7ecfee75c7128aa6b7652d5dd317f86d34ffc16e00f6bcbaff95dcf7e`。
- `phase4_balh108_restart512_recovery_attempt02/linear_terminal_before_gate.json`：237512 B，SHA-256 `ab17d6de5c43f33d966ee5e11c3a6b69ad6d1733cfd4ff6a2b53bf980968e6c6`。
- `phase4_balh108_restart512_recovery_attempt02/linear_cleanup.json`：432 B，SHA-256 `3246fbdac593b756cee700f4fb271ab287469878fc63dd07bda497e90e4de733`。
- `phase4_balh108_restart512_recovery_attempt02/actual_V512_observation.json`：4257 B，SHA-256 `f72062cf5e761248ff1b61d770024dd1bcf36b1e42f80e574a7aef675ef81a0e`。
