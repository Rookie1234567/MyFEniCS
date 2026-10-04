"""Historical V44 API, delegating to the reusable explicitly scoped workflow."""

from src.solvers import neighborhood_late_error_scope as scope
from src.solvers.neighborhood_pilot_workflow import LateErrorStudy

study = LateErrorStudy(scope)


def graph_packet():
    return study.graph_packet()


def load_action(budget):
    return study.load_action(budget)


def model_for(code, action, *, diagnostic=False):
    return study.model_for(code, action, diagnostic=diagnostic)


def setup(folder, budget):
    return study.setup(folder, budget)


def data(folder, budget):
    return study.data(folder, budget)


def training_values(split, *, labels=True):
    return study.training_values(split, labels=labels)


def gradient(folder, budget):
    return study.gradient(folder, budget)


def validation(model, values, action, graph, mixed):
    return study.validation(model, values, action, graph, mixed)


def train(folder, budget, code, resume=None):
    return study.train(folder, budget, code, resume)


def evaluate(folder, budget, code):
    return study.evaluate(folder, budget, code)


def check(folder, budget):
    return study.check(folder, budget)


def diagnostic(folder, budget):
    return study.diagnostic(folder, budget)


def execute(role, folder, state):
    return study.execute(role, folder, state)
