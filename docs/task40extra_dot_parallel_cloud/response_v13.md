# Response V13：成功X点的完整保存证据资格化

结论：本p4/X网格加密点已由实际fresh worker与完整saved-only独立checker通过inverse/FGMRES/residual/recovery/all532 output资格化。worker HEAD816b7247c8359a7affbd450365de5bbb86de367a，checker HEAD2a07d23d17b527675e6ae0b904c56121e258b4fc，来源分别绑定；这是同一光学尺寸与固定manual532下的网格加密点，不是目标光学规模、AUTO32060或原目标尺寸资格化。

这次把同一小型三维结构的网格加密，检查“两胞元参考求逆”能否继续恢复整个原三维场：先在单元内部精确消去未知量，再按周期方向分块求解，最后恢复全部内部自由度，并回到原始三维方程检查误差。收益是避免构造完整周期参考矩阵；代价是保留四个分块因子及恢复和核验成本。本轮只验证该加密点。

## 结果与成本

| 指标 | 本次X实测/证据 |
|---|---|
| 离散范围 | p4，6×4×5=120 global cells，两local twist各60 cells；每cell300原始列，完整12960 interior自由度 |
| 端口/输出 | q端口76/152/152/152；8组source各532 finite且representable的完整physical output |
| worker终态 | COMPLETED/exit0，1535.1467186810041s，whole-tree RSS峰值1422172160B，swap0，后代已清 |
| 独立checker终态 | COMPLETED/exit0，590.1043245119945s，RSS峰值1567666176B，swap0、complete identity、后代已清 |
| factor | 四个q factor同时保留；stored CSR总payload54078536B |
| factor setup | 3.9568744160060305s，含测试与evidence；pure backend factor与pure PC计时未知 |
| notch FGMRES | generic/interior_only/notch_supported/physical分别4/4/5/4次；原始full3D FFCx+all DtN residual最大4.710949682298374e-12 |
| regular physical native residual | worker保存7.57682638912512e-11；独立重构native最大7.546733167266532e-11，均在1e-10真残差gate内 |

所有成本受明确X-only 2GiB/1800s、MPI1/thread1、zero-swap研究边界约束；不声明普通1.5GiB/600s资格化。checker只消费保存证据，numeric factor calls=0，不重跑PDE。四factor实际fill/内存未测，不能用CSR payload代替factor内存。

## 独立checker与来源链

真实success schema为task40extra.y-orbit-direct-profile-checker.v1，gate_pass=true，qualification为fresh X complete full original inverse/FGMRES/residual/recovery/all532 output。检查条目为358 direct、33519 raw、37 operator、41217 shared，总计75131条通过。shared有35754个unique name；不同实体合法复用控制label，不能额外要求全局label唯一。历史312 check及历史数组均未拿来替代新点检查；事件读取保留全部99657条顺序与EOF，双遍hash相同，详见紧凑JSON保存的event receipt。

[实际checker](outcomes/records/direct_X_v13/compact_record.json) SHA256=7cfba8a3de25cbb15d9cfaef7000b9d7860feacb474740cdadadcfcace80c08a；[supervisor](outcomes/records/direct_X_v13/compact_record.json) SHA256=5c0aae7af937ef22e9a2379ab6eae9f8974f579343be676b8dbd9cec602001fd。原worker report SHA256=f98c393f1056b6722d3fda28775dfa6c98cd25ec332417c08dfc2d7ae883de08。跨HEAD source bridge只允许两checker文件与metadata test三处差异，其他numerical/config/input依赖相同。

## supplemental receipt与失败记录

success schema自然没有evidence_valid字段；外部launcher在成功packet与watchdog已保存后取该字段，产生KeyError。随后首个supplemental finalizer又额外要求shared label唯一，在任何receipt写入之前失败。这两项外部收尾失败原样保留。

[receipt-only补充](outcomes/records/direct_X_v13/compact_record.json) SHA256=8741aee5110e4167e52638a370a7163eee6384d6c2eb755415336c114d40506c确认实际schema、75131条通过及资源终态，不修改原worker/checker、不添加evidence_valid、不重跑checker或PDE。过去startup/时间/内存admission、source-role与residual定义失败的archive保留，见 [compact_record.json](outcomes/records/direct_X_v13/compact_record.json) / [manifest.json](outcomes/records/direct_X_v13/manifest.json)。

残差比较按各自exact operand定义与独立operand差异核验，independent operand gate为1e-11，saved/recomputed各12组native/FE/port真方程gate为1e-10。computed complex128舍入/减法包络属于诊断，未认证为区间算子界；不承诺tiny residual跨表示的1e-12/RHS相对精度。旧crossrepresentation/RHS gate失败不被改写。

## 适用范围

材料/几何仍是弱扰动校准case，physical nonzero-q primal相对量9.791635566626867e-5；4/4/5/4迭代不能推广至更强耦合。sampled right-PC defect最大0.013423201750147613仅是样本，不是operator norm界。target_geometry_accuracy=false、official_results=false；目标尺度精度、容量、原目标尺寸、AUTO32060收敛和用户2TB/48h均仍未资格化。

本次归档沿用已完成的独立核验；没有因文档发布重新运行数值。上文实际checker、supervisor和补充receipt链接指向compact中记录的原artifact路径及完整哈希，大型原始文件不进入Git。compact中的worker_terminal.interpretation保留首轮checker失败时的历史说明；最终状态以同文件checker_terminal与最终独立receipt为准。

[最终独立来源/metadata linkage receipt](outcomes/records/direct_X_v13/independent_final_X_evidence_linkage_review_v1.json)已原字节复制并绑定，SHA256=cd597f64842896afecd2f51ebd7e436285a13cfc94d99475eccff3dbba817c25，status=PASS_FINAL_X_WORKER_SAVED_CHECKER_AND_SUPPLEMENTAL_EVIDENCE_LINKAGE。该审阅独立核查来源/ABI/全部scalar check entries/hash/resource/supplemental与失败链；没有数组、event文件或PDE重算。
