from __future__ import annotations

from pathlib import Path

REGISTRY = Path("docs/development_model_registry.md")


def replace_between(text: str, start: str, end: str, replacement: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        raise RuntimeError(f"start marker not found: {start!r}")
    end_index = text.find(end, start_index + len(start))
    if end_index < 0:
        raise RuntimeError(f"end marker not found: {end!r}")
    return text[:start_index] + replacement.rstrip() + "\n\n" + text[end_index:]


FULL3D_BLOCK = r'''### 1.2.1 Full 3D

Task034 的 `all_model_compact_fixture.json` 冻结了固定几何 S 偏振主线的 40 行事实。下表把其中所有正式 Full3D 求解或受控资源停止逐项登记；同一 `p/h` 只引用一个最新 authority，避免 Task032/033 与 Task034 重复计数。

| Task / 模型 | p/h | cells | FE DoF | total rows | matrix NNZ | factor NNZ | R00 | Rtotal | Ttotal | Avolume | true residual | peak GiB | total s | 状态 / 说明 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Task034 Full3D | p2/h5 | 1,680 | 44,698 | 44,778 | 4,896,156 | 31,053,132 | `0.0890130359` | `0.0890216029` | `0.442588279` | `0.468390118` | `9.707e-12` | 2.959606 | 16.5676 | `success`；低成本同网格基线 |
| Task034 Full3D | p2/h3 | 7,776 | 198,438 | 198,518 | 21,317,860 | 266,127,836 | `0.00460127305` | `0.00461303141` | `0.583653357` | `0.411733611` | 历史权威见 Case093 | 9.534939 | 152.972 | `success` |
| Task034 Full3D | p2/h2 | 24,570 | 615,108 | 615,188 | 65,448,472 | 历史主表未冻结 | `0.00133312476` | `0.00134293285` | `0.599213229` | `0.399443838` | 历史权威见 Case093 | 32.539612 | 1,235.54 | `success`；p2 最细正式点 |
| Task034 Full3D | p3/h10 | 252 | 23,073 | 23,153 | 历史主表未冻结 | 历史主表未冻结 | `0.0553826781` | `0.0553984905` | `0.406067867` | `0.538533643` | 历史权威见 Case093 | 2.744572 | 20.0918 | `success`；粗网格高阶起点 |
| Task034 Full3D | p3/h7.5 | 720 | 63,747 | 63,827 | 历史主表未冻结 | 历史主表未冻结 | `0.00307976819` | `0.00309072745` | `0.591160863` | `0.405748409` | `6.449e-12` | 4.609695 | 52.3277 | `success_with_qualifications`；固定-p等精度压缩点 |
| Task034 Full3D | p3/h5 | 1,680 | 145,863 | 145,943 | 35,566,727 | 历史主表未冻结 | `0.00108058337` | `0.00109010701` | `0.600622478` | `0.398287415` | `5.442e-12` | 9.040073 | 149.658 | `success`；MPI identity authority |
| Task034 Full3D | p3/h3 | 7,776 | 656,325 | 656,405 | 历史主表未冻结 | 历史主表未冻结 | `0.000780309834` | `0.000789467957` | `0.602514984` | `0.396695548` | 历史权威见 Case093 | 44.068672 | 1,726.36 | `success`；p3 收敛主点 |
| Task034 Full3D | p4/h10 | 252 | 53,084 | 53,164 | 历史主表未冻结 | 历史主表未冻结 | `0.00187216051` | `0.00188231722` | `0.596619520` | `0.401498163` | 历史权威见 Case093 | 5.639561 | 115.525 | `success` |
| Task034 Full3D | p4/h7.5 | 720 | 147,844 | 147,924 | 历史主表未冻结 | 历史主表未冻结 | `0.000793283286` | `0.000802469015` | `0.602429773` | `0.396767758` | 历史权威见 Case093 | 12.724396 | 345.384 | `success` |
| Task034 Full3D | p4/h5 | 1,680 | 339,892 | 339,972 | 155,205,040（assembly authority） | 历史主表未冻结 | `0.000757187647` | `0.000766313377` | `0.602677531` | `0.396556156` | 历史权威见 Case093 | 28.888458 | 917.470 | `success`；Task034 高阶固定几何参考 |

#### Full3D 资源停止（不是成功物理解）

| p/h | 已完成阶段 | rows / NNZ | measured peak | 预测或停止原因 | 状态 |
|---|---|---:|---:|---|---|
| p2/h1 | assembly | 4,379,832 / 461,122,320 | 67.922901 GiB | factor upper 418.821 GiB；未启动 factorization | `not_run_by_conservative_resource_gate_after_assembly` |
| p3/h2 | assembly | 2,047,298 / 488,789,000 | 64.014950 GiB | factor upper 232.460 GiB；未启动 factorization | `not_run_by_conservative_resource_gate_after_assembly` |
| p4/h3 | assembly | 1,540,028 / 696,091,072 | 80.537712 GiB | factor upper 204.132 GiB；未启动 factorization | `not_run_by_conservative_resource_gate_after_assembly` |

**证据：** `docs/task034_workstation_wsl_adaptive_scalability/outcomes/summary.md`、`benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/all_model_compact_fixture.json` 和 Case093 records。Task034 的非零衍射级与复振幅保存在 Case093 heavy/compact records；本表只登记跨全部固定网格都具有统一 authority 的总量、零级、规模和资源字段。'''

HYBRID_BLOCK = r'''### 1.2.2 Hybrid FEM–Modal

Hybrid 把上下短 3D FEM 区保留为完整 FE 矩阵，中间均匀长段改用二维本征模态传播。下表完整登记 Task034 固定几何中已经实际完成的 M160 Hybrid shard；`pass only` 表示线性求解与本 shard 物理量有效，但缺少同网格 Full3D closure 或 M funnel，不能提升为最终基准。

| Task / 模型 | p/h | local FE DoF（上下合计） | modal `2M` | total rows | R00 | Rtotal | Ttotal | Avolume | true residual | peak GiB | total s | 状态 / 说明 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Task034 Hybrid M160 | p2/h5 | 13,652 | 320 | 14,052 | `0.0890118197` | `0.0890210691` | `0.442586743` | `0.468392188` | `2.546e-12` | 3.284866 | 96.2844 | `success`；同网格 Full3D closure |
| Task034 Hybrid M160 | p2/h3 | 68,396 | 320 | 68,796 | `0.00460111770` | `0.00461281990` | `0.583650940` | `0.411736240` | `2.604e-12` | 4.695160 | 164.317 | `success`；同网格 Full3D closure |
| Task034 Hybrid M160 | p2/h2 | 180,696 | 320 | 181,096 | `0.00133309761` | `0.00134288473` | `0.599212676` | `0.399444439` | Case093 record | 11.305332 | 461.776 | `success`；同网格 Full3D closure |
| Task034 Hybrid M160 | p3/h10 | 7,194 | 320 | 7,594 | `0.0553792864` | `0.0553988021` | `0.406069310` | `0.538531887` | Case093 record | 2.867710 | 91.9203 | `controlled_negative`；formal closure 未通过 |
| Task034 Hybrid M160 | p3/h7.5 | 26,598 | 320 | 26,998 | `0.00307976491` | `0.00309064738` | `0.591159679` | `0.405749673` | Case093 record | 3.614460 | 117.671 | `success_with_qualifications`；固定-p等精度压缩 |
| Task034 Hybrid M160 | p3/h5 | 43,614 | 320 | 44,014 | `0.00108058359` | `0.00109009569` | `0.600622368` | `0.398287536` | `2.343e-12` | 4.908238 | 143.515 | `success`；MPI identity authority |
| Task034 Hybrid M160 | p3/h3 | 223,770 | 320 | 224,170 | `0.000780309829` | `0.000789467334` | `0.602514979` | `0.396695554` | `6.718e-12` | 14.271553 | 661.410 | `success`；M funnel authority |
| Task034 Hybrid M160 | p3/h2 | 595,956 | 320 | 596,356 | `0.000755344038` | `0.000764466671` | `0.602690128` | `0.396545405` | `3.613e-11` | 49.641502 | 3,513.82 | `success_with_qualifications`；仅 shard pass，无 Full3D closure/M funnel |
| Task034 Hybrid M160 | p4/h10 | 16,216 | 320 | 16,616 | `0.00187215501` | `0.00188234769` | `0.596619395` | `0.401498258` | Case093 record | 3.517616 | 136.253 | `success` |
| Task034 Hybrid M160 | p4/h7.5 | 61,064 | 320 | 61,464 | `0.000793283227` | `0.000802464969` | `0.602429757` | `0.396767778` | Case093 record | 5.967117 | 279.377 | `success` |
| Task034 Hybrid M160 | p4/h5 | 100,520 | 320 | 100,920 | `0.000757187631` | `0.000766313235` | `0.602677530` | `0.396556157` | `7.031e-12`（M160 funnel） | 9.205917 | 412.422 | `success`；高阶同网格 closure |
| Task034 Hybrid M160 | p4/h3 | 522,136 | 320 | 522,536 | `0.000753065135` | `0.000762184540` | `0.602706301` | `0.396531514` | `2.924e-11` | 42.481407 | 3,662.69 | `success_with_qualifications`；仅 shard pass，无 Full3D closure/M funnel |

#### Hybrid 资源停止

| p/h | measured progress | measured peak | status |
|---|---|---:|---|
| p2/h1 M160 | local factors/Schur 完成并进入 field recovery；7200 s timeout | 95.878723 GiB | `timeout_during_field_recovery_no_official_solution` |

#### M funnel

| case | MPI | M | total rows | R / T / Avolume | R00 | true residual | peak GiB | total s | 相邻 M 最大总量差 |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| p3/h3 | 8 | 80 | 224,010 | `0.000789467335 / 0.602514979 / 0.396695555` | `0.000780309830` | `2.076e-11` | 12.737340 | 529.556 | baseline |
| p3/h3 | 8 | 120 | 224,090 | `0.000789467334 / 0.602514979 / 0.396695554` | `0.000780309829` | `6.972e-12` | 13.708720 | 567.573 | `1.103e-9` |
| p3/h3 | 8 | 160 | 224,170 | `0.000789467334 / 0.602514979 / 0.396695554` | `0.000780309829` | `6.718e-12` | 14.271550 | 661.410 | `8.570e-12` |
| p4/h5 | 4 | 80 | 100,760 | `0.000766313235 / 0.602677530 / 0.396556158` | `0.000757187631` | `5.182e-12` | 5.048573 | 558.967 | baseline |
| p4/h5 | 4 | 120 | 100,840 | `0.000766313235 / 0.602677530 / 0.396556157` | `0.000757187631` | `5.726e-12` | 5.497772 | 634.194 | `1.107e-9` |
| p4/h5 | 4 | 160 | 100,920 | `0.000766313235 / 0.602677530 / 0.396556157` | `0.000757187631` | `7.031e-12` | 5.961403 | 734.218 | `8.713e-12` |

#### MPI identity：p3/h5

| method | MPI | rows | peak GiB | core/total s | max physical drift | identity |
|---|---:|---:|---:|---:|---:|---|
| Full3D | 1 | 145,943 | 6.339725 | core `1050.519`；total历史未冻结 | `0` | pass |
| Full3D | 8 | 145,943 | 9.013885 | core `150.511` | `8.776e-13` | pass |
| Full3D | 16 | 145,943 | 11.358720 | core `72.971` | `8.706e-13` | pass |
| Full3D | 32 | 145,943 | 15.772570 | core `41.948` | `8.817e-13` | exploratory pass |
| Hybrid M160 | 1 | 44,014 | 1.244774 | total `431.072` | `0` | pass |
| Hybrid M160 | 8 | 44,014 | 4.900311 | total `144.692` | `3.852e-13` | pass |
| Hybrid M160 | 16 | 44,014 | 7.149570 | total `134.132` | `1.942e-13` | pass |
| Hybrid M160 | 32 | 44,014 | 12.087820 | total `201.097` | `1.488e-13` | exploratory pass |

**证据：** `docs/task034_workstation_wsl_adaptive_scalability/outcomes/summary.md`、Case092 compact fixture、Case093 fixed-geometry records。Full3D/Hybrid各方法内的fields、interfaces、orders、complex amplitudes、QEP beta和true residual也通过对应MPI identity Gate。'''

TASK034_BLOCK = r'''## 3.35 Task034：WSL、固定几何 p2/p3/p4 收敛矩阵、Hybrid 与 graded-h

**研究对象。** Task034 在工作站WSL环境中冻结 `F-HO-S` 规则矩形光栅，完整计算 p2、p3、p4 的固定几何 Full3D/Hybrid 矩阵，并补充 M 漏斗、MPI identity、资源停止和 graded-h。该任务不是只得到一个 p4/h5 点，而是形成了26个固定几何主线/补充模型、6个 M-funnel模型和8个MPI identity模型，共40行统一事实。

**为什么重要。** 这些结果是后续高阶、静态凝聚、Hybrid和h/p自适应的基础：它们说明提高阶次能在较粗网格上迅速接近高阶参考，也说明“Hybrid rows少”必须与同网格Full3D物理闭合、M收敛和实际内存一起判断。

### 3.35.1 固定几何 Full3D / Hybrid 物理矩阵

| p/h | Full3D status | Full3D R/T/A | Full3D FE DoF / peak / total | Hybrid M160 status | Hybrid R/T/A | Hybrid rows / peak / total |
|---|---|---|---|---|---|---|
| p2/h5 | pass | `0.0890216029 / 0.442588279 / 0.468390118` | `44,698 / 2.959606 GiB / 16.568 s` | pass | `0.0890210691 / 0.442586743 / 0.468392188` | `14,052 / 3.284866 GiB / 96.284 s` |
| p2/h3 | pass | `0.00461303141 / 0.583653357 / 0.411733611` | `198,438 / 9.534939 GiB / 152.972 s` | pass | `0.00461281990 / 0.583650940 / 0.411736240` | `68,796 / 4.695160 GiB / 164.317 s` |
| p2/h2 | pass | `0.00134293285 / 0.599213229 / 0.399443838` | `615,108 / 32.539612 GiB / 1235.543 s` | pass | `0.00134288473 / 0.599212676 / 0.399444439` | `181,096 / 11.305332 GiB / 461.776 s` |
| p2/h1 | assembly stop | `not_run` | `4,379,752 / 67.922901 GiB / 792.958 s assembly` | timeout | no official output | `95.878723 GiB / 7200 s` |
| p3/h10 | pass | `0.0553984905 / 0.406067867 / 0.538533643` | `23,073 / 2.744572 GiB / 20.092 s` | formal not pass | `0.0553988021 / 0.406069310 / 0.538531887` | `7,594 / 2.867710 GiB / 91.920 s` |
| p3/h7.5 | pass | `0.00309072745 / 0.591160863 / 0.405748409` | `63,747 / 4.609695 GiB / 52.328 s` | pass | `0.00309064738 / 0.591159679 / 0.405749673` | `26,998 / 3.614460 GiB / 117.671 s` |
| p3/h5 | pass | `0.00109010701 / 0.600622478 / 0.398287415` | `145,863 / 9.040073 GiB / 149.658 s` | pass | `0.00109009569 / 0.600622368 / 0.398287536` | `44,014 / 4.908238 GiB / 143.515 s` |
| p3/h3 | pass | `0.000789467957 / 0.602514984 / 0.396695548` | `656,325 / 44.068672 GiB / 1726.362 s` | pass | `0.000789467334 / 0.602514979 / 0.396695554` | `224,170 / 14.271553 GiB / 661.410 s` |
| p3/h2 | assembly stop | `not_run` | `2,047,218 / 64.014950 GiB / 1334.645 s assembly` | shard pass only | `0.000764466671 / 0.602690128 / 0.396545405` | `596,356 / 49.641502 GiB / 3513.818 s` |
| p4/h10 | pass | `0.00188231722 / 0.596619520 / 0.401498163` | `53,084 / 5.639561 GiB / 115.525 s` | pass | `0.00188234769 / 0.596619395 / 0.401498258` | `16,616 / 3.517616 GiB / 136.253 s` |
| p4/h7.5 | pass | `0.000802469015 / 0.602429773 / 0.396767758` | `147,844 / 12.724396 GiB / 345.384 s` | pass | `0.000802464969 / 0.602429757 / 0.396767778` | `61,464 / 5.967117 GiB / 279.377 s` |
| p4/h5 | pass | `0.000766313377 / 0.602677531 / 0.396556156` | `339,892 / 28.888458 GiB / 917.470 s` | pass | `0.000766313235 / 0.602677530 / 0.396556157` | `100,920 / 9.205917 GiB / 412.422 s` |
| p4/h3 | assembly stop | `not_run` | `1,539,948 / 80.537712 GiB / 3035.139 s assembly` | shard pass only | `0.000762184540 / 0.602706301 / 0.396531514` | `522,536 / 42.481407 GiB / 3662.685 s` |

### 3.35.2 收敛指导

- p2需要细到h2才接近高阶中心，且Full3D峰值已达32.54 GiB；
- p3从h7.5到h3持续逼近高阶中心，p3/h3为正式M漏斗点；
- p4/h7.5已经接近p4/h5，说明规则结构的大部分场适合高阶逼近；
- p4/h5的 `R/T/A = 0.000766313377 / 0.602677531 / 0.396556156`，是Task034阶段的高阶工程参考；
- 后续Task035b/035c的p6/h10将离散参考进一步推进到 `R/T/A ≈ 0.000762881475 / 0.602701634 / 0.396535485`。

### 3.35.3 M 漏斗与MPI identity

M80→120的总量差约 `1.1e-9`，M120→160约 `1e-11`，所以当前13.5 nm固定结构在这些离散上M120已基本稳定，M160是保守正式点。p3/h5 Full3D和Hybrid在MPI1/8/16均通过，MPI32只作exploratory；更高rank降低core时间但增加进程复制内存，Hybrid MPI16相对MPI8只小幅加速。

详细6行M漏斗和8行MPI identity见第1.2.2；权威数据来自Task034 summary表2/表3和Case092/093 compact records。

### 3.35.4 graded-h 与资源负结果

| profile / case | 实际结果 | 状态 |
|---|---|---|
| conservative graded-h | raw DoF reduction `1.561×`；peak3.964GiB；112.12s | `controlled_negative`；未通过同误差Gate |
| balanced graded-h | raw DoF reduction `3.172×`；peak3.292GiB；96.63s | `controlled_negative` |
| aggressive graded-h | raw DoF reduction `9.590×`；peak2.537GiB；71.92s | `controlled_negative` |
| p2/h1 Full3D | assembly后预测factor upper418.821GiB | `not_run_by_resource_gate` |
| p3/h2 Full3D | assembly后预测factor upper232.460GiB | `not_run_by_resource_gate` |
| p4/h3 Full3D | assembly后预测factor upper204.132GiB | `not_run_by_resource_gate` |
| 0.7nm current layout | 多个单组件超过2TiB；simultaneous peak未知 | `production_feasibility_unknown / stress-test negative` |

**证据：** `docs/task034_workstation_wsl_adaptive_scalability/outcomes/summary.md`、Case092 `all_model_compact_fixture.json`、Case093 records、`all_model_authority_audit.json`。'''


def main() -> None:
    text = REGISTRY.read_text(encoding="utf-8")
    text = replace_between(
        text,
        "### 1.2.1 Full 3D",
        "### 1.2.2 Hybrid FEM–Modal",
        FULL3D_BLOCK,
    )
    text = replace_between(
        text,
        "### 1.2.2 Hybrid FEM–Modal",
        "---\n\n## 1.3 FEniCS 原始完整 FE 矩阵法：迭代求解",
        HYBRID_BLOCK,
    )
    text = replace_between(
        text,
        "## 3.35 Task034：WSL、高阶固定几何与 graded-h",
        "## 3.36 Task035：H(curl) goal-oriented adaptivity",
        TASK034_BLOCK,
    )

    coverage_note = (
        "> **2026-07-26 历史回填。** 本版重新核对 Task000–Task035c 的 outcomes、"
        "response、review 和 compact records。方法级成功表已补齐 Task034 的 p2/p3/p4 "
        "Full3D、Hybrid、M funnel 与 MPI identity；逐 Task 第3章继续保留失败、停止和未运行证据。\n"
    )
    marker = "> **维护规则。**"
    if "2026-07-26 历史回填" not in text:
        pos = text.find("\n", text.find(marker))
        if pos < 0:
            raise RuntimeError("maintenance paragraph not found")
        text = text[: pos + 1] + ">\n" + coverage_note + text[pos + 1 :]

    required_tokens = [
        "| Task034 Full3D | p2/h2 |",
        "| Task034 Full3D | p3/h3 |",
        "| Task034 Full3D | p4/h5 |",
        "| Task034 Hybrid M160 | p4/h5 |",
        "| p3/h3 | 8 | 80 |",
        "| Full3D | 16 | 145,943 |",
        "## 3.35 Task034：WSL、固定几何 p2/p3/p4 收敛矩阵、Hybrid 与 graded-h",
    ]
    for token in required_tokens:
        if token not in text:
            raise RuntimeError(f"registry backfill validation failed: {token}")
    if text.count("## 3.35 Task034") != 1:
        raise RuntimeError("Task034 section count drifted")
    REGISTRY.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
