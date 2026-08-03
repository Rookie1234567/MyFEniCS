# Case128 — Task004 M4G train112 local qualification

Case128 is a read-only, training-only audit of the final local qualification
after the one authorized Round1.  It recomputes the 112-row fold coverage,
tuple identity, OOF errors, composition, candidate set, paired-report
semantics, and outlier-audit references from the immutable train112 package.
It never opens blind responses and never launches FEM.

The six finite candidates are the four Review V5 local candidates plus the
latent-median and cross-fitted non-negative-stack ensembles.  A failed
Aggregate Level A is an intentional negative result; no model lock or blind
package is created in that case.
