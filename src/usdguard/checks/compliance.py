"""Compliance with OpenUSD's own validators."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pxr import UsdValidation

from usdguard.checks import _options
from usdguard.core import Issue, Severity, StageCheck

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from usdguard.core import Context

# usdchecker only runs this validator with --rootPackageOnly; mirror its
# default behaviour by leaving it out.
_ROOT_PACKAGE_VALIDATOR = "usdUtilsValidators:RootPackageValidator"

_ERROR_TYPES = UsdValidation.ValidationErrorType


class UsdCheckerCheck(StageCheck):
    """OpenUSD's built-in validators must pass, as with ``usdchecker``.

    OpenUSD ships validators for its own schemas: gprim and material
    encapsulation, material binding rules, geometry subsets, skinning,
    physics, lights, package layout and composition errors. This check
    runs them through the ``UsdValidation`` framework, which powers
    ``usdchecker``, instead of reimplementing them, so new validators
    come for free with new USD releases. (``UsdUtils.ComplianceChecker``,
    the older implementation, was removed from usd-core 26.8.)

    Validator errors are reported with the check's severity, warnings
    as WARNING and informational results as INFO; each message starts
    with the validator error identifier. Validation needs a stage
    opened from a file: in-memory stages get a single informational
    issue and are skipped. Only the current variant selections are
    validated.

    Options:
        keywords: Only run validators tagged with one of these keywords,
            such as ``UsdGeomValidators`` or ``UsdShadeValidators``.
            Empty runs every registered validator, like ``usdchecker``.
        exclude: Names of validators to skip, for instance
            ``usdGeomValidators:StageMetadataChecker`` when
            ``stage.metadata`` already covers it.

    Example:
        ``usdGeomValidators:EncapsulationChecker`` reports the nested
        gprim::

            def Mesh "outer"
            {
                def Mesh "inner" {}
            }
    """

    check_id = "compliance.usdchecker"
    description = "OpenUSD's built-in validators pass, as with usdchecker."

    def __init__(
        self, *, keywords: Sequence[str] = (), exclude: Sequence[str] = ()
    ) -> None:
        registry = UsdValidation.ValidationRegistry()
        self.keywords = _options.string_list("keywords", keywords)
        self.exclude = _options.string_list("exclude", exclude)
        known = {str(meta.name) for meta in registry.GetAllValidatorMetadata()}
        unknown = sorted(set(self.exclude) - known)
        if unknown:
            msg = f"exclude names unknown validators: {', '.join(unknown)}"
            raise ValueError(msg)
        self.validator_names = self._select(registry)
        if self.keywords and not self.validator_names:
            msg = f"no validator matches keywords {', '.join(self.keywords)}"
            raise ValueError(msg)

    def _select(self, registry: Any) -> list[str]:
        if self.keywords:
            metadata = registry.GetValidatorMetadataForKeywords(
                list(self.keywords)
            )
        else:
            metadata = registry.GetAllValidatorMetadata()
        skipped = {*self.exclude, _ROOT_PACKAGE_VALIDATOR}
        return sorted(
            {str(meta.name) for meta in metadata if not meta.isSuite} - skipped
        )

    def check_stage(self, context: Context) -> Iterator[Issue]:
        """Validate the stage and report every validator error."""
        if context.stage.GetRootLayer().anonymous:
            yield self.issue(
                "Root layer is anonymous (in-memory stage); usdchecker "
                "validation was skipped",
                severity=Severity.INFO,
            )
            return
        registry = UsdValidation.ValidationRegistry()
        validators = registry.GetOrLoadValidatorsByName(self.validator_names)
        errors = UsdValidation.ValidationContext(validators).Validate(
            context.stage
        )
        for error in errors:
            yield from self._issues(error)

    def _issues(self, error: Any) -> Iterator[Issue]:
        """Yield the issue for a validation error, if it is one."""
        error_type = error.GetType()
        if error.HasNoError() or error_type == _ERROR_TYPES.None_:
            return
        severity = {
            _ERROR_TYPES.Warn: Severity.WARNING,
            _ERROR_TYPES.Info: Severity.INFO,
        }.get(error_type, self.severity)
        prim_path, layer = _site_location(error.GetSites())
        yield Issue(
            check_id=self.check_id,
            severity=severity,
            message=f"{error.GetIdentifier()}: {error.GetMessage()}",
            prim_path=prim_path,
            layer=layer,
        )


def _site_location(sites: Any) -> tuple[str, str]:
    """Return the prim path and layer identifier of the first sites."""
    prim_path = ""
    layer = ""
    for site in sites:
        if not prim_path and site.IsPrim():
            prim_path = str(site.GetPrim().GetPath())
        elif not prim_path and site.IsProperty():
            prim_path = str(site.GetProperty().GetPrimPath())
        site_layer = site.GetLayer()
        if not layer and site_layer and not site_layer.anonymous:
            layer = str(site_layer.identifier)
    return prim_path, layer
