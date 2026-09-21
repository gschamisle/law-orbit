"""Customs profile of the shared MOFE engine."""
from core import mofe_universe as engine
from core.mofe_profiles import PROFILES
from core.mofe_universe import present,report,mark_sector
DOMAIN='customs'
BUNDLE=engine.path(DOMAIN)
SECTORS=PROFILES[DOMAIN]['sectors']
def load_bundle(path=BUNDLE):return engine.load_bundle(DOMAIN,path)
def validate_bundle(bundle):return engine.validate_bundle(bundle,DOMAIN)
