"""Isolated work area over the shared explicit-citation engine."""
from core import mofe_universe as engine
from core.prices_profile import PROFILE
from core.mofe_universe import present,report,mark_sector
from core.ftc_universe import overview_graph
DOMAIN='prices'
BUNDLE=engine.path(DOMAIN)
SECTORS=PROFILE['sectors']
def load_bundle(path=BUNDLE):return engine.load_bundle(DOMAIN,path)
def validate_bundle(bundle):return engine.validate_bundle(bundle,DOMAIN)
