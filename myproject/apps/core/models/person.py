from django.db import models
from django.core.exceptions import ValidationError

class Person(models.Model):
    STATUS_CHOICES = [
        ('ativo', 'Ativo'),
        ('inativo', 'Inativo'),
    ]
    TIPO_CHOICES = [
        ('fornecedor', 'Fornecedor'),
        ('faturado', 'Faturado'),
    ]
    tipo = models.CharField(max_length=45, choices=TIPO_CHOICES)
    razao_social = models.CharField(max_length=150)
    fantasia = models.CharField(max_length=150, blank=True, null=True)
    documento = models.CharField(max_length=45, unique=True)
    status = models.CharField(max_length=45, default='ativo', choices=STATUS_CHOICES)
    
    def __str__(self):
        return self.razao_social
    
    def desactivate(self):
        """Desactivate the person"""
        self.status = 'inativo'
        self.save()
    
    def activate(self):
        """Activate the person"""
        self.status = 'ativo'
        self.save()

    def delete(self, using=None, keep_parents=False):
        self.desactivate()
    
    class Meta:
        verbose_name = "Person"
        verbose_name_plural = "People"