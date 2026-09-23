# Review V5 migration checklist (working record)

Scope: selective V20/V19/Q4/Q3 migration for the four authorized profiles;
not a whole-source merge and not a formal-run qualification.

## Frozen inputs and evidence

- Migration baseline: `ea717ed5c6ffe45214ecdeca80cabdaeaef5960b`; Q4 anchor
  `4bf2bba56cc2e568d56ff3096aeb4a108744f28d`; Q3 qualification
  `cad282e25ed53cad1f9e4a5a70c14f3dd40e6d32`.
- V5 source review and inherited constraints: task-local `review_report_v5.md`
  and `review_report_v4.md`; old D3 controlled stop and H0/H1 measurements are
  indexed in `v5_h0_h1_m_a_profile_checks_v1.json`.
- Exact R13 frozen axes and plan hashes are sourced mechanically from the
  frozen V21 plan; q3/q4 inputs use the same 9x5x22 mesh plan. Their `q` is
  the coarse Nedelec degree, not an integration order. Report windows are
  m,n=-2..2; DtN mode inventory remains separate and complete.

## M-a complete as configuration-layer work

- Added opt-in x/y/z frozen-axis identity only for R13; 5 nm and 2 nm inputs
  retain their existing boundary-fitted geometry identity.
- Added the four V5 profile identities and CPU24 worker/CPU9 parent contract;
  legacy profiles retain CPU23. Generated argv was exercised without starting
  a process.
- The M-a input/profile/argv tests passed under both the standard activation
  and the restored task-local PORD64 activation. Their scope is still only
  configuration/argv; FE and numerical qualifications are listed separately.
- The prior `/tmp` stacks were absent. The pinned int64 base and PORD64 overlay
  were restored under `tmp/task39extra_v5_abi_restore_20260923/base`; the
  current fixed activation roots and binary/config SHA256 values are recorded
  in `v5_m_c_and_four_input_contract_v1.json`. Historical `/tmp` build records
  remain unchanged and are not presented as the current installed paths.

## Selective M-b/C component qualification

- V5 `run_case` dispatch reaches `physical_intermediate.run_physical_intermediate`
  and `run_retained_condensed_workflow`; that workflow builds levels `(6,q)`,
  opts V5 into `build_packed_physical_action(sum_factorized_work=True)`, uses
  the optimized fixed-serial owner route, and assembles the exact coarse Aq
  inverse. The corresponding factory/backend labels are V5-specific; legacy
  profile facts remain on their historical implementation labels.
- Selective source lineage: Q4 anchor `4bf2bba56cc2e568d56ff3096aeb4a108744f28d`
  and Q3 qualification `cad282e25ed53cad1f9e4a5a70c14f3dd40e6d32`. The
  actual per-file donor/target blob table and call-path checks are recorded in
  `v5_m_c_and_four_input_contract_v1.json`; D2 P4 refinement ledger, raw
  geometry identity, and cache inventory/lifecycle fixes remain target-owned.
- Component evidence includes q3/q4 990-cell split Aq projection, q3/q4
  18-cell same-object setup, real material and H6/A6 comparisons, source 362
  sum-factorized cases, source 323 optimized-owner cases, actual PORD64
  FE/MPC/MUMPS fixture, and the pair checker/schema plus canonical recovery
  roundtrip. These are component qualifications, not full-run results.
- R13 pair comparison is implemented but not executed before both formal runs.
  Numerical pair success is not the final `R13_PAIR_RELEASE`; common-path
  qualification and sustained hardware review remain separate release gates.
  No formal run has started.
