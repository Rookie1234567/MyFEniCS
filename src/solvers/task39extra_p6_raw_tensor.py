"""Profile-locked p6 raw tensor builder for task39extra."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from time import perf_counter
from typing import Any

import numpy as np


@dataclass(frozen=True)
class _IntegralRule:
    points: np.ndarray
    weights: np.ndarray
    degree: int
    rule: str
    sha256: str


def _subdomain_tags(subdomain_id: Any, aliases: dict[Any, int]) -> set[int | str]:
    if subdomain_id == "everywhere" or subdomain_id == "otherwise":
        if "otherwise" in aliases:
            return {int(aliases["otherwise"])}
        return {"otherwise"}
    if isinstance(subdomain_id, (tuple, list, set)):
        tags: set[int | str] = set()
        for item in subdomain_id:
            tags.update(_subdomain_tags(item, aliases))
        return tags
    if isinstance(subdomain_id, (int, np.integer)):
        return {int(subdomain_id)}
    raise NotImplementedError(f"unsupported p6 cell subdomain {subdomain_id!r}")


def _components(integrand: Any) -> set[str]:
    """Classify only the frozen curl-curl plus vector-mass UFL expression."""

    import ufl
    from ufl.corealg.traversal import unique_pre_traversal

    if isinstance(integrand, ufl.classes.Sum):
        result: set[str] = set()
        for operand in integrand.ufl_operands:
            result.update(_components(operand))
        return result
    has_curl = any(
        type(node).__name__ == "Curl"
        for node in unique_pre_traversal(integrand)
    )
    return {"curl" if has_curl else "mass"}


def _is_default_subdomain(subdomain_id: Any) -> bool:
    return subdomain_id == "everywhere" or subdomain_id == "otherwise"


def _is_literal_ufl_zero(integrand: Any) -> bool:
    import ufl

    return isinstance(integrand, ufl.classes.Zero)


def _analyze_original_form(
    form: Any,
    *,
    tag_aliases: dict[Any, int] | None = None,
) -> tuple[dict[tuple[int, str], _IntegralRule], dict[str, Any]]:
    """Read actual integral rules from FFCx analysis of the full bilinear form."""

    from ffcx.analysis import analyze_ufl_objects
    from ffcx.ir.representationutils import create_quadrature_points_and_weights

    import ufl

    aliases = {} if tag_aliases is None else dict(tag_aliases)
    analysis = analyze_ufl_objects([form], np.dtype(np.complex128))
    form_data = analysis.form_data[0]
    source_components_by_tag: dict[int, dict[str, list[tuple[int | None, str | None]]]] = {}
    source_counts_by_tag: dict[str, dict[str, int]] = {}
    source_integral_ids: list[dict[str, Any]] = []
    literal_zero_default_integral_count = 0
    for source_integral in form.integrals():
        if str(source_integral.integral_type()) != "cell":
            raise NotImplementedError("task39extra p6 raw candidate accepts cell integrals only")
        subdomain_id = source_integral.subdomain_id()
        integrand = source_integral.integrand()
        is_default = _is_default_subdomain(subdomain_id)
        literal_zero_default = is_default and _is_literal_ufl_zero(integrand)
        if _is_literal_ufl_zero(integrand) and not is_default:
            raise NotImplementedError(
                "literal-zero tagged integrals are not part of the p6 candidate contract"
            )
        if is_default and not literal_zero_default and "otherwise" not in aliases:
            raise NotImplementedError(
                "nonzero default cell integral has no qualified material-tag mapping"
            )
        if literal_zero_default:
            # Preserve proof of this source term without aliasing it to a
            # material tag; only a literal UFL Zero may be omitted.
            literal_zero_default_integral_count += 1
            tags: set[int | str] = {"otherwise"}
            components: set[str] = set()
        else:
            tags = _subdomain_tags(subdomain_id, aliases)
            components = _components(integrand)
        metadata = source_integral.metadata() or {}
        source_degree = (
            int(metadata["quadrature_degree"])
            if "quadrature_degree" in metadata
            else None
        )
        source_rule = (
            str(metadata["quadrature_rule"])
            if "quadrature_rule" in metadata
            else None
        )
        source_integral_ids.append(
            {
                "subdomain_tags": sorted(tags),
                "components": sorted(components),
                "literal_zero": bool(literal_zero_default),
                "source_quadrature_degree": source_degree,
                "source_quadrature_rule": source_rule,
            }
        )
        for tag in tags:
            per_tag = source_components_by_tag.setdefault(
                tag, {"curl": [], "mass": []}
            )
            counts = source_counts_by_tag.setdefault(
                str(tag), {"curl": 0, "mass": 0}
            )
            for component in components:
                per_tag[component].append((source_degree, source_rule))
                counts[component] += 1

    cell = form.ufl_domains()[0].ufl_cell()
    rules: dict[tuple[int, str], _IntegralRule] = {}
    observed_pairs: dict[tuple[int, str], set[tuple[int, str]]] = {}
    rule_records: list[dict[str, Any]] = []
    analyzed_group_counts: list[dict[str, Any]] = []
    for group in form_data.integral_data:
        integral_type = getattr(group.integral_type, "name", group.integral_type)
        integral_type = str(integral_type)
        if integral_type != "cell":
            raise NotImplementedError(
                "task39extra p6 raw candidate accepts cell integrals only"
            )
        group_tags = _subdomain_tags(group.subdomain_id, aliases)
        analyzed_group_counts.append(
            {"subdomain_tags": sorted(group_tags), "integral_count": len(group.integrals)}
        )
        if any(not isinstance(tag, int) for tag in group_tags):
            raise NotImplementedError(
                "analyzed full form still contains an untagged cell integral"
            )
        for analyzed_integral in group.integrals:
            metadata = analyzed_integral.metadata()
            degree = int(metadata["quadrature_degree"])
            quadrature_rule = str(metadata["quadrature_rule"])
            if quadrature_rule == "custom":
                raise NotImplementedError("custom FFCx quadrature is not qualified")
            point_tables, weight_tables, _ = create_quadrature_points_and_weights(
                "cell",
                cell,
                degree,
                quadrature_rule,
                form_data.argument_elements,
                False,
            )
            cell_name = cell.cellname()
            points = np.ascontiguousarray(point_tables[cell_name], dtype=np.float64)
            weights = np.ascontiguousarray(weight_tables[cell_name], dtype=np.float64)
            if points.ndim != 2 or points.shape[1] != 3 or weights.shape != (len(points),):
                raise ValueError("FFCx analysis returned an invalid hexahedron rule")
            digest_builder = hashlib.sha256()
            digest_builder.update(memoryview(points).cast("B"))
            digest_builder.update(memoryview(weights).cast("B"))
            digest = digest_builder.hexdigest()
            rule = _IntegralRule(points, weights, degree, quadrature_rule, digest)
            actual_pair = (degree, quadrature_rule)
            analyzed_tags = _subdomain_tags(analyzed_integral.subdomain_id(), aliases)
            if analyzed_tags != group_tags:
                raise NotImplementedError(
                    "FFCx integral tag coverage differs inside one analyzed group"
                )
            mapped_components: set[str] = set()
            for tag in analyzed_tags:
                if tag not in source_components_by_tag:
                    raise NotImplementedError(
                        f"FFCx integral tag {tag} has no original bilinear terms"
                    )
                for component, source_rules in source_components_by_tag[tag].items():
                    if any(
                        expected_degree is None
                        or (expected_degree, expected_rule) == actual_pair
                        for expected_degree, expected_rule in source_rules
                    ):
                        mapped_components.add(component)
                        key = (tag, component)
                        prior = rules.get(key)
                        if prior is not None and (
                            prior.degree != rule.degree
                            or prior.rule != rule.rule
                            or not np.array_equal(prior.points, rule.points)
                            or not np.array_equal(prior.weights, rule.weights)
                        ):
                            raise NotImplementedError(
                                f"p6 {component} rules vary within tag {tag}"
                            )
                        rules[key] = rule
                        observed_pairs.setdefault(key, set()).add(actual_pair)
            if not mapped_components:
                raise NotImplementedError(
                    "FFCx analyzed rule is not bound to a source curl/mass integral"
                )
            rule_records.append(
                {
                    "tags": sorted(analyzed_tags),
                    "components": sorted(mapped_components),
                    "degree": degree,
                    "rule": quadrature_rule,
                    "point_count": int(len(points)),
                    "points_weights_sha256": digest,
                }
            )

    for tag, component_rules in source_components_by_tag.items():
        # An untagged/default term is skipped only after its integrand was
        # proved to be a literal UFL Zero above. Nonzero defaults are not
        # silently dropped: they require an explicit alias and the compiled
        # kernel inventory is still checked by __call__.
        if not isinstance(tag, int):
            continue
        for component in ("curl", "mass"):
            source_rules = component_rules[component]
            if len(source_rules) != 1:
                raise NotImplementedError(
                    f"tag {tag} has duplicate or missing original {component} integrals"
                )
            key = (tag, component)
            if key not in rules or len(observed_pairs.get(key, ())) != 1:
                raise NotImplementedError(
                    f"FFCx full-form analysis did not bind one rule to tag {tag} {component}"
                )
            expected_degree, expected_rule = source_rules[0]
            if expected_degree is not None and observed_pairs[key] != {
                (expected_degree, expected_rule)
            }:
                raise NotImplementedError(
                    f"FFCx full-form rule disagrees with source metadata for tag {tag} {component}"
                )

    return rules, {
        "full_form_signature": str(form.signature()),
        "integral_rule_records": rule_records,
        "integral_counts_by_tag": source_counts_by_tag,
        "source_integrals": source_integral_ids,
        "literal_zero_default_integral_count": literal_zero_default_integral_count,
        "analyzed_cell_integral_groups": analyzed_group_counts,
    }


class Task39ExtraP6RawTensorCandidate:
    """Blocked exact-integration builder bound to one analyzed full p6 form."""

    identity = "task39extra_p6_isotropic_blocked_gram_ffcx_rules_v1"
    point_block_size = 32

    def __init__(
        self,
        basix_element: Any,
        cfg: Any,
        full_bilinear_form: Any,
        *,
        compiled_form: Any | None = None,
        tag_aliases: dict[Any, int] | None = None,
        require_all_material_tags: bool = True,
    ) -> None:
        if bool(getattr(cfg, "use_pml", True)):
            raise NotImplementedError("p6 raw candidate does not support PML tensors")
        if float(getattr(cfg, "divergence_penalty", -1.0)) != 0.0:
            raise NotImplementedError("p6 raw candidate requires zero divergence penalty")
        self.element = basix_element
        self.dimension = int(basix_element.dim)
        if self.dimension != 882:
            raise NotImplementedError(
                f"p6 raw candidate requires the frozen 882-DoF cell, got {self.dimension}"
            )
        inv_mu = complex(1.0 / cfg.mu_r)
        k0_squared = float(cfg.k0) ** 2
        self.coefficients_by_tag = {
            int(cfg.tags.air): (inv_mu, complex(-k0_squared * cfg.eps_r)),
            int(cfg.tags.substrate): (
                inv_mu,
                complex(-k0_squared * cfg.substrate_index**2),
            ),
            int(cfg.tags.grating): (
                inv_mu,
                complex(-k0_squared * cfg.grating_index**2),
            ),
        }
        if len(self.coefficients_by_tag) != 3:
            raise ValueError("task39extra material tags must be distinct")

        self.rules_by_tag_component, analysis_facts = _analyze_original_form(
            full_bilinear_form, tag_aliases=tag_aliases
        )
        self.expected_ufcx_signature = None
        self.ffcx_default_kernel_absent = None
        if compiled_form is not None:
            if np.dtype(compiled_form.dtype) != np.dtype(np.complex128):
                raise NotImplementedError("p6 raw candidate requires complex128")
            self.expected_ufcx_signature = compiled_form.module.ffi.string(
                compiled_form.ufcx_form.signature
            ).decode("ascii")

        tags_in_form = {tag for tag, _component in self.rules_by_tag_component}
        if require_all_material_tags and tags_in_form != set(self.coefficients_by_tag):
            raise NotImplementedError(
                "the analyzed p6 bilinear form tag set differs from task39extra materials"
            )
        for tag in tags_in_form:
            if tag not in self.coefficients_by_tag:
                raise NotImplementedError(f"unsupported task39extra material tag {tag}")
            counts = analysis_facts["integral_counts_by_tag"].get(str(tag), {})
            if counts != {"curl": 1, "mass": 1}:
                raise NotImplementedError(
                    f"p6 tag {tag} has duplicate or missing curl/mass integrals: {counts}"
                )
        if require_all_material_tags and any(
            (tag, component) not in self.rules_by_tag_component
            for tag in self.coefficients_by_tag
            for component in ("curl", "mass")
        ):
            raise NotImplementedError("the analyzed p6 form lacks a required component rule")

        self.analysis_facts = analysis_facts
        self.class_seconds: dict[str, float] = {}
        self.class_count = 0
        n = self.dimension
        block = self.point_block_size
        # Bound simultaneous derivative/value/curl/flattened/weighted arrays,
        # one Gram product, the complex result, and its coefficient temporary.
        self.workspace_bytes_upper = int(
            14 * block * n * 3 * np.dtype(np.float64).itemsize
            + 40 * n * n
        )

    def _affine_jacobian(self, coordinates: np.ndarray) -> tuple[np.ndarray, float]:
        import basix

        vertices = np.asarray(coordinates, dtype=np.float64).reshape((8, 3))
        reference = np.asarray(
            basix.geometry(basix.CellType.hexahedron), dtype=np.float64
        )
        origin_index = int(np.flatnonzero(np.all(reference == 0.0, axis=1))[0])
        origin = vertices[origin_index]
        jacobian = np.empty((3, 3), dtype=np.float64)
        for axis in range(3):
            unit_vertex = np.zeros(3, dtype=np.float64)
            unit_vertex[axis] = 1.0
            matches = np.flatnonzero(np.all(reference == unit_vertex, axis=1))
            if matches.size != 1:
                raise NotImplementedError("unsupported hexahedron reference vertex ordering")
            jacobian[:, axis] = vertices[int(matches[0])] - origin
        scale = max(float(np.max(np.abs(vertices))), 1.0)
        if not np.allclose(origin + reference @ jacobian.T, vertices, rtol=0.0, atol=1e-11 * scale):
            raise NotImplementedError("p6 raw candidate requires affine hexahedra")
        nonzero_by_column = np.count_nonzero(np.abs(jacobian) > 1e-12 * scale, axis=0)
        nonzero_by_row = np.count_nonzero(np.abs(jacobian) > 1e-12 * scale, axis=1)
        if not np.all(nonzero_by_column == 1) or not np.all(nonzero_by_row == 1):
            raise NotImplementedError("p6 raw candidate requires axis-aligned hexahedra")
        determinant = float(np.linalg.det(jacobian))
        if not np.isfinite(determinant) or abs(determinant) <= np.finfo(float).tiny:
            raise ValueError("p6 raw candidate received a singular cell Jacobian")
        return jacobian, determinant

    @staticmethod
    def _flat_and_weights(table: np.ndarray, weights: np.ndarray, dimension: int):
        flat = np.ascontiguousarray(table.transpose(0, 2, 1)).reshape((-1, dimension))
        repeated_weights = np.repeat(weights, 3)
        return flat, repeated_weights

    @staticmethod
    def _add_gram(
        result: np.ndarray,
        table: np.ndarray,
        weights: np.ndarray,
        coefficient: complex,
        dimension: int,
    ) -> None:
        flat, repeated_weights = Task39ExtraP6RawTensorCandidate._flat_and_weights(
            table, weights, dimension
        )
        weighted = flat * repeated_weights[:, None]
        gram = flat.conjugate().T @ weighted
        result += coefficient * gram

    def _add_component(
        self,
        result: np.ndarray,
        tag: int,
        component: str,
        coefficient: complex,
        jacobian: np.ndarray,
        determinant: float,
    ) -> None:
        import basix

        rule = self.rules_by_tag_component[(tag, component)]
        d_x, d_y, d_z = (
            basix.index(1, 0, 0),
            basix.index(0, 1, 0),
            basix.index(0, 0, 1),
        )
        for start in range(0, len(rule.points), self.point_block_size):
            stop = min(start + self.point_block_size, len(rule.points))
            table = self.element.tabulate(1, rule.points[start:stop])
            if component == "mass":
                physical = np.einsum(
                    "qaj,ji->qai",
                    table[0],
                    np.linalg.inv(jacobian),
                    optimize=True,
                )
            else:
                curl_ref = np.empty_like(table[0])
                np.subtract(table[d_y, :, :, 2], table[d_z, :, :, 1], out=curl_ref[:, :, 0])
                np.subtract(table[d_z, :, :, 0], table[d_x, :, :, 2], out=curl_ref[:, :, 1])
                np.subtract(table[d_x, :, :, 1], table[d_y, :, :, 0], out=curl_ref[:, :, 2])
                physical = np.einsum(
                    "qaj,ij->qai",
                    curl_ref,
                    jacobian / determinant,
                    optimize=True,
                )
                del curl_ref
            flat, repeated_weights = self._flat_and_weights(
                physical, rule.weights[start:stop] * abs(determinant), self.dimension
            )
            weighted = flat * repeated_weights[:, None]
            gram = flat.conjugate().T @ weighted
            result += coefficient * gram
            del table, physical, flat, repeated_weights, weighted, gram

    def build(self, coordinates: np.ndarray, *, tag: int, dimension: int) -> np.ndarray:
        if int(dimension) != self.dimension:
            raise NotImplementedError("compiled p6 dimension does not match candidate")
        tag = int(tag)
        if tag not in self.coefficients_by_tag:
            raise NotImplementedError(f"unsupported task39extra material tag {tag}")
        curl_rule = self.rules_by_tag_component.get((tag, "curl"))
        mass_rule = self.rules_by_tag_component.get((tag, "mass"))
        if curl_rule is None or mass_rule is None:
            raise NotImplementedError(f"tag {tag} has no complete curl/mass rule")
        jacobian, determinant = self._affine_jacobian(coordinates)
        curl_coefficient, mass_coefficient = self.coefficients_by_tag[tag]
        result = np.zeros((self.dimension, self.dimension), dtype=np.complex128)
        started = perf_counter()
        shared_rule = (
            curl_rule.degree == mass_rule.degree
            and curl_rule.rule == mass_rule.rule
            and np.array_equal(curl_rule.points, mass_rule.points)
            and np.array_equal(curl_rule.weights, mass_rule.weights)
        )
        if shared_rule:
            # One basis tabulation and two weighted Gram products per block.
            import basix

            d_x, d_y, d_z = (
                basix.index(1, 0, 0),
                basix.index(0, 1, 0),
                basix.index(0, 0, 1),
            )
            points, weights = curl_rule.points, curl_rule.weights
            for start in range(0, len(points), self.point_block_size):
                stop = min(start + self.point_block_size, len(points))
                table = self.element.tabulate(1, points[start:stop])
                values_ref = table[0]
                curls_ref = np.empty_like(values_ref)
                np.subtract(table[d_y, :, :, 2], table[d_z, :, :, 1], out=curls_ref[:, :, 0])
                np.subtract(table[d_z, :, :, 0], table[d_x, :, :, 2], out=curls_ref[:, :, 1])
                np.subtract(table[d_x, :, :, 1], table[d_y, :, :, 0], out=curls_ref[:, :, 2])
                values = np.einsum(
                    "qaj,ji->qai", values_ref, np.linalg.inv(jacobian), optimize=True
                )
                curls = np.einsum(
                    "qaj,ij->qai", curls_ref, jacobian / determinant, optimize=True
                )
                physical_weights = weights[start:stop] * abs(determinant)
                self._add_gram(
                    result,
                    curls,
                    physical_weights,
                    curl_coefficient,
                    self.dimension,
                )
                flat_values, repeated_weights = self._flat_and_weights(
                    values, physical_weights, self.dimension
                )
                weighted_values = flat_values * repeated_weights[:, None]
                gram_values = flat_values.conjugate().T @ weighted_values
                result += mass_coefficient * gram_values
                del (
                    table,
                    values_ref,
                    curls_ref,
                    values,
                    curls,
                    flat_values,
                    repeated_weights,
                    weighted_values,
                    gram_values,
                )
        else:
            # Distinct original rules are integrated separately, without
            # changing either component's points, weights, or material term.
            self._add_component(
                result, tag, "curl", curl_coefficient, jacobian, determinant
            )
            self._add_component(
                result, tag, "mass", mass_coefficient, jacobian, determinant
            )
        key = (
            f"tag={tag},widths="
            f"{tuple(float(x) for x in np.ptp(coordinates.reshape(8, 3), axis=0))}"
        )
        self.class_seconds[key] = float(perf_counter() - started)
        self.class_count += 1
        return result

    def validate_compiled_form(
        self, compiled_form: Any, kernels: dict[int, Any]
    ) -> None:
        if np.dtype(compiled_form.dtype) != np.dtype(np.complex128):
            raise NotImplementedError("p6 raw candidate requires complex128")
        if self.expected_ufcx_signature is None:
            raise NotImplementedError("candidate has no compiled-form identity binding")
        signature = compiled_form.module.ffi.string(
            compiled_form.ufcx_form.signature
        ).decode("ascii")
        if signature != self.expected_ufcx_signature:
            raise NotImplementedError("candidate was bound to another FFCx form")
        expected_tags = set(self.coefficients_by_tag)
        if -1 in kernels or set(map(int, kernels)) != expected_tags:
            raise NotImplementedError("FFCx cell integral IDs differ from analyzed p6 tags")
        if any(len(kernels[tag]) != 1 for tag in expected_tags):
            raise NotImplementedError("duplicate FFCx cell kernels are not qualified")
        self.ffcx_default_kernel_absent = -1 not in kernels

    def __call__(
        self,
        compiled_form: Any,
        kernels: dict[int, Any],
        coordinates: np.ndarray,
        *,
        tag: int,
        dimension: int,
    ) -> np.ndarray:
        self.validate_compiled_form(compiled_form, kernels)
        return self.build(coordinates, tag=tag, dimension=dimension)

    def audit(self) -> dict[str, Any]:
        return {
            "implementation": self.identity,
            "quadrature_source": "FFCx analysis of the exact full p6 bilinear form",
            "full_form_signature": self.analysis_facts["full_form_signature"],
            "integral_rule_records": list(self.analysis_facts["integral_rule_records"]),
            "integral_counts_by_tag": dict(self.analysis_facts["integral_counts_by_tag"]),
            "literal_zero_default_integral_count": int(
                self.analysis_facts["literal_zero_default_integral_count"]
            ),
            "ffcx_default_kernel_absent": self.ffcx_default_kernel_absent,
            "material_coefficients_by_tag": {
                str(tag): [[float(x.real), float(x.imag)] for x in pair]
                for tag, pair in self.coefficients_by_tag.items()
            },
            "point_block_size": self.point_block_size,
            "workspace_bytes_upper": self.workspace_bytes_upper,
            "class_count": self.class_count,
            "class_seconds": dict(self.class_seconds),
            "mass_coefficient_conjugated": False,
            "hermitian_assumption": False,
            "full_matrix_built_before_schur": True,
        }
