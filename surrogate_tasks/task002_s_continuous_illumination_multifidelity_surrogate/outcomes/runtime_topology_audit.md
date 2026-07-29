# Actual runtime topology qualification

The earlier planned-helper self-comparison was replaced by an observer attached
to the actual solved field. On every formal p5 smoke it reads:

- distributed mesh cell geometry and resolved coordinate axes;
- actual cell material tags and boundary facet tags;
- actual Basix function-space element and global DoF count;
- actual Floquet constraint mode, physical entity blocks and constraint counts.

These runtime identities are canonicalized across MPI ranks and compared with
an independently constructed planned identity. The Gate covers cell geometry,
material tags, boundary/Floquet entities, axis counts, uniform N1curl p5 element
identity and the expected global DoF count `101815`.

Five MPI2/thread1 p5 smoke solves bind clean implementation SHA
`eaf17cd01f9e69eff4575b83ea94490a453e09bb`. All five planned-vs-actual and
formal numerical Gates passed. Runtime was 62.58–64.64 s, peak RSS was
4.251–4.272 GB, peak swap was zero and cleanup completed for every solve.

The points cover low/high grazing, axial/conical/high-azimuth illumination and
height/width perturbations. They are M3R runtime qualification only and are not
members of the frozen M4 training or validation dataset.
