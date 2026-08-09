# Candidate H H2：coercive block smoother

## 1. 分类

| 项目 | 状态 |
|---|---|
| H2 | H2_NOT_RUN_GATED_BY_H1 |
| H1.1 前置 | PASS，tiny fixture |
| H1.2 前置 | CONTROLLED_STOP_TIMEOUT / NOT_QUALIFIED |
| H3 eligibility | false |
| Candidate H 当前 campaign | 在 H1.2 hard stop 后停止 |

H2 原计划验证一个更容易判断的 coercive proxy：给 curl-curl 问题配正质量项，
让算子具有强制性；再对相同材料、尺寸、orientation 和边界类别的 element block
只保存一份 factor，作为 exact-class-reused block smoother。这样可以先判断局部
平滑是否稳定，而不把原始时谐散射、DtN 和官方场结果混在同一个 Gate 中。

冻结的 proxy 形式为：

```math
B_h = K_{curl,h} + k_0^2 M_{|\epsilon|,h}.
```

本计划没有启动。H1.2 没有形成首个 source 的 action record、完整 payload 或
canonical identity，因此没有依据进入 H2。

## 2. H2 未运行项

| 量或对象 | 状态 |
|---|---|
| rho / contraction | not_run |
| block class count | not_run |
| factor payload | not_run |
| apply/action ratio | not_run |
| repeated action determinism | not_run |
| original time-harmonic FGMRES | not_run |
| official field / official RTA | not_run |
| global matrix | not_run |
| per-cell factors | not_run |
| slab factors | not_run |
| parameter scan | not_run |

这些字段均不填 0、不预测、不从 H1.1 或历史 G2 结果外推。H3 eligibility=false；
没有启动 H3/H4，也没有重新打开 G2 的 LOR-HX、G3 additive 路线或旧 G4 sweep。

## 3. 历史边界

G2 LOR-HX 仍为 G2_FAIL；G3 additive LOR-HX prohibited；旧 G4 sweep with failed
LOR-HX prohibited；ordinary default unchanged。H2 的未运行状态不改变这些历史结论。
