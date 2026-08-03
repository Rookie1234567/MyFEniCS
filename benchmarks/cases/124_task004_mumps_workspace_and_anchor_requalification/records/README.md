# Case124 records

The five design JSON files are the tracked, response-blind design contract.
Heavy solver output is intentionally kept under the ignored artifact root:

`benchmarks/artifacts/cases/124_task004_mumps_workspace_and_anchor_requalification/`

`checker.py` resolves the manifests and re-reads the named execution and
compact-record files.  It does not run a solver and does not read any blind
validation or Task003 validation response.
