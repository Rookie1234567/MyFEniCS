# 工作站波长续试：结果与证据

**阶段结论：六个正式 case 的数值求解门通过，但物理功率没有通过资格门；0.7 nm 未运行 PDE。** 累计源转移在本次固定离散上能复现 direct 解；提高到 N=4 没有降低 wall time 或进程树峰值 RSS。所有 R/T/吸收保持 `diagnostic_unqualified_for_physical_convergence`，不能据此声称物理功率正确或网格收敛。

## 1. 模型与比较方法

模型是一个 50 × 50 nm 周期单胞，z 范围为 −10 至 130 nm。Si 基底占 z=[−10,0] nm；有限 Si 块占 x=[16.5,33.5] nm、y=[15,35] nm、z=[0,120] nm，块体尺寸为 17 × 20 × 120 nm。x、y 都保留 Floquet 周期边界，块体在两个横向方向均有限。固定 p2 boundary-fitted 网格为 4 × 4 × 16 = 256 个六面体，独立 FE 行数 6,272；全系统还包含由各波长模式清单决定的端口辅助未知量。入射为 θ=89°、φ=90°、s 偏振、单位幅值。

PSTDDM 将相邻物理层的源影响逐段传给下一个局部子域，再把局部结果组合成全域场；这样做的目标是减少大规模全局求解成本。这里把其结果与同一原始 Floquet–DtN 离散系统的 direct 解比较，并以完整显式真残差检查方程是否真的满足。内部局部问题使用 PML；原全局问题不加吸收。固定 p2 粗网格只回答这个离散算法测试是否一致，不回答真实光学精度、连续解收敛或其他网格上的性能。

## 2. 六个 case 的数值与资源结果

`true residual` 是对完整原始 FE+端口系统显式重算的相对残差。E/H 是候选复场相对同波长 direct 场的相对 L2 误差。wall 为 supervisor 全程墙钟时间；RSS 是监督器采样到的同时进程树峰值，单位为十进制 byte。六次均返回码 0、未触发停止、完整进程组退出，最终任务 cgroup swap 为 0。

| Case | source SHA | supervisor wall (s) | process-tree peak RSS (B) | full true residual | FGMRES 步数 | E rel. error | H rel. error |
|---|---|---:|---:|---:|---:|---:|---:|
| 13.5 nm direct | `f1ad2aa51e27aa7ae014cf3a6257da8c1338dffd` | 66.18183055706322 | 439730176 | 7.108120129330216e-14 | — | reference | reference |
| 13.5 nm N=2 | `f1ad2aa51e27aa7ae014cf3a6257da8c1338dffd` | 142.657965131104 | 761593856 | 5.135081916298711e-14 | 0 | 1.2962329932392333e-15 | 1.3033253827632339e-15 |
| 13.5 nm N=4 | `20712b4aa13c5c48aecfdf981ba8fbf97fe26e81` | 151.2700126208365 | 919085056 | 6.904713991603162e-9 | 18 | 7.460191107285582e-11 | 7.50172978678905e-11 |
| 5 nm direct | `20712b4aa13c5c48aecfdf981ba8fbf97fe26e81` | 68.07932984735817 | 593358848 | 1.6988893566697058e-15 | — | reference | reference |
| 5 nm N=2 | `20712b4aa13c5c48aecfdf981ba8fbf97fe26e81` | 140.71321944147348 | 781942784 | 1.808653215195212e-15 | 0 | 8.736138685800404e-18 | 8.371881857827875e-18 |
| 5 nm N=4 | `20712b4aa13c5c48aecfdf981ba8fbf97fe26e81` | 184.09004832059145 | 936599552 | 4.2060615167569276e-9 | 9 | 5.5752925705028683e-11 | 5.4431047073417084e-11 |

按任务门槛，direct 残差均小于 1e-10，候选残差均小于 1e-8；候选 E/H 误差也分别低于 1e-4/1e-3。N=2 的初始 sweep 已几乎等于 direct，故为 0 步 FGMRES。这个 N=2 只有一个 pair 横跨全物理域，未形成可扩展的局部子域，也不代表低内存路线。

N=4 比 N=2 慢且占用更大：13.5 nm 多 8.6120474897325 s、峰 RSS 多 157,491,200 B；5 nm 多 43.37682887911797 s、峰 RSS 多 154,656,768 B。全局质量矩阵 LU 与局部因子同时常驻，因而局部化并未移除全局因子占用。13.5 nm N=4 局部组装 91.54638784192502 s、局部分解 1.078907709568739 s、局部 solve 计数 `[38,38,38]`；5 nm N=4 分别为 104.78329011332244 s、0.727816334925592 s、`[20,20,20]`。5 nm N=2 局部组装 66.84750025253743 s、局部分解 0.4475272707641125 s、solve 计数 `[2]`。全局质量因子 NNZ 分别为 2,780,110（13.5 nm）和 2,780,101（5 nm）；这些 NNZ 不是 RSS。

## 3. 功率诊断：未通过物理资格

`A_flux` 是由端口通量得到的吸收诊断；`A_volume` 是体积分吸收诊断。表中能量缺口定义为 `R + T + A_volume − 1`。这些后处理量没有通过物理资格，且网格与 DtN 模式均未做收敛研究。尤其 A_volume 远大于 1，说明不能把它当成合格物理吸收；候选与 direct 解彼此吻合，只能说明同离散求解一致。

| 波长 / case | R | T | A_flux | A_volume | energy defect |
|---|---:|---:|---:|---:|---:|
| w13p5_direct | 0.568788782789886 | 0.26255671216736726 | 0.16865450504274676 | 2.3953684927134478 | 2.226713987670701 |
| w13p5_n2 | 0.5687887827898862 | 0.26255671216736726 | 0.16865450504274654 | 2.3953684927134478 | 2.226713987670701 |
| w13p5_n4 | 0.5687887827902943 | 0.2625567121752757 | 0.16865450503442997 | 2.3953684927256154 | 2.2267139876911854 |
| w5_direct | 0.8375012541172718 | 0.009094259780738016 | 0.15340448610199015 | 22.208391959345533 | 22.054987473243543 |
| w5_n2 | 0.8375012541172718 | 0.009094259780738016 | 0.15340448610199015 | 22.208391959345533 | 22.054987473243543 |
| w5_n4 | 0.8375012541173057 | 0.009094259780739257 | 0.15340448610195506 | 22.208391959338474 | 22.05498747323652 |

以上数字直接取各场保存的 summary，不用 direct 数值替代候选；完整独立对照及分量差见 compact。失衡来源尚未完成归因，不能仅凭粗网格或未资格标签判定具体原因。

## 4. 数据身份与模式清单

每个输入文件 hash 将 case 配置与波长、模式、分区和求解选项绑定；source SHA 是运行所用源码身份。13.5 nm 的 direct/N=2 使用 evidence-only 更新前源码，N=4 与全部 5 nm 案例使用后续源码。原始记录各自的 source/input hash 均保留，不能把六案写成同一 source SHA。

| Case | input SHA256 |
|---|---|
| 13.5 nm direct | `fe012581ef1eb2a22f1c2bfcf17661e9ca9403723cafd2776cbdf48a2e185543` |
| 13.5 nm N=2 | `0de715a10d397b78aaff77126f668361e36e6145ce0e87de6e9385f4c60e3d4e` |
| 13.5 nm N=4 | `5ad8575c8f5aa4940b6c8f17cba903cc10c2e562a0de14ada96e07314b1ba2ed` |
| 5 nm direct | `bcea2ad56b4268486d5223a57938a7e5e4e1b10f7980a1c58a0f94a48a3bf8a6` |
| 5 nm N=2 | `881b5d5d4c6046ea57df918e99e790d0eaf4b2227d14d48b3c7795d6ff82756d` |
| 5 nm N=4 | `195c34913908d889d7ca1eebbead1ef5ae648e160bdb7dc8a62df42ee0f12e1c` |

5 nm 共同物理 SHA256 为 `bfbd842d61a0dbc645b077e3b172ecce60f0e9a91cf43d68687f96f0c7adf640`；材料 identity SHA256 为 `0ca6887bc6cf992a5b9256c911a1785c4da02961070e454df2b5e3a3a328f6f6`，Si 复折射率为 `(0.9939708306207328, 0.004352253040131573)`。有序模式 identity SHA256 为 `21e7edcb4afdef1d4f5712196c13e2fb5d3bc0c69624c7cd6c6821627a53cd3c`；共 3,772 个辅助模式（1,230 propagating、2,542 evanescent），auto max `(10,19)`，实际选取 `(11,20)`。C、D identity SHA256 分别为 `80fb1ed0daa27a60c2e49e752c3ce5a39ffda546090ac52e68a2da274f74ec2f` 与 `45981ffc5c34e25759b9c1fe0b093279427e25cd23926e6db4010125f038bee7`。5 nm 全系统行数为 10,044。

13.5 nm 为 612 辅助模式（166传播、446倏逝），auto=(3,7)，selected=(4,8)，完整系统6884行。物理 SHA256 `f67681a7725164e383d0c4734f80539b4409505a7e41b9f1aa951365e138b20c`；材料 `0dd4093be35e7226f0425853866b4458d27facc5c2ae31131ba8c3e45c999e25`；ordered modes `953be5a1283555a87c0dfac258c7b1b346ec64dd17d78072d186687856e65208`；C `52d946a3dc91c6b30a48c74496a54f86293bfa4df66aecd491b48e3d3ac8ed6b`、D `d8e58dffdfb2bdabf7844960824dea2f22ee28350eeef3f002169f246811d3db`。这些 hash 绑定本波长，不能替换其他波长身份。

## 5. 5 nm 与 0.7 nm 的准入状态

5 nm live no-FE 预检记录：`preparation/5nm_live_preflight_20712b4.json`，SHA256 `f07a5e54ec3afe7401cf1757fd9bea480c858076c2dc4d85de6e3160858ba954`。结构网格为 256 个六面体，独立 FE 行 6,272，全系统 10,044 行。direct/N=2/N=4 的 `4*n²*16 B` 计划 allowance 分别为 6,456,443,904 B、5,035,261,952 B、5,968,494,592 B；加 512 MiB 余量均在 8,000,000,000 B 单任务门内。live MemAvailable 为 506,390,179,840 B，磁盘可用 427,189,772,288 B。此预检之后确实运行了上述三个 5 nm case。

0.7 nm live no-FE 预检记录：`preparation/0p7nm_live_preflight_20712b4.json`，SHA256 `23f8d53538f243d9cc3a4784680278e4c47433402554e55f20c95a19ac976318`。材料复折射率 `(0.9998851703688496, 4.3236152269189515e-06)`；mode inventory 有 166,460 个模式（64,120 propagating、102,340 evanescent），auto max `(71,142)`，选取 `(72,143)`；独立 FE 行 6,272，全系统行 172,732。计划 allowance 为 direct 1,909,526,004,736 B、N=2 5,035,261,952 B、N=4 5,968,494,592 B；预留量 536,870,912 B。`4*n²*16 B` 是保守计划 allowance，不是测得的因子内存或必需因子大小。direct 计划连同余量超过 8 GB 和约 400 GiB 宿主保留线投影；N=2/N=4 的数值虽可放入 task cgroup 估算，整对象内存尚未覆盖全模式对象、C/D、装配和缓存，因此没有通过完整对象 admission。**本轮未运行 0.7 PDE/FE。** 该停止只表示当前工作站 gate 未批准；不说明 PSTDDM 或 0.7 nm 在别处不可计算。

预算账本 `budget_ledger.json` SHA256 为 `3a05982cabcd90f147cbe336e3c9f31484193a274d922e17103ee9ce654c999d`：六个正式 supervisor runs 总 wall 为 752.9924059184268 s，共 6 次 attempt，均完成，预算上限为 10 次/21,600 s；任何 case 均低于 1,800 s。所有 case 的 cgroup swap 为 0。

## 6. 原始记录、审阅与失败尝试

远端专用 evidence 根：`/home/fenics/Projects/laptop_share/benchmarks/artifacts/pstddm_workstation`。源码根为其 `source/`；正式 run 原始文件在 `runs/<case>/`；审阅 JSON 在 `reviews/`；两份 no-FE 预检在 `preparation/`。每行依次列出 `run_manifest.json`、`run_summary.json`、`supervision.json`、`artifact_hashes.json` 文件的 SHA256。

| Case | 原始目录 | manifest SHA256 | run_summary SHA256 | supervision SHA256 | artifact_hashes SHA256 |
|---|---|---|---|---|---|
| 13.5 nm direct | `runs/w13p5_direct/` | `e709ea369ba24c9cf64ae926f68a399e43a09bc573494fbe75d193c697ab8810` | `d83de6eed41d4c04cf53ceeabf5f728d3b0a6cc392f16fcc03fb1b5d566646c9` | `02f937b6a8227e6bc22c452340c099fea1fc9c860919e24cf93ebefd3efe79aa` | `2e9c4341cd116ba02c3f01785ca61aacaa4b6536129ffb7ce323a08f1ccec09f` |
| 13.5 nm N=2 | `runs/w13p5_n2/` | `811a9d86876634e83f20155adc8a9bbaafb5ca155cc5320a406fc8a9745c0f74` | `cc1178761779d22da8712e2e4c7bbc1b14b496576396391a515cfb37deae39bc` | `6a187dc5496f39a341dacc2cd614f3242bd0426eef5bdb13fba730cb0ccfbc07` | `5cda23a213106942d8a5dd6f6d010d7591b8b4e16bf048786d452c2d6e9ed272` |
| 13.5 nm N=4 | `runs/w13p5_n4/` | `6258b0534ce24eedab3108da719854fcaeedeabbfc4ae1230c99be1c03dc8af1` | `174c31c971c576541199c929488ab66c3c6dca1bd063049c2cede3648db91eed` | `895837b2b157cfbb3a9b22c800679fefea634cf096c8fa78394b57fba55f7eb5` | `d6ef6b76c4bca69546d402c29ecceddc06c90a8c7bcd5a1b647ebcba53b7acea` |
| 5 nm direct | `runs/w5_direct/` | `6427c70df9f4c9a1747342814ef5eed9d28a8efa71c0cebc94aec071530cd371` | `f9e8e69fa32ae5e25d4a6746d332b9d6992766ebb42622e4efbddfc4a3b4c34b` | `55337c81d68395f3a76b20cd214ca1a2bb919cd0f6e84a34d6cf54928f6f9057` | `3c9e375828f2f75ed4d485ed1ae439611dbbac0c7b475ce1415a0edacf2042fc` |
| 5 nm N=2 | `runs/w5_n2/` | `182b64a4e2a012e6b5a644c9349c85df50619b771caaeaccbe2c8220f9538b1a` | `e9b11c1273a7b6ca1686adf6c9f59e0287ca44ffa4b7b270dfd3028d2a421d18` | `f057ab882f5300fa442717d202916c069d02f50cf02e489af3065814ae4e3a33` | `f46434d3d2bbceb548a14a8b123d72c7f241fe8f09b6939a65514042ae17377a` |
| 5 nm N=4 | `runs/w5_n4/` | `ef392055a0d375f9f65f24d12b04b18112298b4275b95051d77de8cdbbdfc167` | `e032b0860421358c6d99bc937f00455f25ee2f148de6035152d59c048871ec5e` | `0e30775f8343003361d83e0f3a0901b5b02a9facd8af4bb8214976e9ec2ed7ad` | `b1f79e0bf45bd5f79e74814fc74ce512a59119415ed34b8d4f03eca485d33ca7` |

| 审阅对象 | review JSON | SHA256 | 审阅 wall (s) | 审阅峰 RSS (B) | 状态 |
|---|---|---|---:|---:|---|
| 13.5 nm direct | `reviews/w13p5_direct_main.json` | `3d7750216f2deaa5ee5dd1b418524eb482f29c81f4c96bdae40d5e9616aefc7f` | 1.483883896842599 | 204357632 | 完成 |
| 13.5 nm N=2 | `reviews/w13p5_n2_main_20712b4.json` | `0822a868e4ae12c7667a8aa6c641f2e45dc53702f735b48b9a804602e41352a5` | 1.6648029359057546 | 232960000 | 完成，有局部矩阵复算限制 |
| 13.5 nm N=4 | `reviews/w13p5_n4_20712b4.json` | `2442bd5327a346f48e3301570d8ad38c0a57f30d6a218131ae9939827bb0c27f` | 1.4625654835253954 | 233279488 | 完成 |
| 5 nm direct | `reviews/w5_direct_20712b4.json` | `86d22b829ad70153143f534fdbbd6fbbecb7934028358b5e3181584c81bcec36` | 2.511584049090743 | 438837248 | 完成 |
| 5 nm N=2 | `reviews/w5_n2_20712b4.json` | `4ecb28fa5abd8b26c09df61ac7334512b9483e7af107fa96bdd2635474df5a8a` | 4.332337691448629 | 469630976 | 完成；独立 local matrix recompute PASS |
| 5 nm N=4 | `reviews/w5_n4_20712b4.json` | `50e1e55ad49df5d6da5b6a2b74c4cd194f1173a7bece2f96b3aecb6175af55ae` | 3.1522063966840506 | 469381120 | 完成 |

13.5 nm N=2 的原生记录内 `n2_operator_relative=9.956328301758284e-17`，但独立 local matrix recompute 因未保存 `pair0_map.npz` 与 `pair0_L.npz` 而标为 `NOT_RECOMPUTABLE_MISSING_SAVED_LOCAL_MATRICES`；其 full residual、E/H、资源和其他保存数组已复核。原始审阅失败记录未删除：direct 启动尝试 JSON `reviews/w13p5_direct_review_attempts.json` SHA256 `a1c0193c5cf89a38ea1a10a797498836276e84d54a25028b29f36e540727cd9f`；N=2 缺矩阵审阅尝试 JSON `reviews/w13p5_n2_review_attempts.json` SHA256 `4b951c60f888e6150c009124d2af9caf4ee7b9aa3652233e5f84999bce09a943`。这些是 review/checker 启动或保存数据缺项，不是 PDE case 失败，也没有重跑 PDE。

## 7. 限制与决定

- 同离散残差/场误差通过，不代表连续物理解或真实光学精度。p2 粗网格未做 h/p 收敛，也未做 DtN 模式、PML 或积分收敛检查。
- 体吸收诊断显著失衡：13.5 nm `A_volume=2.3953684927134478`、energy defect `2.226713987670701`；5 nm 分别为 `22.208391959345533`、`22.054987473243543`。两者都是负的物理资格结论，不能改写成通过。
- N=2 是跨整个物理域的单 pair 极限对照；N=4 同时增加 wall 和 RSS。全局质量矩阵因子仍与局部因子同时驻留，当前结果没有显示分区带来的资源收益。
- 0.7 nm 仅有 no-FE admission 预检，状态为 `not_run`；不是求解失败，也不是其他机器/实现不可运行的结论。
- 本轮实现阶段已完成定向测试，详见 [test_summary](test_summary.md)。文档收口只校验文件/hash/数字及 diff，不重跑数值测试；没有全仓测试、MPI 多 rank 或 CI 通过结论。

当前建议：保留本轮数据供主控 review；在物理吸收后处理与局部因子/全局质量因子生命周期得到独立解释前，不把这些诊断升级为物理结果，也不依据本轮资源数据宣称 N=4 更省内存或时间。

## 8. 交接入口与下一项

[运行/证据索引](run_index.md)与[机器可读compact](records/compact_v1.json)给出全部实际路径/hash、监督命令和独立回执。下一项应先利用已保存 direct/候选场，核对吸收积分与入射功率归一化及场定义，定位巨大能量缺口；当前不自动追加网格/PML/PC扫描。物理诊断闭合后，再审议非全域局部问题的规模收益和0.7nm完整对象准入。
