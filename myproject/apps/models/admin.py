from django.contrib import admin
from django.contrib import messages
from .entities.classification import Classification
from .entities.installment import Installment
from .entities.account_transaction import AccountTransaction
from .entities.person import Person

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
    filter_horizontal = ('classificacoes',)  # Interface melhor para ManyToMany

# Registrar os models com suas classes Admin
admin.site.register(Person, PersonAdmin)
admin.site.register(Classification, ClassificationAdmin)
admin.site.register(Installment, InstallmentAdmin)
admin.site.register(AccountTransaction, AccountTransactionAdmin)