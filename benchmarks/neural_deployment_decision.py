"""One scalar-only, hash-bound cost/engine consumption; never invokes a solver."""

import argparse
import json
from pathlib import Path

from src.runners.task042_shared import write_json
from src.solvers.neural_deployment_cost import (
    frozen_v45_costs,
    necessary_time_condition,
    select_cold_n1,
    summarize,
)
from src.solvers.neural_engine_contract import (
    consume_contract,
    memory_condition,
    read_metadata,
)


def run(plan, root, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    parents = plan["parents"]
    loaded = {name: read_metadata(receipt, root) for name, receipt in parents.items()}
    cost, comparison, checker, inherited, dot = (
        loaded[name]
        for name in ("cost", "comparison", "checker", "inherited_cost", "dot_compact")
    )
    # The preserved scenario embeds old CL-E; check it against its actual source.
    if (
        cost["route_costs"]["CL44"]["inherited_V44_CL44_preparation_training_cost"]
        != inherited["route_costs"]["CL-E"]
    ):
        raise ValueError("inherited CL44 cost source mismatch")
    counts = checker["full_pass_by_route"]
    if comparison["qualification"] != counts:
        raise ValueError("frozen correctness inventory mismatch")
    routes = frozen_v45_costs(
        cost,
        comparison,
        evidence=parents["cost"],
        inherited_evidence=parents["inherited_cost"],
    )
    selection = select_cold_n1(routes, counts)
    offered = plan["dot_offered_contract"]
    if (
        offered["engineering"]["source_sha"] != dot["source_head"]
        or offered["problem"]["full_PDE_solved"] != dot["PDE_solved"]
    ):
        raise ValueError("dot offered contract not bound to frozen compact")
    if offered["problem"]["all_quotients_complete"] != dot["all532_quotient_qualified"]:
        raise ValueError("partial q0 inventory promoted to complete")
    consumed = []
    engine = consume_contract(
        plan["target_contract"], offered, lambda p: consumed.append(p) or "SCALAR_ONLY"
    )
    if consumed:
        raise ValueError("unexpected real partial engine acceptance")
    bounds = {
        "target_time": necessary_time_condition(
            common=None, unavoidable=None, variable=None, overhead=None, fraction=None
        ),
        "selected_zero_correction": {
            "fraction": 0,
            "classification": "derived_from_frozen_zero_decoder",
            "saving_identity": "f*V-H=-H<=0 for H>=0; no numerical work removed",
            "target_costs": "unknown; no unit placeholder is a measured second",
            "NN20": "NOT_DEMONSTRATED",
        },
        "selected_zero_semantics": "f=0 only for the frozen zero decoder; no numerical speedup from run-order noise",
        "target_memory": memory_condition(
            plan["baseline_memory_objects"],
            plan["neural_memory_objects"],
            time_seconds=None,
        ),
        "time_formula": "f*V-H >= .2*(C+U+V); necessary V >= .2*T_B+H; unknown common cost stays in percentage denominator",
        "memory_formula": "M_N <= .8*M_B AND complete time <=172800s; simultaneous live objects, not archive bytes",
    }
    records = {
        "cold_n1_cost_contract": {
            "routes": routes,
            "correctness": counts,
            "selector": selection,
            "summaries": {k: summarize(v) for k, v in routes.items()},
            "all_model_research_total_separate": cost[
                "all_three_new_model_research_costs_in_actual_batch"
            ],
            "numeric_actions": 0,
        },
        "engine_matching": engine,
        "benefit_necessary_conditions": bounds,
        "research_admission": {
            "status": "DEPENDENCY_CLOSED_NO_MATCHED_QUALIFIED_ENGINE",
            "closed_candidates": plan["closed_candidates"],
            "future_numeric_admission": False,
            "NN20": "NOT_DEMONSTRATED",
            "target_complete_solution": "NOT_QUALIFIED",
            "reentry_requires": plan["reentry_requires"],
            "numeric_actions": 0,
        },
    }
    for name, data in records.items():
        write_json(folder / (name + ".json"), data)
    return {
        "status": "SCALAR_DECISION_COMPLETE",
        "cost_selection": selection["status"],
        "engine": engine["status"],
        "numeric_actions": 0,
        "records": sorted(records),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    from src.solvers.neural_decision_scope import PLAN, plan_record, window

    window.guard_worker_parent()
    if args.plan.resolve() != PLAN:
        raise ValueError("V46 requires the single canonical frozen scalar plan")
    plan = plan_record()
    print(json.dumps(run(plan, root, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
