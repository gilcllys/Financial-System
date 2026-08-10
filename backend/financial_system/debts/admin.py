from django.contrib import admin

from debts.models import (
    SharedDebt,
    SharedDebtInvite,
    SharedDebtMember,
    SharedEntry,
    SharedEntryParticipant,
)

admin.site.register(SharedDebt)
admin.site.register(SharedDebtMember)
admin.site.register(SharedEntry)
admin.site.register(SharedEntryParticipant)
admin.site.register(SharedDebtInvite)
