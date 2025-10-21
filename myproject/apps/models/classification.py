from django.db import models

class Classification(models.Model):
    STATUS_CHOICES = [
        ('ativo', 'Ativo'),
        ('inativo', 'Inativo'),
    ]

    tipo = models.CharField(max_length=45)
    descricao = models.CharField(max_length=150)
    status = models.CharField(max_length=45, default='ativo', choices=STATUS_CHOICES)

    def __str__(self):
        return f"{self.tipo} - {self.descricao}"

    def desactivate(self):
        self.status = 'inativo'
        self.save()

    def activate(self):
        self.status = 'ativo'
        self.save()

    def delete(self, using=None, keep_parents=False):
        self.desactivate()

    class Meta:
        verbose_name = "Classification"
        verbose_name_plural = "Classifications"