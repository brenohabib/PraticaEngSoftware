from django.contrib import admin
from .classification import Classification
from .installment import Installment
from .account_transaction import AccountTransaction
from .person import Person

# Register your models here.
admin.site.register(Classification)
admin.site.register(Installment)
admin.site.register(AccountTransaction)
admin.site.register(Person)
