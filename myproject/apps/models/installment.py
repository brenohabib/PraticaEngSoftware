from django.db import models
from .account_transaction import AccountTransaction

class Installment(models.Model):
    account_transaction = models.ForeignKey(
        AccountTransaction,
        on_delete=models.CASCADE,
        related_name='parcelas'
    )

    identificacao = models.CharField(max_length=45)
    data_vencimento = models.DateField()
    valor_parcela = models.DecimalField(max_digits=10, decimal_places=2)
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    valor_saldo = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    status_parcela = models.CharField(max_length=45, default='aberta')

    def __str__(self):
        return f"Parcela {self.identificacao} de {self.account_transaction.descricao}"

    class Meta:
        verbose_name = "Installment"
        verbose_name_plural = "Installments"
