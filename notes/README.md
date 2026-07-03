# notes 索引

`notes/` 只保存理论笔记、学习笔记、使用说明和解释性文档。任务书、Codex outcomes、ChatGPT review report 已统一迁移到根目录 `docs/`。

## 目录说明

| 目录 | 用途 |
|---|---|
| `theory/` | 数学模型、边界条件、R/T/A、DtN、PML、材料吸收等理论说明 |
| `quick_start/` | 日常运行入口、PyCharm/Docker/MPI 使用说明 |
| `reference/` | 代码阅读路线、当前版本边界、验证流程、外部对比和检查记录 |
| `test/` | 历史验证报告、测试记录、resume log |
| `parallel/` | 并行运行和并行后处理说明 |

## 当前重点笔记

- `reference/current_version_boundaries.md`：当前合并版本能力边界，优先阅读。
- `theory/THEORY_RTA_AND_VOLUME_ABSORPTION.md`
- `theory/stage4_3d_dtn_port.md`
- `theory/stage4_3d_block_grating_diffraction.md`
- `theory/reflection_transmission_metrics.md`
- `quick_start/stage4_3d_block_grating_usage_guide.md`
- `quick_start/stage2_2a_2b_2c_usage_guide.md`
- `quick_start/2d_euv_grating_dtn_usage_guide.md`
- `reference/code_walkthrough.md`

## 当前版本边界摘要

当前版本可以较有信心使用：

```text
2D EUV DtN port 主线；
3D Stage 1 / Stage 2 / flat-layer sanity / stage4_block_grating smoke 路径；
Stage 4 dtn_port + A_volume 主线；
small-cell flat-layer p=1/p=2 收敛；
MPI 1/4/8 主线一致性。
```

当前不能过度声称：

```text
真实 100 nm 3D EUV grating 已完成物理收敛 benchmark；
probe_eh_fourier / net_flux 已能替代 port 作为主 R/T；
Stage 2B/2C 粗网格 smoke 代表 PML/Fresnel 精度通过。
```

详细说明见：

```text
notes/reference/current_version_boundaries.md
```

## 任务流转记录

任务闭环资料请看：

```text
docs/
```

每一轮任务都放在独立目录中：

```text
docs/taskXXX_task_name/
├── task.md
├── outcomes/
└── review_report.md
```
