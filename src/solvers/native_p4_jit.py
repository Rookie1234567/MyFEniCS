"""Native FFCx loop scheduling; each output retains its summation order."""
import re
from contextlib import contextmanager

OLD = 'for (int j = 0; j < 300; ++j)\n    {\n      for (int i = 0; i < 300; ++i)'
NEW = 'for (int i = 0; i < 300; ++i)\n    {\n      for (int j = 0; j < 300; ++j)'
BASE_FLAGS = ['-O3', '-march=native', '-mprefer-vector-width=512', '-ffp-contract=off', '-g0']
FLAGS = [*BASE_FLAGS, '-DMYFENICS_NATIVE_P4_ROW_LOOP_V1=1']
FINE_CURL_FLAGS = [*BASE_FLAGS, '-DMYFENICS_NATIVE_CURL_FUSED_V1=1']
FUNCTION_SECTION = re.compile(r'  // Section: Function\n.*?  // ------------------------ ', re.DOTALL)


def _row_loop(ir, domain, implementation):
    if list(ir.expression.tensor_shape) != [300, 300] or domain.name != 'hexahedron':
        raise ValueError('native row loop requires p4 hexahedron tensor')
    if implementation.count(OLD) != 1:
        raise ValueError('unexpected FFCx p4 matrix loop structure')
    return implementation.replace(OLD, NEW)


def _fused_curl(ir, domain, implementation):
    shape = list(ir.expression.tensor_shape)
    if shape not in ([300], [882]) or domain.name != 'hexahedron':
        raise ValueError('native fused curl requires p4/p6 hexahedron action')
    sections = list(FUNCTION_SECTION.finditer(implementation))
    declarations, updates = [], []
    for match in sections:
        declarations.extend(re.findall(r'  double _Complex (w\w+) = 0.0;', match.group()))
        updates.extend(re.findall(
            r'      (w\w+ \+= w\[ic\] \* FE\w+\[0\]\[0\]\[iq\]\[ic\];)', match.group()))
    if (len(sections) != 12 or len(declarations) != 12 or
            [line.split()[0] for line in updates] != declarations):
        raise ValueError('unexpected FFCx curl coefficient loops')
    fused = '\n'.join('  double _Complex '+name+' = 0.0;' for name in declarations)
    fused += f'\n  for (int ic = 0; ic < {shape[0]}; ++ic)\n  {{\n'
    fused += '\n'.join('    '+line for line in updates)+'\n  }\n'
    for match in reversed(sections[1:]):
        implementation = implementation[:match.start()] + implementation[match.end():]
    first = sections[0]
    return implementation[:first.start()] + fused + implementation[first.end():]


@contextmanager
def _scoped_codegen(transform):
    # Formal native execution is single-threaded; restore the in-process hook
    # even when compilation fails. No installed FFCx files are changed.
    from ffcx.codegeneration import codegeneration
    original = codegeneration.integral_generator
    changed = []
    def generate(ir, domain, options):
        declaration, implementation = original(ir, domain, options)
        implementation = transform(ir, domain, implementation)
        changed.append(ir.expression.name)
        return declaration, implementation
    codegeneration.integral_generator = generate
    try:
        yield changed
    finally:
        codegeneration.integral_generator = original


def row_loop_codegen():
    return _scoped_codegen(_row_loop)


def fused_curl_codegen():
    return _scoped_codegen(_fused_curl)


def compile_rowwise_p4(form, jit_options):
    from dolfinx import fem
    options = dict(jit_options, cffi_extra_compile_args=FLAGS)
    with row_loop_codegen() as changed:
        compiled = fem.form(form, jit_options=options)
    return compiled, {'implementation': 'native_p4_row_loop_avx512_v1',
                     'compiler_flags': list(FLAGS), 'generated_integrals': list(changed),
                     'cache_reused': not bool(changed),
                     'per_entry_summation_order': 'unchanged', 'fast_math': False}
