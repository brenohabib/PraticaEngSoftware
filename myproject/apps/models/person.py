from django.db import models

class Person(models.Model):
    tipo = models.CharField(max_length=45, null=True)
    razao_social = models.CharField(max_length=150)
    fantasia = models.CharField(max_length=150, blank=True, null=True)
    documento = models.CharField(max_length=45, unique=True) # CPF ou CNPJ
    status = models.CharField(max_length=45, default='ativo')

    def __str__(self):
        return self.razao_social

    class Meta:
        verbose_name = "Person"
        verbose_name_plural = "People"