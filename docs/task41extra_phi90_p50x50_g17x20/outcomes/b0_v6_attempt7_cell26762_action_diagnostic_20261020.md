# V6 attempt7 cell26762 保存样本 action 补诊断（2026-10-20）

本记录补充 attempt7 已保存的首个 V6 prefix 样本。它只描述 `cell26762` 的局部诊断，不能替代八键 prefix qualification、全域 action 门或最终数值结论。原 attempt7 receipt 保持不变。

## 证据身份与方法

| 项目 | 身份 |
|---|---|
| attempt | `task41_b0_v6_actual_qmetric_e58835fe_20261020T114318Z_attempt7` |
| source / execution contract | `e58835fe4c6bd8587cec1ad1555e3450a2d0b631` / `a2c5b85e0f556eb31b1d73bbe1fd4b53582049df0de852467b1218bf2ca9ec74` |
| 原 candidate receipt | `/home/fenics/Projects/laptop_share/results/task41extra_phi90_p50x50_g17x20/task41_b0_v6_actual_qmetric_e58835fe_20261020T114318Z_attempt7/task41_p0_v6_actual_qmetric_candidate.json`，SHA-256 `d2dcb419e89c4946eb960e7eca59281235c426d2d0625b7480a54f716e4b5990` |
| frozen donor manifest | SHA-256 `f55ac594382f40662954e19521ef9922d805abc64459cc7812877b12ec618465`；与 attempt7 receipt 绑定值相同 |
| 保存几何/dof-map 报告 | `task41_b0_v4_geometry_pair_02523b3d_attempt1/task41_p0_v4_geometry_pair_probe.json`，SHA-256 `a47eb7a8795b5af542c23ae45915588d89c962d1af1bb8360b8a9d42f1e7c031` |
| 原失败原因 | prefix receipt 的 `cell26762` 在 `local_action_comparisons` 为空时被保存为 `FAILED`；错误仅是 `TASK41_V5_FROZEN_DENOMINATORS` 未导入，发生于 action 循环开始处 |
| 补算范围 | 只读取上列哈希绑定 receipt、已保存的 `882×882` oriented tensors、`original_dofs` / trace map 和 donor 的 `known`、`j0`、`j3` 向量；用 NumPy memmap 读取该 cell 的 882 个值并执行小型矩阵向量乘。没有创建 mesh/function/form，没有重建 FE，也没有写入 attempt7 目录 |
| 误差口径 | `full_action_relative_frobenius = norm((C-R)x)₂ / norm(Rx)₂`；`difference_over_frozen_denominator = norm((C-R)x)₂ / d_column`。selected-row 值通过保存的 trace expansion 计算。它们仅为单元级诊断。 |

## 实际命令

以下是读取保存样本并得到本文件六行数值的实际只读命令；SSH 使用已有 agent，BatchMode 禁止交互认证：

```bash
source /home/shenjh/.ssh/task40_agent.env >/dev/null 2>&1
ssh -F /mnt/c/Users/admin/.ssh/config -o BatchMode=yes -o UserKnownHostsFile=/mnt/c/Users/admin/.ssh/known_hosts fenics-ws 'bash -s' <<'REMOTE'
set -euo pipefail
cd /home/fenics/Projects/laptop_share
python3 - <<'PY'
from pathlib import Path
import hashlib, json
import numpy as np
from scipy import sparse

run = Path('results/task41extra_phi90_p50x50_g17x20/task41_b0_v6_actual_qmetric_e58835fe_20261020T114318Z_attempt7')
receipt = json.loads((run / 'task41_p0_v6_actual_qmetric_candidate.json').read_text())
record = receipt['candidate_prefix_qualification']['records'][0]
if record['cell_index'] != 26762 or record.get('source') != 'V4_SAVED_ACTUAL_BLOCKS':
    raise SystemExit('saved first sample identity differs')

def load_record(ref, root=None):
    path = Path(ref['path'])
    if not path.is_absolute():
        if root is None:
            raise ValueError(f'no root for relative artifact path: {path}')
        path = root / path
    array = np.load(path, mmap_mode='r', allow_pickle=False)
    if list(array.shape) != ref['shape'] or str(array.dtype) != ref['dtype']:
        raise ValueError(f'artifact shape/dtype differs: {path}')
    return array

summary_path = Path('/home/fenics/Projects/laptop_share/results/task41extra_phi90_p50x50_g17x20/task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/20261019T053402.514018Z/task40_v10_p6_candidate_summary.json')
summary = json.loads(summary_path.read_text())
manifest_ref = summary['b0_recovery_evidence']['manifest']
manifest_path = Path(manifest_ref['path'])
if not manifest_path.is_absolute():
    manifest_path = summary_path.parent / manifest_path
manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
if manifest_sha != receipt['donor_manifest_sha256']:
    raise SystemExit('donor manifest SHA differs from attempt7 receipt')
manifest = json.loads(manifest_path.read_text())
donor_root = summary_path.parent

gprobe = json.loads(Path(receipt['geometry_reference_report_path']).read_text())['geometry_pair_probe']
cell = next(item for item in gprobe['selected_cells'] if item['cell_index'] == 26762)
geo = cell['geometry_and_dof_artifacts']
maps = cell['saved_map_artifacts']
original_dofs = np.asarray(load_record(geo['original_dofs']), dtype=np.int64)
trace_original = np.asarray(load_record(maps['trace_original_rows']), dtype=np.int64)
active_ids = np.asarray(load_record(maps['active_ids']), dtype=np.int64)
data = np.asarray(load_record(maps['trace_expansion_data']))
indices = np.asarray(load_record(maps['trace_expansion_indices']), dtype=np.int64)
indptr = np.asarray(load_record(maps['trace_expansion_indptr']), dtype=np.int64)
if np.unique(original_dofs).size != original_dofs.size:
    raise SystemExit('saved local original_dofs are not unique')
row_to_pos = {int(value): i for i, value in enumerate(original_dofs)}
try:
    trace_positions = np.asarray([row_to_pos[int(value)] for value in trace_original], dtype=np.int64)
except KeyError as exc:
    raise SystemExit(f'trace row missing from saved original_dofs: {exc}')
if trace_positions.size != trace_original.size or np.unique(trace_positions).size != trace_positions.size:
    raise SystemExit('saved trace map does not select unique local dofs')
expansion = sparse.csr_matrix((data, indices, indptr), shape=(len(trace_original), len(active_ids)))
if expansion.shape[0] != len(trace_positions):
    raise SystemExit('saved trace expansion shape differs from saved trace positions')

candidate = np.asarray(load_record(record['candidate_artifacts']['candidate_oriented_tensor']))
reference = np.asarray(load_record(record['reference_artifacts']['reference_oriented_tensor']))
if candidate.shape != (len(original_dofs), len(original_dofs)) or reference.shape != candidate.shape:
    raise SystemExit('saved oriented tensor shape differs from saved local dofs')
selected_active_row = 5458716
selected_locations = np.flatnonzero(active_ids == selected_active_row)
if selected_locations.size > 1:
    raise SystemExit('selected active row appears more than once')

def artifact_path(ref):
    p = Path(ref['path'])
    return p if p.is_absolute() else donor_root / p

def load_vector(record_ref):
    return np.load(artifact_path(record_ref), mmap_mode='r', allow_pickle=False)

for column_index, meta in enumerate(manifest['columns']):
    artifacts = meta['artifacts']
    state_refs = [('known', artifacts['known_field']), ('j0', artifacts['recovered_storage'])]
    final_step = meta['same_lu_refinement'][-1]
    state_refs.append(('j3', final_step['artifacts']['storage']))
    denominator = (2225.481253487629, 2225.4807123031883)[column_index]
    for state_label, ref in state_refs:
        vector = load_vector(ref)
        local_values = np.asarray(vector[original_dofs], dtype=np.complex128)
        ref_action = reference @ local_values
        cand_action = candidate @ local_values
        delta = cand_action - ref_action
        abs_frob = float(np.linalg.norm(delta))
        rel_frob = abs_frob / max(float(np.linalg.norm(ref_action)), np.finfo(float).tiny)
        max_abs = float(np.max(np.abs(delta), initial=0.0))
        if selected_locations.size:
            weights = np.asarray(expansion.getcol(int(selected_locations[0])).toarray()).reshape(-1)
            ref_row = complex(np.vdot(weights, ref_action[trace_positions]))
            cand_row = complex(np.vdot(weights, cand_action[trace_positions]))
        else:
            ref_row = cand_row = 0.0j
        print(json.dumps({
            'column': column_index, 'state': state_label,
            'full_action_relative_frobenius': rel_frob,
            'full_action_absolute_frobenius': abs_frob,
            'full_action_max_abs': max_abs,
            'full_action_relative_status': 'PASS' if rel_frob <= 1e-11 else 'FAIL',
            'full_action_difference_over_frozen_denominator': abs_frob / denominator,
            'selected_row_reference': [ref_row.real, ref_row.imag],
            'selected_row_candidate': [cand_row.real, cand_row.imag],
            'selected_row_difference_over_frozen_denominator': abs(cand_row-ref_row) / denominator,
            'denominator': denominator,
            'selected_row_present': bool(selected_locations.size),
        }, sort_keys=True, separators=(',', ':')))
PY
REMOTE
```

## 六个保存状态的离线输出

以下保留本次命令的实际 stdout。`full_action_relative_status` 是针对该 cell 的局部量比较结果；冻结分母比值也只是 diagnostic，不能单独代表全域验收。

```text
{"column":0,"denominator":2225.481253487629,"full_action_absolute_frobenius":8.28635752178784e-09,"full_action_difference_over_frozen_denominator":3.7234002797381465e-12,"full_action_max_abs":2.787290116262827e-09,"full_action_relative_frobenius":1.5859435858762255e-15,"full_action_relative_status":"PASS","selected_row_candidate":[-98574.57148431681,-63172.20629358962],"selected_row_difference_over_frozen_denominator":1.634693081054046e-14,"selected_row_present":true,"selected_row_reference":[-98574.57148431681,-63172.20629358958],"state":"known"}
{"column":0,"denominator":2225.481253487629,"full_action_absolute_frobenius":8.26898896924522e-09,"full_action_difference_over_frozen_denominator":3.715595876750973e-12,"full_action_max_abs":2.657229129810195e-09,"full_action_relative_frobenius":1.582619381673376e-15,"full_action_relative_status":"PASS","selected_row_candidate":[-98574.5714843104,-63172.20629358565],"selected_row_difference_over_frozen_denominator":1.4621139406341683e-14,"selected_row_present":true,"selected_row_reference":[-98574.57148431039,-63172.20629358562],"state":"j0"}
{"column":0,"denominator":2225.481253487629,"full_action_absolute_frobenius":8.047221463121853e-09,"full_action_difference_over_frozen_denominator":3.615946640984179e-12,"full_action_max_abs":2.5271779561988557e-09,"full_action_relative_frobenius":1.5401748271187325e-15,"full_action_relative_status":"PASS","selected_row_candidate":[-98574.57148431681,-63172.206293589654],"selected_row_difference_over_frozen_denominator":1.8494441004352746e-14,"selected_row_present":true,"selected_row_reference":[-98574.57148431678,-63172.206293589625],"state":"j3"}
{"column":1,"denominator":2225.4807123031883,"full_action_absolute_frobenius":1.7010098690448487e-08,"full_action_difference_over_frozen_denominator":7.643336828942653e-12,"full_action_max_abs":5.812611306467991e-09,"full_action_relative_frobenius":1.5990100913950032e-15,"full_action_relative_status":"PASS","selected_row_candidate":[133976.93667504407,-197149.14296863362],"selected_row_difference_over_frozen_denominator":3.9232643485748724e-14,"selected_row_present":true,"selected_row_reference":[133976.93667504398,-197149.14296863362],"state":"known"}
{"column":1,"denominator":2225.4807123031883,"full_action_absolute_frobenius":1.6827740765943168e-08,"full_action_difference_over_frozen_denominator":7.561395914560791e-12,"full_action_max_abs":5.295297790106459e-09,"full_action_relative_frobenius":1.5818677945256623e-15,"full_action_relative_status":"PASS","selected_row_candidate":[133976.93667503502,-197149.1429686208],"selected_row_difference_over_frozen_denominator":4.135483734811123e-14,"selected_row_present":true,"selected_row_reference":[133976.93667503493,-197149.14296862078],"state":"j0"}
{"column":1,"denominator":2225.4807123031883,"full_action_absolute_frobenius":1.685850079143603e-08,"full_action_difference_over_frozen_denominator":7.575217658924969e-12,"full_action_max_abs":5.426752390715603e-09,"full_action_relative_frobenius":1.5847593468951303e-15,"full_action_relative_status":"PASS","selected_row_candidate":[133976.93667504404,-197149.14296863362],"selected_row_difference_over_frozen_denominator":3.698889100352954e-14,"selected_row_present":true,"selected_row_reference":[133976.93667504398,-197149.14296863356],"state":"j3"}
```

| 列 / 状态 | action relative Frobenius | action absolute Frobenius | action max abs | absolute / frozen denominator | selected row difference / denominator |
|---|---:|---:|---:|---:|---:|
| 0 / known | 1.5859435858762255e-15 | 8.28635752178784e-09 | 2.787290116262827e-09 | 3.7234002797381465e-12 | 1.634693081054046e-14 |
| 0 / j0 | 1.582619381673376e-15 | 8.26898896924522e-09 | 2.657229129810195e-09 | 3.715595876750973e-12 | 1.4621139406341683e-14 |
| 0 / j3 | 1.5401748271187325e-15 | 8.047221463121853e-09 | 2.5271779561988557e-09 | 3.615946640984179e-12 | 1.8494441004352746e-14 |
| 1 / known | 1.5990100913950032e-15 | 1.7010098690448487e-08 | 5.812611306467991e-09 | 7.643336828942653e-12 | 3.9232643485748724e-14 |
| 1 / j0 | 1.5818677945256623e-15 | 1.6827740765943168e-08 | 5.295297790106459e-09 | 7.561395914560791e-12 | 4.135483734811123e-14 |
| 1 / j3 | 1.5847593468951303e-15 | 1.685850079143603e-08 | 5.426752390715603e-09 | 7.575217658924969e-12 | 3.698889100352954e-14 |

本地 action 对照逐行状态均为 PASS（相对比较限值 1e-11）。选中行参考/候选值也在上述命令 stdout 中逐项保留。六行数据只说明保存 cell 的局部对照通过；attempt7 仍是普通代码失败，且没有八键 prefix、全域 action、FE 收口或 official 结果。
