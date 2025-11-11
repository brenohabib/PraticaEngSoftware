from django.db import models
from .account_transaction import AccountTransaction
from .classification import Classification

class AccountTransactionClassification(models.Model):
    account_transaction = models.ForeignKey(AccountTransaction, on_delete=models.CASCADE)
    classification = models.ForeignKey(Classification, on_delete=models.CASCADE)

    data_relacionamento = models.DateField(auto_now_add=True)

    class Meta:
        db_table = 'AccountTransactionClassification'
        unique_together = ('account_transaction', 'classification')

    def __str__(self):
        return f"{self.account_transaction} ↔ {self.classification}"
