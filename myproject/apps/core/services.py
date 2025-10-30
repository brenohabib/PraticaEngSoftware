from datetime import datetime, timedelta
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from .models.classification import Classification
from .models.account_transaction import AccountTransaction
from .models.installment import Installment
from .models.person import Person

def parse_date(date_str):
    """Converte string DD/MM/AAAA para date object"""
    if not date_str or date_str == 'null':
        return None
    try:
        return datetime.strptime(str(date_str), '%d/%m/%Y').date()
    except ValueError as e:
        print(f"Erro ao converter data '{date_str}': {e}")
        return None

def normalize_document(document):
    """Remove formatação de CPF/CNPJ (pontos, traços, barras)"""
    if not document:
        return ''
    return ''.join(filter(str.isdigit, str(document)))

def safe_strip(value):
    """Retorna string vazia se valor for None, caso contrário faz strip"""
    if value is None or value == 'null':
        return ''
    return str(value).strip()

def process_extracted_invoice(data: dict):
    """
      - Verifica se fornecedor, faturado e classificações existem
      - Cria novos cadastros se necessário
      - Cria o movimento e as parcelas
      - Retorna relatório de verificações e sucesso ou falha
    """
    mensagens = []
    try:
        # Verify provider
        provider_data = data.get('fornecedor', {})
        provider_doc = normalize_document(provider_data.get('cnpj'))
        provider_razao = safe_strip(provider_data.get('razao_social'))
        provider_fantasia = safe_strip(provider_data.get('fantasia')) or None
        
        provider = Person.objects.filter(documento=provider_doc).first()
        if provider:
            mensagens.append(f"FORNECEDOR: {provider_razao} - EXISTE (ID: {provider.id})")
        else:
            mensagens.append(f"FORNECEDOR: {provider_razao} - NÃO EXISTE")
            provider = Person.objects.create(
                tipo='fornecedor',
                razao_social=provider_razao,
                fantasia=provider_fantasia,
                documento=provider_doc,
                status='ativo'
            )
            mensagens.append(f"Novo fornecedor criado: {provider.razao_social}")
        
        # Verify invoiced
        invoiced_data = data.get('faturado', {})
        invoiced_doc = normalize_document(invoiced_data.get('cpf_cnpj'))
        invoiced_nome = safe_strip(invoiced_data.get('nome_completo'))
        
        invoiced = Person.objects.filter(documento=invoiced_doc).first()
        if invoiced:
            mensagens.append(f"FATURADO: {invoiced_nome} - EXISTE (ID: {invoiced.id})")
        else:
            mensagens.append(f"FATURADO: {invoiced_nome} - NÃO EXISTE")
            invoiced = Person.objects.create(
                tipo='faturado',
                razao_social=invoiced_nome,
                documento=invoiced_doc,
                status='ativo'
            )
            mensagens.append(f"Novo faturado criado: {invoiced.razao_social}")
        
        # Verify and create classifications
        classification_list = data.get('classificacao_despesa', [])
        created_classifications = []
        linked_classifications = []
        
        for c in classification_list:
            c = safe_strip(c)
            if not c:
                continue
            
            classification = Classification.objects.filter(descricao__iexact=c).first()
            if classification:
                mensagens.append(f"DESPESA: {c} - EXISTE (ID: {classification.id})")
                linked_classifications.append(classification)
            else:
                mensagens.append(f"DESPESA: {c} - NÃO EXISTE")
                classification = Classification.objects.create(
                    tipo='despesa',
                    descricao=c,
                    status='ativo'
                )
                created_classifications.append(classification)
                linked_classifications.append(classification)
                mensagens.append(f"Nova classificação criada: {c}")
        
        # Create transactions and installments
        with transaction.atomic():
            result = create_service_account(data)
            
            # Se houve erro na criação, retorna o erro
            if not result.get('success'):
                mensagens.append(f"Erro ao criar registro: {result.get('error')}")
                return {
                    "success": False,
                    "mensagens": mensagens,
                    "error": result.get('error')
                }
            
            mensagens.append("Registro de movimento criado com sucesso.")
        
        # Return result complete
        return {
            "success": True,
            "mensagens": mensagens,
            "numero_nota_fiscal": result.get("numero_nota_fiscal"),
            "fornecedor": result.get("fornecedor"),
            "faturado": result.get("faturado"),
            "valor_total": result.get("valor_total"),
            "classificacoes": result.get("classificacoes"),
        }
    
    except ValidationError as e:
        mensagens.append(f"Erro de validação: {str(e)}")
        return {"success": False, "mensagens": mensagens, "error": str(e)}
    except Exception as e:
        mensagens.append(f"Erro inesperado: {str(e)}")
        return {"success": False, "mensagens": mensagens, "error": str(e)}

@transaction.atomic
def create_service_account(data: dict):
    """Recebe dicionário da extração de PDF e salva os dados no banco de dados"""
    
    try:
        # Create and search provider
        provider_data = data.get('fornecedor', {})
        provider_document = normalize_document(provider_data.get('cnpj'))
        provider_razao = safe_strip(provider_data.get('razao_social'))
        provider_fantasia = safe_strip(provider_data.get('fantasia')) or None
        
        if not provider_document or not provider_razao:
            raise ValidationError("Dados do fornecedor incompletos (CNPJ ou Razão Social)")
        
        provider, created = Person.objects.get_or_create(
            documento=provider_document,
            defaults={
                'tipo': 'fornecedor',
                'razao_social': provider_razao,
                'fantasia': provider_fantasia,
                'status': 'ativo'
            }
        )
        
        if not created:
            provider.razao_social = provider_razao
            if provider_fantasia:
                provider.fantasia = provider_fantasia
            provider.save()
            print(f"Fornecedor atualizado: {provider_razao}")
        else:
            print(f"Fornecedor criado: {provider_razao}")
        
        # Create and search invoiced 
        invoiced_data = data.get('faturado', {})
        invoiced_doc = normalize_document(invoiced_data.get('cpf_cnpj'))
        invoiced_nome = safe_strip(invoiced_data.get('nome_completo'))
        
        if not invoiced_doc or not invoiced_nome:
            raise ValidationError("Dados do faturado incompletos (CPF/CNPJ ou Nome)")
        
        invoiced, created = Person.objects.get_or_create(
            documento=invoiced_doc,
            defaults={
                'tipo': 'faturado',
                'razao_social': invoiced_nome,
                'fantasia': None,
                'status': 'ativo'
            }
        )
        
        if not created:
            invoiced.razao_social = invoiced_nome
            invoiced.save()
            print(f"Faturado atualizado: {invoiced_nome}")
        else:
            print(f"Faturado criado: {invoiced_nome}")
        
        # Create account transaction 
        data_emissao = parse_date(data.get('data_emissao'))
        if not data_emissao:
            data_emissao = datetime.now().date()
        
        total_value = Decimal(str(data.get('valor_total', 0)))
        product_description = data.get('descricao_produtos', [])
        product_description = ' | '.join(product_description) if product_description else 'Sem descrição'
        product_description = product_description[:300]
        number_nf = safe_strip(data.get('numero_nota_fiscal')) or 'S/N'
        
        # Check if invoice number already exists
        if AccountTransaction.objects.filter(numero_nota_fiscal=number_nf).exists():
            raise ValidationError(f"Número da nota fiscal '{number_nf}' já existe no banco de dados.")
        
        account_transaction = AccountTransaction.objects.create(
            tipo='a pagar',
            numero_nota_fiscal=number_nf,
            data_emissao=data_emissao,
            descricao=product_description,
            status='ativo',
            valor_total=total_value,
            fornecedor_cliente=provider,
            faturado=invoiced
        )
        
        print(f"Transação criada: #{account_transaction.id}")
        
        # Create and search classification 
        classification_list = data.get('classificacao_despesa', [])
        classification_created = []
        
        for category in classification_list:
            category = safe_strip(category)
            if not category:
                continue
            
            classification, created = Classification.objects.get_or_create(
                descricao=category,
                defaults={
                    'tipo': 'despesa',
                    'status': 'ativo'
                }
            )
            
            classification_created.append(classification)
            
            if created:
                print(f"Classificação criada: {category}")
        
        if classification_created:
            account_transaction.classificacoes.set(classification_created)
            print(f"Classificações associadas: {len(classification_created)}")
        
        # Create installments 
        qtd_installments = int(data.get('quantidade_parcelas', 1))
        data_vencimento = parse_date(data.get('data_vencimento'))
        
        if not data_vencimento:
            data_vencimento = datetime.now().date()
        
        value_installment = total_value / qtd_installments
        installment_created = []
        
        for i in range(1, qtd_installments + 1):
            data_vencimento_parcela = data_vencimento + timedelta(days=30*(i-1))
            installment = Installment.objects.create(
                account_transaction=account_transaction,
                identificacao=f"{i}/{qtd_installments}",
                data_vencimento=data_vencimento_parcela,
                valor_parcela=value_installment,
                valor_pago=Decimal('0.00'),
                valor_saldo=value_installment,
                status_parcela='aberta'
            )
            installment_created.append(installment)
            print(f"Parcela criada: {installment.identificacao}")
        
        return {
            'success': True,
            'account_transaction_id': account_transaction.id,
            'numero_nota_fiscal': number_nf,
            'fornecedor': provider.razao_social,
            'faturado': invoiced.razao_social,
            'valor_total': float(total_value),
            'parcelas_criadas': len(installment_created),
            'classificacoes': [c.descricao for c in classification_created]
        }
    
    except ValidationError as e:
        print(f"Erro de validação: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }
    except Exception as e:
        print(f"Erro ao salvar dados: {str(e)}")
        import traceback
        traceback.print_exc()  # Imprime o stack trace completo para debug
        return {
            'success': False,
            'error': f"Erro inesperado: {str(e)}"
        }