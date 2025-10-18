from django.db import models

class Classification(models.Model):
    tipo = models.CharField(max_length=45)
    descricao = models.CharField(max_length=150)
    status = models.CharField(max_length=45, default='ativo')

    def __str__(self):
        return f"{self.tipo} - {self.descricao}"

    class Meta:
        verbose_name = "Classification"
        verbose_name_plural = "Classifications"