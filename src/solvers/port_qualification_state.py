"""Explicit role gate; readable negative evidence is never a solve permit."""


def qualification_state(*, shared, role, output, files_present, identity_matches):
    values = (shared, role, output, files_present, identity_matches)
    if any(type(x) is not bool for x in values):
        raise ValueError("QUALIFICATION_STATE_BOOLEAN_FIELDS_REQUIRED")
    return dict(
        component_passed=shared and role,
        negative_field_readable=files_present and identity_matches,
        strict_complete_qualified=all(values),
        solve_admitted=all(values),
    )
