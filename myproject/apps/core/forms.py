from django import forms
from .models.person import Person
from .models.classification import Classification
from .models.account_transaction import AccountTransaction

class PersonForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = ['tipo', 'razao_social', 'fantasia', 'documento']
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'razao_social': forms.TextInput(attrs={'class': 'form-input'}),
            'fantasia': forms.TextInput(attrs={'class': 'form-input'}),
            'documento': forms.TextInput(attrs={'class': 'form-input'}),
        }

class ClassificationForm(forms.ModelForm):
    class Meta:
        model = Classification
        fields = ['tipo', 'descricao']
        widgets = {
            'tipo': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ex: despesa ou receita'}),
            'descricao': forms.TextInput(attrs={'class': 'form-input'}),
        }

class TransactionForm(forms.ModelForm):
    # Campos existentes
    data_emissao = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
        label="Data de Emissão"
    )
    
    quantidade_parcelas = forms.IntegerField(
        min_value=1, 
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-input'}),
        label="Qtd. Parcelas"
    )
    
    primeiro_vencimento = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
        label="Vencimento (1ª Parcela)"
    )

    fornecedor_cliente = forms.ModelChoiceField(
        queryset=Person.objects.filter(tipo='fornecedor', status='ativo'),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Fornecedor"
    )
    faturado = forms.ModelChoiceField(
        queryset=Person.objects.filter(tipo='faturado', status='ativo'),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Cliente/Faturado"
    )
    classificacoes = forms.ModelMultipleChoiceField(
        queryset=Classification.objects.filter(status='ativo'),
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'style': 'height: 100px;'}),
        required=False
    )

    class Meta:
        model = AccountTransaction
        fields = [
            'tipo', 'numero_nota_fiscal', 'data_emissao', 
            'descricao', 'valor_total', 'fornecedor_cliente', 
            'faturado', 'classificacoes'
        ]
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'numero_nota_fiscal': forms.TextInput(attrs={'class': 'form-input'}),
            'descricao': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
            'valor_total': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
        }