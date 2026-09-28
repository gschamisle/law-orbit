"""Medical profile of the shared engine; separately validated annex bodies."""
from core import mofe_universe as engine
from core.medical_profile import PROFILE
from core.mofe_universe import present,report,mark_sector
DOMAIN='medical'
BUNDLE=engine.path(DOMAIN)
SECTORS=PROFILE['sectors']
def load_bundle(path=BUNDLE):return engine.load_bundle(DOMAIN,path)
def validate_bundle(bundle):return engine.validate_bundle(bundle,DOMAIN)
