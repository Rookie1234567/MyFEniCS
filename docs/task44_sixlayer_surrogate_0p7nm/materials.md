# Task44：0.7 nm 六层材料与来源

## 结论及适用范围

本文件给出能重复计算的**连续介质测试模型**。Si 沿用指定母版本的光学常数；SiGe 和 SiO2 由各自元素散射因子与明确密度计算，**不是该薄膜的实测光学常数，也没有把 Si 值复制给其他材料**。这足以定义本次代理模型拟合的数值对象，但不能证明亚纳米薄层的实际器件与此对象一致。

材料身份文件为 [`input/materials/task44_0p7nm.json`](../../input/materials/task44_0p7nm.json)。源模块 [`sixlayer_materials.py`](../../src/common/sixlayer_materials.py) 仅依赖 Python 标准库，加载时复算并逐字段核对完整 JSON，不自动下载、不运行有限元。

| 材料 | 密度 (g/cm³) | 求解器复折射率 n（约值） | 相对介电常数 εr（约值） | 身份 |
|---|---:|---|---|---|
| Si（衬底和第1/3/5层） | 2.3291 | 0.9998851703688496 + 4.32361522691895e−6 i | 0.9997703539048498 + 8.64623749555442e−6 i | 指定母源精确继承；元素数据推导，不是本样品实测 |
| Si0.7Ge0.3（第2/4层） | 3.33199 | 0.999827977741799 + 3.95932605324180e−5 i | 0.9996559835076291 + 7.91728992206632e−5 i | DERIVED，随机合金、独立原子测试模型 |
| 非晶 SiO2（第6层） | 2.2 | 0.9998683932886525 + 8.33132393731389e−6 i | 0.9997368038282206 + 1.66604549583387e−5 i | DERIVED，任务指定密度的化合物测试模型 |

空域使用 n=1、εr=1、μr=1。三种材料 μr=1。表中多位小数用于复现，**不是物理精度声明**；完整浮点值以机器文件为准。六层顺序自下而上为 `Si, SiGe, Si, SiGe, Si, SiO2`。

## 波长、插值与符号

波长0.7 nm 对应光子能量 **1771.2028347600037 eV**，不是0.7 eV，也不沿用13.5 nm 常数。采用母源 `hc/e=1239.8419843320025 eV·nm`、`r_e=2.8179403205e−15 m`、`N_A=6.02214076e23 mol⁻¹`。

| 元素 | 下端 E / f1 / f2 | 上端 E / f1 / f2 | 本次 f1 / f2 |
|---|---|---|---|
| Si | 1756.82 / 10.6935 / 0.399988 | 1785.24 / 10.2377 / 0.388059 | 10.462828075875802 / 0.3939509544035157 |
| Ge | 1752.89 / 29.3384 / 11.6634 | 1781.24 / 29.5711 / 11.3904 | 29.488713814767298 / 11.487054183792557 |
| O | 1752.89 / 8.35021 / 0.67503 | 1781.24 / 8.3471 / 0.655908 | 8.34820107879705 / 0.6626780414010304 |

三种元素都对 f1、f2 **按光子能量作线性插值**，沿用冻结 Si 的明示算法；不是对数插值，不外推。JSON 保存原始行号、两端数据、插值比例和全表 SHA256。Si 的区间在表中1838.8/1839.0 eV K 吸收边以下，没有跨边插值；这并不意味着化学态误差已经可忽略。

[CXRO 符号说明](https://henke.lbl.gov/optical_constants/pert_form.html) 使用 n=1−δ−iβ。本求解器固定 `exp(i k·r) exp(−i ωt)`，故使用其共轭 **n=1−δ+iβ，εr=n²**。β>0、Im(εr)>0 表示被动吸收。端口需继续采用自身已资格化的向外传播/衰减分支；材料加载器没有替端口程序证明此分支。

## 从成分与密度得到光学常数

将材料看作独立原子集合，并把各元素的散射贡献相加；这不是对折射率或介电常数作质量分数插值。令 νj 为化学计量数，M 为每摩尔化学式单位的质量：

```math
M=\sum_j\nu_j M_j,\qquad N_f=\frac{\rho}{M}N_A,\qquad
\delta+i\beta=\frac{r_e\lambda^2N_f}{2\pi}\sum_j\nu_j(f_{1,j}+if_{2,j}).
```

上式使用 SI：ρ 为 kg/m³，M 从 g/mol 除1000转为 kg/mol，λ 从 nm 乘1e−9转为 m。

- **SiGe：** x=0.3 是 Ge 原子/摩尔分数；νSi=0.7、νGe=0.3，M=0.7×28.0855+0.3×72.64=41.45185 g/mol。因 ν 总和为1，此处 Nf 就是总原子数密度。
- **SiO2：** νSi=1、νO=2，M=28.0855+2×15.9994=60.0843 g/mol。此处 Nf 是化学式单位数密度，总原子数密度为3Nf；散射因子为 fSi+2fO，不能再次乘3。
- **密度：** Si 精确保留母源2.3291 g/cm³（20°C）。SiGe 使用 [Ioffe Institute NSM](https://www.ioffe.ru/SVA/NSM/Semicond/SiGe/basic.html) 的300 K 随机合金密度拟合 `2.329+3.493x−0.499x²`，所得3.33199 g/cm³仅声明为本次**松弛体材料测试假设**，不是应变外延薄膜测量。SiO2 的2.2 g/cm³来自本任务明确指定，不声称查到本样品密度。
- Ge 的72.64 g/mol取 [NIST Chemistry WebBook](https://webbook.nist.gov/cgi/cbook.cgi?ID=C7440564&Mask=20)；O 的15.9994 g/mol取 [NIST O2 的31.9988](https://webbook.nist.gov/cgi/cbook.cgi?ID=C7782447&Mask=20) 除2。它们是明确冻结的表值，不冒称最新同位素特定原子量；Si28.0855沿用母源。

## 来源和可重现性

1. 母源仓库 `Rookie1234567/MyFEniCS`，指定提交 **`db790f92a186988c5147f1828d15c07034e7c430`**。原文件 `docs/task40extra_0p7nm_engineering/outcomes/records/material_identity.json` 的完整4920 B副本为 [`base_si_material_identity.json`](materials_sources/base_si_material_identity.json)，SHA256 `5faedf276aba2918cc399c018936964b059127f135e24ea2bf2ba493e3d9876b`。继承其 Si n/ε 精确数值，而不因当前重算微调。
2. 2026-10-30 从官方 CXRO 获取三个完整小表：[`si.nff`](https://henke.lbl.gov/optical_constants/sf/si.nff)、[`ge.nff`](https://henke.lbl.gov/optical_constants/sf/ge.nff)、[`o.nff`](https://henke.lbl.gov/optical_constants/sf/o.nff)。本地原字节副本在 `materials_sources/`；Si 当前全表 SHA 与母源记录相同。
3. Ioffe 密度行在官方页面的检索索引中实际可读；直接HTTP下载返回503。保存的是 [`density_source_observation.json`](materials_sources/density_source_observation.json) 的**观察记录**，不是伪造原 HTML，其 `original_html_sha256=null`。页面归因 Schaffler F. et al. (2001)，此轮未直接取得该原出版物；本方法没有采用该页的红外折射率或静态介电常数充当 X 射线值。
4. 独立原子公式/局限参见 [CXRO 说明](https://henke.lbl.gov/optical_constants/intro.html)，原数据文献为 Henke, Gullikson & Davis, *Atomic Data and Nuclear Data Tables* 54 (1993),181–342。原始表含测量与理论汇编成分，不是三个薄膜各自测得的n。

在本任务当日已资格化的 cloud activation 后，可用：

```bash
python -m src.common.sixlayer_materials
python -m unittest src.test.test_task44_materials -v
```

第一条核对全部来源及完整材料JSON；仅在文件尚不存在时，`--write` 才允许从原始表创建材料文件，不覆盖旧文件。API `load_sixlayer_materials()` 返回 `refractive_indices`、`epsilon_r` 两个 complex 映射（键 `air/Si/SiGe/SiO2`），以及完整 JSON `identity`、规范树 `identity_sha256`、实际文件 `file_sha256`。每种材料也含自身 `identity_sha256`。这些是**材料数据/软件核验**，不冒充 PDE、样品或代理精度资格。

2026-10-30 在当日恢复并独立资格化的 Python 中实际完成12个定向标准库测试：**12通过、0失败，0.151 s（含测试导入），未导入 NumPy/FE/MPI/PETSc**；收据见 [`targeted_tests_20261030_v2.json`](materials_sources/targeted_tests_20261030_v2.json)。第一次测试中一个负例把 Si 化学计量重新写成其原值，故没有发生应被拒绝的改变；已把负例改为 Si2，保留[首次失败收据](materials_sources/targeted_tests_20261030_v1.json)，材料代码/公式/JSON 未因此修改。

## 仍未验证的物理事项

- 该随机体合金密度不包含实际应变、超薄膜松弛、界面互扩散、孔隙和氧化；非晶 SiO2 的标签不使独立原子模型自动包含键合细节。
- 吸收阈附近化学态会影响 X 射线响应；现有表不能为此具体薄膜给可靠误差条，未编造百分比不确定度。
- 0.5–1 nm 各层以及小横向尺寸接近原子尺度；连续介质与尖锐界面在此只定义算法测试模型，未建立原子尺度或实验真实性。
- 代理模型即使以很少样本拟合这些有限元输出成功，也只证明对该冻结材料模型的插值可行性，不证明标准尺寸实验器件预测准确。
