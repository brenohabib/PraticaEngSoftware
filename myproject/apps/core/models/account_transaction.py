from django.db import models
from .person import Person
from .classification import Classification
from pgvector.django import VectorField, HnswIndex

class AccountTransaction(models.Model):
    TIPO_CHOICES = [
        ('a pagar', 'A Pagar'),
        ('a receber', 'A Receber'),
    ]

    STATUS_CHOICES = [
        ('ativo', 'Ativo'),
        ('inativo', 'Inativo'),
    ]

    descricao_embedding = VectorField(
        dimensions=768,
        null=True,
    )

    tipo = models.CharField(max_length=45, default = 'a pagar', choices=TIPO_CHOICES)
    numero_nota_fiscal = models.CharField(max_length=45, unique=True)
    data_emissao = models.DateField()
    descricao = models.CharField(max_length=300)
    status = models.CharField(max_length=45, default='ativo', choices=STATUS_CHOICES)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2)
    fornecedor_cliente = models.ForeignKey(
        Person, on_delete=models.PROTECT, 
        related_name='movimentos'
    )
    faturado = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name='movimentos_faturados'
    )

    classificacoes = models.ManyToManyField(
        Classification,
        through='AccountTransactionClassification',
        related_name='account_transactions',
    )

    def __str__(self):
        return f"#{self.id} - {self.descricao} - {self.valor_total}"

    def desactivate(self):
        self.status = 'inativo'
        self.save()

    def activate(self):
        self.status = 'ativo'
        self.save()

    def delete(self, using=None, keep_parents=False):
        self.desactivate()

    class Meta:
        verbose_name = "Account Transaction"
        verbose_name_plural = "Account Transactions"

        indexes = [
            HnswIndex(
                name='idx_desc_embedding_hnsw',
                fields=['descricao_embedding'],
                m=16,
                ef_construction=64,
                opclasses=['vector_l2_ops']
            )
        ]