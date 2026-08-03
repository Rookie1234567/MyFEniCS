# Case129：M4H selective angle surrogate

This case is a training-only, response-blind qualification record.  It checks
the immutable train112 package, the five frozen outer folds, the two finite
cross-fitted risk rules, and the candidate/blind angle screening contracts.
It does not load Task003 validation data and it does not run a forward solver.

The expected result is a valid controlled-negative evidence package when no
predictor/risk pair passes every selective Gate.  A future model lock is not
created by this checker.

