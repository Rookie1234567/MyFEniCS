# Full3D sparse p2→p4 y-reference inverse：冻结前实施计划

本组件把规则参考光栅沿周期y方向的重复单元编号转换成全部q块；每个单元内所有高阶H(curl)通道和每个真实端口都保留。单元内部未知量先准确消去，求解后由既有Task39代码完整恢复。缺口问题的外迭代仍使用原完整三维FFCx/DtN算子。本包是Task040 S2c/S2d背景逆的定向扩展，配合main Task40extra，不是重新提出背景逆或替代主campaign。

## 状态与固定对象

仅外部staging/AST检查；没有新增import、unit、PDE、factor或checker计算。父协调方完成审查后才最小文件集成到own branch、clean source commit、资格化ABI/单元测试、准确命令准入。先运行sparse-p2桥接，独立checker通过后再单独申请p4；不自动继续p4。两次必须使用同一冻结HEAD，中间不插入无关代码/文档commit。

- λ=0.7nm、真实继承Si折射率、1° grazing、real ky/phi=5°、80个原三维hexahedral cells
- 几何/mesh与已资格化phi5 pilot完全相同：继承50×25×140nm配置按7/135缩放；x/z非均匀、y四个bit-identical widths；A0保留heterogeneous x-z Si/air，而非平均介质
- 同mesh缺口仍改变两个实际cell，完整3D outer；额外确定性notch-supported full-FE load只用于辨别小扰动
- manual m±9,n±3实际生成全部532个side/order/polarization端口；q计数76/152/152/152；n=1与−3同q但分别存储，实际γ/归一化来自原carrier
- p2：2048原独立FE、480内部、1568 trace；增广q块468/544/544/544
- p4：15872原独立FE、8640内部、7232 trace；增广q块1884/1960/1960/1960

## 源码和复用

`src/solvers/y_orbit_condensed_adapter.py`只连接既有assembly-time condensation、完整Bi/Di/Hhat/XiB与P4CellCondensedInverse。`task40extra_y_orbit_reference.build_y_orbit_layout`与共同Hcurl物理方向帮助器继续用作完整map权威；不复制Task040第二套map或恢复公式。

`src/solvers/y_orbit_sparse_reference.py`按Q_t=R_t F_t构建每q稀疏primal map，加该q全部原端口identity列。原始moment R不假定unitary。变分dual RHS为Q_aug^H b，primal恢复为Q_aug z，不能用Q_aug^-1替换dual。

Native增广矩阵仍`S=[SV,C;-D,Hhat]`。端口native translation为diag(T_trace,η_n)，η_n=exp(i(ky Ly+2πn)/Ny)。必须先通过T^H S T=S、完整原FE action covariance、包含全部interior RHS的reduce(T_full^H b)=T_aug^H reduce(b)，恢复后再核验完整A T x=T^(-H)b。随机向量covariance只是采样见证；矩阵norm门在实际S上完整计算。

第一遍流式核验所有16个`Q_p^H S Q_q`块，不创建因子。除全局off-block相对norm/absolute max外，每(p,q)记录Frobenius norm/absolute max，非对角独立门为max(||S_pq||F/||S_pp||F,||S_pq||F/||S_qq||F)≤1e−11。任何zero diagonal block受控停止，不删除sector。只有全门通过后第二遍重新计算原对角块，核对exact CSR hash并逐q创建真实SuperLU factors；全部保留，不复用±q，不产生global dense/modal matrix或L/U统计副本。每个实际块的重复/线性/true-residual门保留S2风格资格。

`src/solvers/y_orbit_sparse_probe.py`负责真正数值工作；runner只处理source/ABI、watchdog、hash与事件。checker从ignored原动作向量、原空间storage、稀疏S/Q及全部q块独立重算原residual、端口闭合、slave zero、nonzero-q和完整congruence。checker也有单独whole-tree watchdog，不重建FFCx或宣称p4 direct control。

## p2桥接权威与门

固定旧`y_orbit_p2_phi5_attempt1`，source `ac1410ca1187352fbe398325c5f7aaa33bf0d0bd`。runner硬绑定report/provenance/checker/watchdog SHA256、旧source、phi5、complex ABI receipt、实际axes、native row inventory、seeded generic RHS及全部ordered port keys。新原volume sparse MPC+所有原carrier贡献在≤32列panel中与旧dense A0的全部2048列比较，门1e−11，任何q factor前执行。mmap可能把整个67MB旧A0页驻留，已计入准入。

新原空间恢复的generic/physical regular和notch场均与旧full dense direct fields比较，门1e−9；full original true residual与augmented闭合门保持1e−10。generic含所有q和全部interior load。p4不创建完整direct factor，原空间residual仍是完整A4 action；缺少p4 direct比较明确写not_run。

p4只能由同HEAD的新p2 bridge report和独立checker解锁。checker记录exact report SHA、provenance SHA、artifact-manifest SHA、source、degree与其监督receipt；runner逐一验证，不能靠邻近文件名或一个gate_pass。stale/swapped checker有负测试。

## 资源、整数和受控停止

- serial、maththreads1、whole parent+descendants aggregate RSS硬上限1.5GiB、600s、zero swap，现有subreaper kill/reap完整tree；失败/受控停止均保留
- 因子初始准入：实际树R0+512MiB声明additional factor/workspace allowance+128MiB evidence reserve <有效cap；名义R0须<939524096B。后续已resident factors计入实时RSS，只保留remaining份额，不重复加整个512MiB
- graph-derived稀疏product support在分配前核验；q切片mask/slice、adjoint/format转换、CSR导出、localcache/ports、original-action证据等有显式additional allocation gate。SciPy/SuperLU fill/nativeworkspace无可用独立估计，policy不是峰值保证；硬watchdog仍为最终门
- all-four dense q数值241188096B仅derived维数说明；实现不生成它们。完整p4 FE dense4.03GB禁止
- 记录原CSR indices与indptr实际dtype/bit宽度、PETSc.IntType；维数和NNZ offset在窄化/创建前用Python整数核验。既有2nm CSR约2.07b entries接近int32上限，不能把本cloud int32 ABI外推原尺寸。SciPy SuperLU本身仍需signed C-int准入，即使PETSc未来换int64；工作站后端/构造需独立资格，不自动切换当前small ABI
- 结构、wrap、模式库存、原residual、source/hash、swap/readability或time任一门失败即停止；不放宽门、不silent rounding、group averaging或truncate aliases

## 待协调方冻结准确命令

```bash
source ../complex_env_setup/activate_cloud_complex.sh
python -m pytest -q src/test/test_y_orbit_condensed_adapter.py src/test/test_y_orbit_sparse_reference.py src/test/test_y_orbit_sparse_bridge_identity.py
python -m benchmarks.run_y_orbit_sparse_probe --run --degree 2 --expected-head <FROZEN_HEAD> --run-directory benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_sparse_p2_phi5_attempt1
python -m benchmarks.check_y_orbit_sparse_probe benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_sparse_p2_phi5_attempt1
# 仅p2/checker通过、根协调方另行准入后：
python -m benchmarks.run_y_orbit_sparse_probe --run --degree 4 --expected-head <SAME_FROZEN_HEAD> --bridge-report benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_sparse_p2_phi5_attempt1/probe_report.json --bridge-report-sha256 <EXACT_REPORT_HASH> --run-directory benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_sparse_p4_phi5_attempt1
```

本计划只验证小scaled模型架构和同mesh degree growth。原尺寸准确度、mode truncation、h/physical convergence、強er notch/optical-size robustness、2TB/48h仍未资格。后续代表y-cell直接装配还必须与当前完整3D变换块逐项证明port面积/row-column归一化和全部alias γ的身份，不能把q当一个物理n或跳过原完整3D residual。
