# Task042 V5：固定对象失效定位

终态 `FIXED_OPERATOR_LOCALIZATION_COMPLETE`；完成 D0–D4 的有界诊断，原 p4 粗逆仍 `NOT_QUALIFIED`，不进入 F5。本轮把同一个残差分别交给局部近似逆 B、粗空间修正 C、原平衡两层 B2，再看保留方向的小最小二乘。这一步用于区分“空间覆盖不足”与“组合改变了局部作用”，代价是有限原方程审核；它没有开发或资格化新的求解器。

| 本轮范围 / 身份 | measured结果 / 边界 | 证据 |
|---|---|---|
| 合同 | [Review V2](../review_report_v2.md) `91c4a0dbfa2e8a14df273eab5e27726059d7c835`；V5_FIXED_OPERATOR_FAILURE_LOCALIZATION | [预登记](records/localization_design_v5.json) |
| 正式运行source | `5d82651af0f723c73487783deb43969f05d46ed3`，四次启动tracked/nonignored状态均clean，文档HEAD不冒充source | [run index](records/run_index_v5.json) |
| 共同库 | 12/12真实可用：ZERO/GEO/OLDPOD/ERROR各3，原index0/10/11；9历史native精确重现 | [共同状态](records/common_state_manifest_v5.json) |
| 空间 / 探针 | OLDPOD/ERROR Z/U/R原rank128完全不变；补空间有效rank16/16，未剔除后补足或换seed | [补空间](records/complement_probes_v5.json) |
| 离线参考 | 只seek原teacher已消费0/10/11三行；3/3原native/port/恢复通过，不新建因子、不传PC | [teacher例外](records/teacher_exception_v5.json) |
| 独立审核 | 24同r对照、192原方程修正审核、2全输出探针重算合格；192修正strict0/192 | [独立checker](records/independent_checks_v5.json) |
| 内存 / 时间 | 四正式阶段wall1144.401529s，同时整树RSS峰1135407104B，own swap0；全部shared-workstation | [成本](records/run_index_v5.json) |
| 保留边界 | V1–V4负结果不改；seed420620不生成、不读；新NN/新basis/长KSP/fresh/F5/p6/短波/GPU/official均not_run | [决策](records/localization_decisions_v5.json) |

## 固定模型、坐标与证据边界

唯一模型仍是原Si、13.5nm、1°/phi0/s，p6/h10对应同网格p4，252六面体、quad15、双Floquet及完整80通道。实际仅建p4：53084 FE存储行，21824独立trace＋port行，Schur存储NNZ8184464；原A4/A6/MPC与恢复不改。S CSR SHA `150f18e26f15783726f2ffeb362ef053450962a16fff13d5241cc93c8d018560`，physical SHA `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f`，mode SHA `d4380495d912f97f6d303a85756bb9b252a1117bad229b559f0ac8140e745fbb`。

原几何 B 仍 R-GEO-CELL80-v3：252个最多272行的原Schur主子块，Nédélec cell trace支撑经Floquet canonical主从映射限制、次数平均延拓，每patch包含全部80port。五个冻结数值文件的content SHA/Git blob在构建前验证，与V4 source5691d79abe87d3582ede5bbaf8369c5487e7c392完全相同；只新增显式research profile与诊断核。[旧冻结身份及新opt-in](records/localization_design_v5.json)。

共同库顺序固定为reduced零初值、V3 GEO最终、V4 OLDPOD最终、V4 ERROR最终，每类按0/10/11。全场由原RHS作particular recovery；ZERO-011完整场范数0.000959760299726而reduced x=0，不能把full场假定零。旧NPZ提取真实master trace及累计port，并逐个重新计算r=b_S−Sx。0属于physical_F1_trajectory，10/11属于同一个heldout_seed420400_first_full_rhs_family，只有两个whole families，不称三个独立family。当前16个旧heldout已消费，本轮只是诊断。

所有r/x/e/SZ均为同一canonical trace＋port复数complex128坐标。原teacher保存的归一化向量乘原normalization_scale还原raw RHS；只用0/10/11准确参考。三个参考的原A4相对残差分别3.95534643235e-12、3.92210413488e-14、7.55030409840e-14，port operation-relative为8.93422114155e-17、4.43684112021e-16、1.67720590810e-16；准确解残差r_star保留，未假定精确零。Se=r−r_star配对最大8.597625667e-14。D1独立进程先退出且后代清场，D2/D3从不加载teacher或D1输出。reference只输出标量/hash，无测试解或系数流入PC、基或在线初值。

## D1：同向量覆盖

eta_r表示残差位于SZ像空间之外的比例，eta_e表示准确解误差位于Z之外的比例；越小表示当下向量被覆盖越多，不等同于收敛率。绝对量、分母、gamma、Pythagoras缺陷、teacher/source/hash见[覆盖CSV](records/coverage_v5.csv)。比例无量纲，绝对量是原离散数组欧氏范数，不是能量或R/T/A。

| 空间 | 共同state | eta_r：残差空间外比例 | eta_e：解误差空间外比例 |
| --- | --- | --- | --- |
| OLDPOD | ZERO-000 | 0.9990665004 | 0.221630311 |
| OLDPOD | ZERO-010 | 0.6252571251 | 0.1087696805 |
| OLDPOD | ZERO-011 | 0.9020971783 | 0.3108998644 |
| OLDPOD | GEO-000 | 0.9891184815 | 0.219429691 |
| OLDPOD | GEO-010 | 0.6452668156 | 0.1087285639 |
| OLDPOD | GEO-011 | 0.9066069529 | 0.3107518967 |
| OLDPOD | OLDPOD-000 | 0.999067533 | 0.2216073402 |
| OLDPOD | OLDPOD-010 | 0.605861507 | 0.1081342627 |
| OLDPOD | OLDPOD-011 | 0.9014240417 | 0.3110674491 |
| OLDPOD | ERROR-000 | 0.9988296527 | 0.2216431682 |
| OLDPOD | ERROR-010 | 0.6541362892 | 0.1097081513 |
| OLDPOD | ERROR-011 | 0.9041332264 | 0.3163567527 |
| ERROR | ZERO-000 | 0.9997844639 | 0.7134416377 |
| ERROR | ZERO-010 | 0.750690256 | 0.2638518138 |
| ERROR | ZERO-011 | 0.929605057 | 0.4470868647 |
| ERROR | GEO-000 | 0.9970913714 | 0.7131200436 |
| ERROR | GEO-010 | 0.7764707867 | 0.2637963329 |
| ERROR | GEO-011 | 0.9371733142 | 0.4469442603 |
| ERROR | OLDPOD-000 | 0.9996746965 | 0.7135224713 |
| ERROR | OLDPOD-010 | 0.7706179312 | 0.2640284274 |
| ERROR | OLDPOD-011 | 0.9335331538 | 0.446666437 |
| ERROR | ERROR-000 | 0.9997845804 | 0.7135157193 |
| ERROR | ERROR-010 | 0.7384240036 | 0.2717528338 |
| ERROR | ERROR-011 | 0.929312393 | 0.4561181451 |


物理初态OLDPOD的eta_e=0.22163031099，ERROR=0.713441637661，而eta_r分别0.999066500398/0.999784463851。OLDPOD对解误差方向比ERROR覆盖好，但解基经过S后并没有覆盖大部分当前残差；不能把这一观察归结为rank128必然不足。port-only残差与误差覆盖较好，仍需看原方程终审。eta_r²+gamma_r²=1与r−SCr=Er都核验，exact-zero分支不换有利分母。

## D2：相同r的作用与保留方向反事实

最优复一步只给当前方向选择一个复系数，完整Schur目标为∥r−alpha Sd∥/∥r∥。BC小LS保留Br和Cr，ZB小LS保留整个128维Z和Br；最多2/129列，固定单位非零image列归一化后薄SVD与相对1e-10秩规则，不构造法方程或全局伪逆，不反馈新KSP。coefficients、列尺度、数值秩、三项分解幅值/复夹角/抵消以及raw数组hash见[action details](records/action_details_v5.json)。

| 空间 | 同一state的r | B最优复一步 | C最优复一步 | B2最优复一步 | BC小LS | ZB小LS |
| --- | --- | --- | --- | --- | --- | --- |
| OLDPOD | ZERO-000 | 0.9997052391 | 0.9990665004 | 0.999184407 | 0.9987340786 | 0.998253827 |
| OLDPOD | ZERO-010 | 0.984592493 | 0.6252571251 | 0.9926200741 | 0.6196581226 | 0.6171863522 |
| OLDPOD | ZERO-011 | 0.9903363329 | 0.9020971783 | 0.9909040321 | 0.8962186525 | 0.8936606399 |
| OLDPOD | GEO-000 | 1 | 0.9891184815 | 0.9991264581 | 0.9887630911 | 0.9882708962 |
| OLDPOD | GEO-010 | 0.999999999 | 0.6452668156 | 0.999852254 | 0.6445740952 | 0.6442535675 |
| OLDPOD | GEO-011 | 1 | 0.9066069529 | 0.9996623594 | 0.9065345102 | 0.9065011327 |
| OLDPOD | OLDPOD-000 | 0.9999940807 | 0.999067533 | 1 | 0.9990675315 | 0.9990675292 |
| OLDPOD | OLDPOD-010 | 0.99657259 | 0.605861507 | 0.9999999999 | 0.6056140707 | 0.6055050795 |
| OLDPOD | OLDPOD-011 | 0.9992365683 | 0.9014240417 | 1 | 0.9013756001 | 0.9013534654 |
| OLDPOD | ERROR-000 | 0.9999982585 | 0.9988296527 | 0.999649988 | 0.9986731933 | 0.9984824785 |
| OLDPOD | ERROR-010 | 0.9916792937 | 0.6541362892 | 0.9973165981 | 0.6526256487 | 0.6519634827 |
| OLDPOD | ERROR-011 | 0.9982437725 | 0.9041332264 | 0.9981925031 | 0.9032282443 | 0.9028277929 |
| ERROR | ZERO-000 | 0.9997052391 | 0.9997844639 | 0.9996865284 | 0.9995294033 | 0.9994714049 |
| ERROR | ZERO-010 | 0.984592493 | 0.750690256 | 0.9872461168 | 0.7492190712 | 0.7423358405 |
| ERROR | ZERO-011 | 0.9903363329 | 0.929605057 | 0.9793669308 | 0.9261185859 | 0.9136025977 |
| ERROR | GEO-000 | 1 | 0.9970913714 | 0.9999305564 | 0.9970351175 | 0.9970231024 |
| ERROR | GEO-010 | 0.999999999 | 0.7764707867 | 0.9965409355 | 0.776325226 | 0.775615168 |
| ERROR | GEO-011 | 1 | 0.9371733142 | 0.9928211189 | 0.9363599511 | 0.9334614844 |
| ERROR | OLDPOD-000 | 0.9999940807 | 0.9996746965 | 0.9999946987 | 0.9996703777 | 0.9996694528 |
| ERROR | OLDPOD-010 | 0.99657259 | 0.7706179312 | 0.9937536791 | 0.7701058518 | 0.7676538462 |
| ERROR | OLDPOD-011 | 0.9992365683 | 0.9335331538 | 0.9915190772 | 0.9323821238 | 0.9283750428 |
| ERROR | ERROR-000 | 0.9999982585 | 0.9997845804 | 1 | 0.9997845803 | 0.9997845803 |
| ERROR | ERROR-010 | 0.9916792937 | 0.7384240036 | 0.9999999996 | 0.7381356451 | 0.7367550972 |
| ERROR | ERROR-011 | 0.9982437725 | 0.929312393 | 1 | 0.92923533 | 0.9289614289 |


单位步会放大残差，不能只看其幅值断言某一项有害。下面额外列出初态的单位步和ZB修正的独立原方程结果：Schur一步改善与native/port改善不等价。

| 空间 | 初始RHS | B单位步Schur | B2单位步Schur | ZB-LS原A4 | ZB-LS port绝对 / operation-relative | 原1e-10全部审核 |
| --- | --- | --- | --- | --- | --- | --- |
| OLDPOD | ZERO-000 | 47.94591448 | 30.56032128 | 0.9975470081479971 | 0.0396184390011819 / 0.03918625697937228 | 未通过 |
| OLDPOD | ZERO-010 | 35.69421159 | 29.68541597 | 0.9554190180237655 | 0.000505986185336605 / 0.09191336408131998 | 未通过 |
| OLDPOD | ZERO-011 | 20.30630899 | 16.91600276 | 0.9050436032487064 | 0.0005029609599077161 / 0.10916910937914898 | 未通过 |
| ERROR | ZERO-000 | 47.94591448 | 43.0858075 | 0.9993369434239483 | 0.027636218832618648 / 0.023977861290978807 | 未通过 |
| ERROR | ZERO-010 | 35.69421159 | 14.32279431 | 0.8896813574688325 | 0.000656076148321124 / 0.06916207378762984 | 未通过 |
| ERROR | ZERO-011 | 20.30630899 | 8.913848506 | 0.8323702501659122 | 0.0006553415939453485 / 0.09180917754866492 | 未通过 |


[完整192行审核CSV](records/same_residual_actions_v5.csv)同时保存原native绝对量/分母、port绝对/operation分母/固定初始scale、internal/recovery/identity/slave/finite及每项剩余比例。physical固定port初始scale=0时用原绝对量，port-only/mixed初始scale=.001；未静默改分母。全部192修正均未达到原A4、port及恢复全套1e-10，因此没有新的严格粗解、场或observable。

两条新增关系用于解释组合，并非收敛保证：

```math
SB_2=\Pi+EHE,\qquad B_2r-Br=Cr-B\Pi r-CSBEr,
\quad H=SB,\quad E=I-UU^H.
```

每个真实r验证三项的S像相加、r−SCr、B2作用配对与rho_ZB≤rho_BC≤rho_opt(B)、rho_ZB≤eta_r。原U/R不重建、不形成n×n投影/private CSR。纯数组反例S=I2、B交换两坐标、Z=e1满足旧四恒等式却使B2=diag(1,0)，正常补空间控制也通过；这里只证明一般代数风险，不能将反例视作真实Maxwell奇异。

## D3：补空间完整输出

每空间固定12个Er方向加seed420805四个复随机方向，按1e-10去零/相关方向，薄QR后检查VᴴV=I及UᴴV≈0。真实H/T作用只在U正交补中测试；T在U上的固有零作用不当作新发现。

| 空间 / 探针rank | 完整HV最小奇异值 | 完整TV最小奇异值 | 小VᴴTV最小奇异值 | 见证∥Hv∥ / ∥Tv∥ / ∥PiHv∥ | Tv/Hv |
| --- | --- | --- | --- | --- | --- |
| OLDPOD / 16 | 6.121629043 | 4.771224799 | 0.03948169096 | 6.239773873 / 4.771224799 / 4.021217715 | 0.7646470682 |
| ERROR / 16 | 5.803778728 | 3.034800156 | 0.02601097338 | 8.227305139 / 3.034800156 / 7.647126118 | 0.368869284 |


上述奇异值属于21824×k的完整输出HV/TV，不是完整S/B2/T的谱或条件数。独立重算最弱TV右奇异组合v=Vw、Hv/Tv/PiHv及SB2v=Tv，并核对完整数组与冻结U，见[独立Gate](records/independent_checks_v5.json)。小VᴴTV数值远小于完整输出，遗漏V之外输出的风险在真实数据中可见；不能据此宣布T近奇异。所测最弱输出仍明显非零，没有near-null全局证据，也不能排除未采样方向。

## D4：证据归因与唯一建议

| 假设 | 本批评价 | 依据与限制 |
| --- | --- | --- |
| space_coverage | supported | 仅支持这些当前残差覆盖不足：physical eta_r OLD .989118–.999068 / ERROR .997091–.999785；ZERO-010 .625257/.750690，ZB反事实仅.617186/.742336；不是rank128普遍不足。OLD物理eta_e≈.22而ERROR≈.713，解误差与残差覆盖不可混称。 |
| fixed_combination_projection | supported | 同ZERO-010 r，Bopt .9845924930而OLD B2opt .9926200741 / ERROR .9872461168；保留Br＋Z的LS .6171863522/.7423358405。对应两个自身V4末态B2opt约1而Copt .605862/.738424。ERROR最弱补空间见证HV8.22731→TV3.03480，确有投影衰减但非near-null；不能把正常去粗分量自动称有害。 |
| local_complement_weakness | inconclusive | 本组完整HV最小奇异值6.121629/5.803779，TV最小4.771225/3.034800，没有近零B/T作用见证。Bopt多数.9846–1说明这些方向削减残差很弱；非正规累积和未采样方向仍不确定，不能将小VᴴTV .03948/.02601当真实T/B2奇异。 |


至少两个局部证据可并存：当前SZ像对物理残差覆盖很少；某些同r的平衡固定组合没有保留B与粗空间的有用Schur方向。解误差覆盖较好仍未产生严格原A4/port收敛，port-only的ZB改善也没有保持native最优；没有新的global奇异或唯一Maxwell模态根因结论。

**唯一下一最小试验（建议，未实施）：** 仅在已消费port-only RHS index10上，对比一条保留原Br＋冻结OLDPOD Z搜索方向的有界augmentation组织，其他S/B/Z/rank128、RIGHT FGMRES32/max256、原A4/port/恢复1e-10和资源预算保持；原B2历史作对照。它只检验固定组合是否丢失可用方向，不预测必然收敛。需下一review授权后实施。 所有其他空间/架构/预算扩展仍需新review，本批在D4结束。

## 资源、环境与完整成本

继续用户2026-09-28只对Task042的受控共享CPU授权，覆盖原task §2.3 heavy/全机独占要求，未修改其他任务合同或锁，也未宣称F0取得正式review。每次启动实时核查CPU拓扑、邻worker/监督器/加载线程的亲和性与活动、MemAvailable/cgroup/disk/GPU，只读轻检查；本轮D0/D1/OLDPOD实际CPU0，ERROR现场重新选择CPU13；编号不是默认或永久空闲承诺。MPI1、三实际OpenBLAS池threads1，自身nice10/idle I/O，独立FE activation及src/cache/JIT/TMP/bytecode/results/artifacts，原生ABI prefix仅只读。complex128/int64/PETSc3.19.6不升级，GPU不使用。

四次正式run整树RSS hard16GiB/warn12GiB、own swap0，独立nonblocking锁防重复。当前cgroup没有可写委派，真实沿用0.5s sampled launcher/subreaper＋所有后代停止策略，不能冒称连续内核限额。系统reserve216310038528B与邻增长128GiB合为353748992000B，另留Task04216GiB；基线实际MemAvailable约949GB、磁盘约3.45TB，原始逐次baseline及监督hash绑定见[run index](records/run_index_v5.json)。低开销5s健康采样包括PSI、disk/artifact、同PID/starttick邻CPU推进与可读短阶段；未发现持续压力触线，缺可比邻阶段耗时，影响仍inconclusive、不承诺绝对零干扰。

构造前预算representation/workspace296234496B、全部local＋小R因素302309536B，各低于512MiB。实测每PC 252patch LU298577664B＋cell/port3469728B＋R262144B，Z＋U89391104B；上界计入解压副本、诊断向量、n×16输出与QR/SVD、≤129²LAPACK、原FE审核及流式states。global p4 factor=false、teacher factor=false、fallback=false、private audit CSR=false；借用原S而不是宣称完全matrix-free。[容量/ownership](records/run_index_v5.json)。

| 独立one-run阶段 | 整树wall s | RSS同时峰 B | CPU / 实际数学线程 | 原runtime setup s | 原审核 calls / s | 释放 s |
| --- | --- | --- | --- | --- | --- | --- |
| V5-D0 | 143.1388741 | 628998144 | 0 / 1 | 101.0200733 | 12 / 32.430122 | 0.02097964298 |
| V5-D1 | 117.3564192 | 706514944 | 0 / 1 | 100.9278969 | 3 / 9.354902966 | 0.02018925699 |
| V5-OLDPOD | 433.4105782 | 1077854208 | 0 / 1 | 96.46427759 | 96 / 273.2924284 | 0.04124840209 |
| V5-ERROR | 450.4956571 | 1135407104 | 13 / 1 | 103.7834381 | 96 / 281.6764179 | 0.02210838394 |


四个不重叠正式监督wall合计1144.401529s，整树同时RSS峰取最大1135407104B（1.057430GiB），own swap0；不是峰值相加或累计对象体积。每空间local B/两层C/B2、exact S、LS代数、probe和I/O另在run index分项；setup、audit、probe计时包含下级B/C/S，禁止再相加。新reference factor/新teacher生成/训练成本均0（not_run）；D1是旧参考的实际读取/审核费用，非免费teacher。辅助前检、失败尝试、独立聚合/静态/发布另见[辅助账](records/post_checks_v5.json)；编辑/Git/审阅总会话wall与RSS未持续计量，不伪称精确全会话峰。

全部成本为shared-workstation；不把V3审核时间相减冒充提速，不声明神经贡献、无争用加速或严格解成本。自有后代正常释放，未操作邻任务、其环境/affinity/priority/锁/watchdog。

## 测试、文档及停止边界

执行前相关55测试通过，另外9项adapter/准入/监控/真实orphan监督测试通过，包含复数非Hermitian、相位/尺度/零/不可变、旧四恒等式反例与正常例、小LS和真实pool隐私。formal source clean提交后四stage只运行一次。Ruff最初FE环境缺模块，直接记录子命令失败；随后只读使用已有ruff0.16.6，修复一处新RUF005列表风格后通过。未重装环境、没重放数值；继承schema lint及registry checker保持与Review91基线相同、不伪称全绿。[前检](records/pre_run_checks_v5.json)、[最终静态](records/static_checks_v5.json)、[总账基线](records/registry_contract_baseline_v5.json)。

Review V2实际GitHub发布HTML有5表和7个math-renderer，表列一致、无裸math代码，review未改。[Review render](records/review_render_check_v5.json)；新文档真实发布检查在[publication](records/publication_checks_v5.json)记录精确发布HEAD/Markdown hash，与运行source区分。没有CI/full pytest/MPI2/MPI4声明，未因无关旧checker重跑昂贵Gate。

| not_run项目 | 原因 |
|---|---|
| V4训练轨迹/建基/六长KSP重放，新PC/新NN/换GPU或参数扫描 | 本合同只许冻结对象诊断 |
| seed420620 16项未用终测 | 数据边界保护，不生成、不读取；旧计划hash逐字保留 |
| F5/p6外层、5/2/0.7nm、official R/T/A/A_volume/衍射/EH/通道终态 | 旧严格粗逆未资格化，本review也没有授权 |
| 全局谱/shift-invert/大矩阵SVD/global p4 factor/hidden fallback | 明确禁止，不以额外计算填表或挑根因 |
| 唯一建议的新augmentation试验 | 仅提出，等待正式review，未实现 |

停止原因是完成本次有限D0–D4，不是资源不足，不是把旧停滞当代码bug。两空间原资格仍失败；诊断identity合格不能代替solver pass。只推送原执行分支后等待review，master不merge。

## Selective merge建议（当前无merge approval）

| 依赖组 | 内容 / 数值变化 | 测试/证据 / 建议顺序 |
|---|---|---|
| production numerical/core | 无资格化新增；原B/S/两层/default不变 | 不提升research路径为默认 |
| research-only numerical | fixed_localization bounded覆盖/作用/探针核及薄适配 | 55前检及独立真实raw Gate；需review后讨论 |
| reusable runner/watchdog | 仅4显式V5 profile/已有监督器的V5 index发布 | adapter/lock/own-tree测试；先既有接口再显式注册 |
| checker/benchmark | 独立raw/norm checker＋有限配置/4 one-run dat | 身份与包含关系/完整像重算；依赖研究核 |
| compact evidence/docs | 本中心说明、response_v5、records及总账新段 | 本轮负结果边界、hash/source/成本可审阅 |
| do-not-merge | ignored states/probes/teacher/checkpoints/cache及临时helpers | 不入Git，不复制大型旧结果，不改旧history |
