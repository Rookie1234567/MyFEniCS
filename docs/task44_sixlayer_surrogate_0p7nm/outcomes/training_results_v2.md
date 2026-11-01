# Task44 v2 训练结果表

本表记录冻结 v2 设计中已完成并通过数值标签门的训练样本。`sample_design_v2.json` 保持原样，继续表示计算前的冻结计划；本表是运行后的独立结果登记。这里的“训练标签合格”表示固定 v2 离散模型产生了可追溯的正式数值结果，并通过完整真残差、能量闭合、服务清场和产物身份核查；它不表示已经证明连续解误差，也不替代最终 GP 盲测。

| 样本 / 六层厚度 (nm) | `R_total` / `T_total` | `R00_s` / `R00_p` / `R00_total` | `A_volume` / 能量闭合误差 | 完整真残差 | 服务与资源 | 训练身份与核验证据 |
|---|---:|---:|---:|---:|---|---|
| `train_006` / `[0.6770004153817964, 0.6960409804168597, 0.8345407608284783, 0.6684162343919503, 0.8133321317942275, 0.8377797351374593]` | `0.09652271781407262` / `0.8828555839215452` | `0.0965221450131587` / `3.7619418372598886e-19` / `0.0965221450131587` | `0.02062169840947761` / `1.4509549117747156e-10`（限值 `1e-5`） | `6.18235042268783e-9`（限值 `1e-6`） | `COMPLETED`, exit `0`, wall `4632.674389977008 s`; unit `task44-sample-train-006-v2.service`, Invocation `44336cff47c847cfab06207f50ebcea3`; 后代清空；进程树 RSS 峰值 `13,091,905,536 B`; cgroup 峰值 `13,864,103,936 B`; cgroup swap 峰值 `0 B` | `qualified_v2_training_label`; source `d53247006894fbc4f94820005c1182491bc7ebbf`; input SHA `a12a914c616adc5d7d3943f39323972c0a208480d5558b741ed4bc0e51b3b85e`; physical SHA `0883e2ce6f8ec1bf2b9e5c43df6fa7962ed95143bb86d66a206cc5daed7951a6`; discrete SHA `19a726fc988bf9a476f6d710494098a28919642319e864ff70bbdb5e129802e2`; [run summary](../../../results/task44_sixlayer_0p7nm/task44_train_006_v2__full3d_direct__mpi1__Mna/20261101T173359.557150Z/numerical_output/run_summary.json), SHA `11203d8654cbb93a457b3a592aedd0723c1545812cef0a7a0681d8f275a2ba1c`; [service summary](../../../benchmarks/artifacts/task44_native_services/task44-sample-train-006-v2.service/service_summary.json), SHA `d02ae1f1e176caf0f9ac7c95aab1e83333e3ba9c7c6dde70aebab963170f0315`; field NPZ SHA `ffc42e2bb3b052e98d0b4b47a35380229db9e8d4f3c92597c21243e3903a55b6`; modal NPZ SHA `d5ad9a5b9bb595631a5b08b4589d0c50a3567b823fc01313f2b3606347dba263`; diffraction-order JSON SHA `29702fcb0f4e0f2eda2fae78d445e56e4c0a2c6479c64fb48dee62081cc7382f`; auxiliary-amplitude JSON SHA `2d10811e6edadb5133199cff932d3eb44b38b0d93814ca0a6486a91211696299`; port-power JSON SHA `8f5c683c2bd1c527692e391e1b6678896b79474fa8149fa53a5d01b4290b0d04` |

端口核验从 160 个原始衍射级独立求和，并与功率记录吻合，末位差在浮点求和舍入范围内；`R00_s/p` 与零级条目一致。160 行端口、辅助幅值 JSON 和 modal NPZ 的模式身份及幅值逐项交叉核对通过。E/H 场 NPZ 中所有数值数组均为有限值。`R_total + T_total + A_volume = 1.0000000001450955`；完整场真残差和端口至体积吸收闭合都低于各自限值。

## 下一训练输入的冻结身份

`train_007` 仍是未运行的训练样本。使用冻结设计 `task44_gp_20261101_seed440731_p6_y12_air0p5_v2` 和其 hash 固定的模板重建输入字节后，输入、物理模型、离散签名与几何哈希均逐项匹配设计记录；这一步没有启动 PDE，也没有读取开发集或盲测标签。

| 身份项 | 冻结值 |
|---|---|
| 输入路径 / 输入 SHA-256 | `input/task44_surrogate_design_v2/train_007.dat` / `0ce23fe8d3c333f23aed932ba06fbdd2c533c203e51e3758eb798204fb84136c` |
| 厚度 / 几何 SHA-256 | `[0.8545507774219032, 0.9067526802949961, 0.8673849864477369, 0.9750536756886291, 0.9320890550610406, 0.5787184973150235] nm` / `54c08f18eef13165f7b2a8374ba93cbf7588a373ab7aa6d06ca2da5ae3aaa23c` |
| physical-model SHA-256 / discrete SHA-256 | `3d70fbc62b39b845c7e1ca65319604f65a510c9e8feefb48720580f88366afb0` / `19a726fc988bf9a476f6d710494098a28919642319e864ff70bbdb5e129802e2` |
| 模板 SHA-256 / 文件大小 | `272312c4e0b997fbf40649c4d3be678a9cd38efe229f3b3d61fddc5fa0656269` / `2534 B` |
| 几何高度 / 顶部空气边界 | `5.114549672229329 nm` / `5.614549672229329 nm` |
