"""Export finance work-area adapter for the shared static/local builders."""
from core.mofe_universe import build_graph, present, mark_sector
from core.mofe_universe import validate_bundle as _validate, load_bundle as _load, report as _report
from core.export_finance_profile import PROFILE
SECTORS = PROFILE['sectors']

def validate_bundle(bundle):
    return _validate(bundle, 'export_finance')

def load_bundle(path=None):
    return _load('export_finance', path)

def report(bundle):
    return _report(bundle)
