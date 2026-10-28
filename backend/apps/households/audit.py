from auditlog.registry import auditlog

from apps.accounts.models import User
from apps.households.models import Household, Membership

auditlog.register(User)
auditlog.register(Household)
auditlog.register(Membership)
