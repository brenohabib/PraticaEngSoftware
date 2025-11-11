from django.contrib import admin

from myproject.apps.core.models.account_transaction_classification import AccountTransactionClassification
from .models.classification import Classification
from .models.installment import Installment
from .models.account_transaction import AccountTransaction
from .models.person import Person

class PersonAdmin(admin.ModelAdmin):
    list_display = ('id', 'razao_social', 'fantasia', 'documento', 'tipo', 'status')
    list_filter = ('tipo', 'status')
    search_fields = ('razao_social', 'fantasia', 'documento')

class ClassificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'tipo', 'descricao', 'status')
    list_display_links = ('id', 'descricao')
    list_filter = ('status', 'tipo')
    search_fields = ('tipo', 'descricao')

class InstallmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'identificacao', 'account_transaction', 'data_vencimento', 
                    'valor_parcela', 'valor_pago', 'valor_saldo', 'status_parcela')
    list_display_links = ('id', 'identificacao')
    list_filter = ('status_parcela', 'data_vencimento')
    search_fields = ('identificacao', 'account_transaction__descricao')
    date_hierarchy = 'data_vencimento'

class AccountTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'tipo', 'numero_nota_fiscal', 'descricao', 
                    'fornecedor_cliente', 'valor_total', 'data_emissao', 'status')
    list_display_links = ('id', 'numero_nota_fiscal')
    list_filter = ('tipo', 'status', 'data_emissao')
    search_fields = ('numero_nota_fiscal', 'descricao', 
                     'fornecedor_cliente__razao_social', 'faturado__razao_social')
    date_hierarchy = 'data_emissao'

class AccountTransactionClassificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'account_transaction', 'classification', 'data_relacionamento')
    list_display_links = ('id', 'account_transaction', 'classification')
    list_filter = ('account_transaction__tipo', 'classification__tipo')
    search_fields = ('account_transaction__numero_nota_fiscal', 'classification__descricao')
    date_hierarchy = 'data_relacionamento'

# Registrar os models com suas classes Admin
admin.site.register(Person, PersonAdmin)
admin.site.register(Classification, ClassificationAdmin)
admin.site.register(Installment, InstallmentAdmin)
admin.site.register(AccountTransaction, AccountTransactionAdmin)
admin.site.register(AccountTransactionClassification, AccountTransactionClassificationAdmin)