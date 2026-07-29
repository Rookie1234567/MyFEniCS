# Task002：S 偏振连续照明四维多保真前向代理与角度设计

> **Review V4 / M3R 权威覆盖（2026-07-29）**
>
> 当前生产路线已冻结为单保真
> `Full3D static uniform N1curl p5/h10/MPI2`，observable 使用覆盖
> `n=0, m=-7..+3` 的 v3。`p4/h10`、`p4/h7.5` 与全部 Hybrid
> 路线仅保留 diagnostic 身份，不得进入 production campaign 或 dataset。
> 本文件下方关于 Hybrid LF/HF、多保真训练和旧样本预算的内容是原始任务书历史，
> 已由 `review_report_v4.md` 覆盖。当前仅授权 M3R；M4、正式 p5 bulk、
> surrogate training、angle DOE 与 inversion 均未获授权。

## 当前身份

```text
status = ready_for_codex_execution
execution_branch = codex/only-one-13p5nm-surrogate-inversion
parent_authority = ../task001_two_parameter_hybrid_multifidelity_pilot/review_report_v3.md
hardware_phase_1 = local 16 GB Windows laptop + WSL2 Ubuntu
hardware_phase_2 = workstation surrogate training and angle design
wavelength_nm = 13.5 fixed
polarization = S fixed
invertible_parameters = height_nm, width_x_nm
forward_surrogate_inputs = height_nm, width_x_nm, grazing_deg, azimuth_deg
production_inversion = out_of_scope
```

Task002 的目标是建立一个经过独立高保真验证的连续前向代理：

```text
(height, width, grazing angle, azimuth)
    -> diffraction responses + R/T/A + predictive uncertainty
```

它既用于快速前向预测，也用于在连续角度域内筛选最适合区分高度和宽度的测量角度。正式实验反演留给 Task003。

## 正式参数域

```text
height_nm  in [115, 125]
width_x_nm in [16, 18]
grazing_deg in [0.5, 10.0]     # 相对样品表面
azimuth_deg in [0, 90]
wavelength_nm = 13.5
incident_polarization = S
```

内部角度约定：

```text
solver incident_theta_deg = 90 - grazing_deg
solver incident_phi_deg = azimuth_deg
```

精确 `grazing_deg=0` 的普通法向功率归一化退化，不属于正式训练域。用户接口对 0°必须返回结构化 limit 状态，不能静默外推。

## 数值保真度

```text
production = S_PROD_FULL3D_STATIC_P5_H10
             Full3D static uniform N1curl p5/h10/MPI2

diagnostic only = Full3D p4/h10, Full3D p4/h7.5, all Hybrid routes
```

P 偏振不进入 Task002 V1。需要 P 时保留 Full3D assembly-time static-condensed direct route；Hybrid-P 改造延期。

## 主要工作

1. 连续角域和传播级/cutoff 解析审计；
2. 中心几何角度 pilot，确认整个 S 角域求解稳定且响应可代理；
3. 四维嵌套 LF/HF 采样设计；
4. 正式数据生成、Gate、manifest 和不可混源数据集；
5. sparse PCE/Chebyshev 诊断基准；
6. Matérn GP 与 autoregressive multi-fidelity discrepancy surrogate；
7. 冻结 HF 验证、主动加点和最终 model selection；
8. 连续角度 Fisher/DOE 排名；
9. forward-surrogate CLI/API 与模型卡。

## 默认预算边界

Task002 使用 staged budget，不要求一开始全部用完：

```text
LF angle pilot at center geometry:        up to 49
LF four-dimensional initial design:       128 Sobol + bounded anchors
HF initial nested training:               24--32
HF frozen validation:                     12--16
HF adaptive additions:                    16--32
```

任何扩展必须由验证误差、cutoff 邻域、LF-HF discrepancy 或 surrogate uncertainty 触发，而不是为了凑固定样本数。

## 代理模型边界

只比较有明确角色的模型：

```text
1. low-order sparse PCE/Chebyshev = smoothness/interpretability diagnostic
2. Matérn-5/2 ARD GP = single-fidelity nonlinear baseline
3. y_H = rho*y_L + delta(x) = production multi-fidelity candidate
```

禁止建立模型动物园；当前不使用神经网络、随机森林或大量无依据超参数搜索。

## 输出合同

每个 FEM 样本继续保存 fixed-order mother response：

- fixed `(side,m,n)` identity；
- complex `kx,ky,kz`；
- outgoing S/P complex boundary amplitudes；
- S/P power 与 order total；
- R/T/A/Avolume；
- numerical Gate、resource 和 provenance；
- prediction/measurement availability mask。

正式代理至少输出：

```text
selected measurable diffraction powers
R_total, T_total, A_balance
predictive uncertainty
propagation/cutoff flags
training-domain and distance diagnostics
```

复振幅代理作为第二层物理审计；不能因它尚未通过而阻止第一版功率代理，除非任务书中的 Gate 明确要求。

## 主要交付

```text
surrogate_tasks/task002_s_continuous_illumination_multifidelity_surrogate/
    README.md
    task.md
    outcomes/
        summary.md
        test_summary.md
        continuous_angle_qualification.md
        sampling_design.md
        dataset_manifest_report.md
        surrogate_selection.md
        validation_report.md
        illumination_design.md
        model_card.md
    response_v1.md

benchmarks/cases/112_s_continuous_illumination_multifidelity_surrogate/
    README.md
    config.json
    expected.json
    test_command.txt
    records/
```

## 完成定义

Task002 只有在以下条件全部满足时结束：

- S 连续角域 pilot 完成，失败点有明确 disposition；
- 一个 clean dataset source SHA 被冻结；
- LF/HF 数据集完成并通过全部 Gate；
- frozen HF validation 从未进入训练或 adaptive selection；
- 生产 surrogate 达到预先冻结的噪声归一化误差 Gate；
- surrogate uncertainty 对验证误差具有合理覆盖；
- 角度 DOE 给出单角度及 2--4 角度组合，并由必要 HF 点复核；
- CLI/API 对域内、域外、cutoff 邻域和 0°极限均 fail closed；
- 不执行正式实验反演或 Bayesian posterior。
