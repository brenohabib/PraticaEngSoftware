from django.db import models
from .person import Person
from .classification import Classification

class AccountTransaction(models.Model):
    tipo = models.CharField(max_length=45)
    numero_nota_fiscal = models.CharField(max_length=45, null=True)
    data_emissao = models.DateField()
    descricao = models.CharField(max_length=300)
    status = models.CharField(max_length=45)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2)

    fornecedor_cliente = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name='movimentos'
    )

    faturado = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name='movimentos_faturados'
    )
    
    classificacoes = models.ManyToManyField(Classification)

    def __str__(self):
        return f"#{self.id} - {self.descricao} - {self.valor_total}"

    class Meta:
        verbose_name = "Account Transaction"
        verbose_name_plural = "Account Transactions"