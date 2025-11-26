from django.shortcuts import render
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.conf import settings
from django.db import transaction
from django.db.models import Q 
from django.views.decorators.http import require_http_methods
from django.shortcuts import render, redirect, get_object_or_404
from ...agents.extraction.invoice_extractor import PDFExtractorAgent
from ...agents.simple_rag import SimpleRAGAgent
from ...agents.embedding.embedding_agent import EmbeddingAgent
from .models.rag import query_semantic_rag, query_semantic_rag_with_history
from .models.person import Person
from .models.classification import Classification
from .models.account_transaction import AccountTransaction
from .models.installment import Installment
from .forms import PersonForm, ClassificationForm, TransactionForm, TransactionEditForm
from .services import process_extracted_invoice
from decimal import Decimal
from datetime import timedelta
import json
import os

def upload_pdf(request):
    context = {}
    if request.method == 'POST' and request.FILES.get('pdf_file'):
        pdf_file = request.FILES['pdf_file']

        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
        temp_path = os.path.join(settings.MEDIA_ROOT, pdf_file.name)
        with open(temp_path, 'wb+') as destination:
            for chunk in pdf_file.chunks():
                destination.write(chunk)
        
        try:
            # Extrai dados do PDF
            extractor_agent = PDFExtractorAgent()
            extracted_data = extractor_agent.extract_pdf_to_json(temp_path)

            # Verifica se houve erro na extração
            if isinstance(extracted_data, dict) and extracted_data.get('error'):
                raise Exception(extracted_data['error'])

            # Valida e salva dados no banco de dados
            result = process_extracted_invoice(extracted_data)

            if result.get("success"):
                messages.success(
                    request,
                    f"Nota fiscal {result['numero_nota_fiscal']} registrada com sucesso. "
                    f"Valor: R$ {result['valor_total']:.2f}"
                )
            else:
                messages.error(request, result.get('error', 'Erro desconhecido ao salvar'))

            # Converte o resultado para JSON formatado
            context['json_result'] = json.dumps(extracted_data, indent=2, ensure_ascii=False)

        except Exception as e:
            messages.error(request, str(e))
        finally:
            # Remove o arquivo temporário
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    return render(request, 'upload/upload.html', context)

def simple_rag(request):
    if request.method == 'POST':
        question = (request.POST.get('question') or '').strip()
        session_id = request.POST.get('session_id')  # Recebe session_id do frontend

        # Usa SimpleRAGAgent com chat e histórico
        agent = SimpleRAGAgent()
        result = agent.query_with_chat(question=question, session_id=session_id)

        return JsonResponse({
            'question': question,
            'response': result.get('response'),
            'tools_used': result.get('tools_used', []),
            'db_query_performed': result.get('db_query_performed', False),
            'error': result.get('error'),
            'session_id': result.get('session_id'),  # Retorna session_id
            'is_new_session': result.get('is_new_session', False)
        })

    context = {
        'title': 'Assistente (Agente Simples)',
        'subtitle': 'O agente decide automaticamente quando consultar o banco de dados.'
    }
    return render(request, 'rag/rag.html', context)

def embedding_rag_view(request):
    if request.method == 'POST':
        question = (request.POST.get('question') or '').strip()
        session_id = request.POST.get('session_id')  # Recebe session_id do frontend

        if not question:
            return JsonResponse({'error': 'Nenhuma pergunta fornecida.'}, status=400)

        try:
            # Usa o novo método com histórico
            result = query_semantic_rag_with_history(
                question=question,
                session_id=session_id
            )

            return JsonResponse({
                'question': question,
                'response': result.get('response'),
                'error': result.get('error'),
                'session_id': result.get('session_id'),
                'is_new_session': result.get('is_new_session', False),
                'transactions_found': result.get('transactions_found', 0)
            })
        except Exception as e:
            print(f"Erro na view embedding_rag_view: {e}")
            return JsonResponse({
                'question': question,
                'response': None,
                'error': f'Erro interno no servidor ao processar o RAG com embedding: {str(e)}',
                'session_id': session_id
            }, status=500)

    context = {
        'title': 'Assistente (RAG Semântico)',
        'subtitle': 'Busca inteligente com "super-contexto" e embeddings.'
    }
    return render(request, 'rag/rag.html', context)

def manual_registration(request):
    # Inicializa os formulários vazios
    person_form = PersonForm()
    classification_form = ClassificationForm()
    transaction_form = TransactionForm()
    
    active_tab = 'person' # Aba padrão

    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        
        if form_type == 'person':
            active_tab = 'person'
            person_form = PersonForm(request.POST)
            if person_form.is_valid():
                person_form.save()
                messages.success(request, 'Pessoa cadastrada com sucesso!')
                return redirect('manual_registration')
            else:
                messages.error(request, 'Erro ao cadastrar pessoa. Verifique os campos.')
                
        elif form_type == 'classification':
            active_tab = 'classification'
            classification_form = ClassificationForm(request.POST)
            if classification_form.is_valid():
                classification_form.save()
                messages.success(request, 'Classificação cadastrada com sucesso!')
                return redirect('manual_registration')
            else:
                messages.error(request, 'Erro ao cadastrar classificação.')
                
        elif form_type == 'transaction':
            active_tab = 'transaction'
            transaction_form = TransactionForm(request.POST)
            
            if transaction_form.is_valid():
                try:
                    # Uso do transaction.atomic() requer "from django.db import transaction"
                    with transaction.atomic():
                        # 1. Salva a transação principal
                        account_transaction = transaction_form.save()
                        
                        # 2. Lógica de Parcelas
                        qtd_parcelas = transaction_form.cleaned_data['quantidade_parcelas']
                        data_primeiro_vencimento = transaction_form.cleaned_data['primeiro_vencimento']
                        valor_total = account_transaction.valor_total
                        
                        valor_parcela = valor_total / qtd_parcelas
                        
                        for i in range(1, qtd_parcelas + 1):
                            # Calcula vencimento (adiciona 30 dias para cada parcela subsequente)
                            data_venc = data_primeiro_vencimento + timedelta(days=30 * (i - 1))
                            
                            Installment.objects.create(
                                account_transaction=account_transaction,
                                identificacao=f"{i}/{qtd_parcelas}",
                                data_vencimento=data_venc,
                                valor_parcela=valor_parcela,
                                valor_saldo=valor_parcela, # Saldo inicial igual ao valor
                                status_parcela='aberta'
                            )

                        # 3. Indexação RAG (Criar Embedding)
                        # Prepara dados mockados para o agente de embedding
                        mock_data = {
                            'numero_nota_fiscal': account_transaction.numero_nota_fiscal,
                            'valor_total': float(account_transaction.valor_total),
                            'data_emissao': str(account_transaction.data_emissao),
                            'data_vencimento': str(data_primeiro_vencimento),
                            'quantidade_parcelas': qtd_parcelas,
                            'descricao_produtos': [account_transaction.descricao]
                        }
                        
                        # Pega os nomes das classificações selecionadas
                        classification_names = [c.descricao for c in account_transaction.classificacoes.all()]

                        embedding_agent = EmbeddingAgent()
                        embedding_vector = embedding_agent.generate_transaction_embedding(
                            data=mock_data,
                            provider_name=account_transaction.fornecedor_cliente.razao_social,
                            invoiced_name=account_transaction.faturado.razao_social,
                            classifications=classification_names
                        )

                        if embedding_vector:
                            account_transaction.descricao_embedding = embedding_vector
                            account_transaction.save(update_fields=['descricao_embedding'])

                        messages.success(request, f'Conta cadastrada com {qtd_parcelas} parcelas!')
                        return redirect('manual_registration')

                except Exception as e:
                    # O rollback acontece automaticamente aqui se der erro
                    messages.error(request, f'Erro ao processar transação: {str(e)}')
            else:
                messages.error(request, 'Erro ao cadastrar conta. Verifique os campos obrigatórios.')

    context = {
        'person_form': person_form,
        'classification_form': classification_form,
        'transaction_form': transaction_form,
        'active_tab': active_tab
    }
    return render(request, 'registration/manual_registration.html', context)

def view_registrations(request):
    """Renderiza a página de visualização vazia inicialmente."""
    return render(request, 'registration/view_registrations.html')

def search_registrations(request):
    """API para buscar dados dinamicamente via AJAX."""
    search_type = request.GET.get('type')
    query = request.GET.get('query', '').strip()
    
    data = []
    
    try:
        if search_type == 'person':
            qs = Person.objects.filter(status='ativo')
            if query:
                # Busca por nome, documento ou fantasia
                qs = qs.filter(
                    Q(razao_social__icontains=query) | 
                    Q(documento__icontains=query) |
                    Q(fantasia__icontains=query)
                )
            
            # Formata os dados para o frontend
            for p in qs.order_by('-id')[:50]:
                data.append({
                    'id': p.id,
                    'type': 'person',
                    'col1': p.razao_social,
                    'col2': p.get_tipo_display(), # Usa o display legível do choice
                    'col3': p.documento,
                    'col4': p.fantasia or '-'
                })

        elif search_type == 'classification':
            qs = Classification.objects.filter(status='ativo')
            if query:
                qs = qs.filter(descricao__icontains=query)
                
            for c in qs.order_by('descricao')[:50]:
                data.append({
                    'id': c.id,
                    'type': 'classification',
                    'col1': c.descricao,
                    'col2': c.tipo.capitalize(),
                    'col3': '-', # Classificação tem menos colunas
                    'col4': '-'
                })

        elif search_type == 'transaction':
            qs = AccountTransaction.objects.filter(status='ativo').select_related('fornecedor_cliente')
            if query:
                qs = qs.filter(
                    Q(numero_nota_fiscal__icontains=query) |
                    Q(fornecedor_cliente__razao_social__icontains=query) |
                    Q(descricao__icontains=query)
                )
            
            for t in qs.order_by('-data_emissao')[:50]:
                data.append({
                    'id': t.id,
                    'type': 'transaction',
                    'col1': t.data_emissao.strftime('%d/%m/%Y'),
                    'col2': t.numero_nota_fiscal,
                    'col3': t.fornecedor_cliente.razao_social,
                    'col4': f"R$ {t.valor_total}"
                })

        return JsonResponse({'success': True, 'data': data})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@require_http_methods(["POST"])
def delete_registration(request):
    """API para realizar Delete (mudar status para inativo)."""
    try:
        data = json.loads(request.body)
        item_type = data.get('type')
        item_id = data.get('id')
        
        obj = None
        if item_type == 'person':
            obj = Person.objects.get(id=item_id)
        elif item_type == 'classification':
            obj = Classification.objects.get(id=item_id)
        elif item_type == 'transaction':
            obj = AccountTransaction.objects.get(id=item_id)
        else:
            return JsonResponse({'success': False, 'error': 'Tipo de item inválido.'})
            
        if hasattr(obj, 'desactivate'):
            obj.desactivate() # Se o model tiver esse método helper
        else:
            obj.status = 'inativo'
            obj.save()
            
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

def edit_registration(request, item_type, item_id):
    """View genérica para editar Pessoa, Classificação ou Transação."""
    
    if item_type == 'person':
        model = Person
        form_class = PersonForm
        redirect_name = 'Pessoa'
    elif item_type == 'classification':
        model = Classification
        form_class = ClassificationForm
        redirect_name = 'Classificação'
    elif item_type == 'transaction':
        model = AccountTransaction
        form_class = TransactionEditForm # Usa o form especial de edição
        redirect_name = 'Conta'
    else:
        messages.error(request, 'Tipo de registro inválido.')
        return redirect('view_cadastros')

    # Busca o objeto ou 404
    obj = get_object_or_404(model, id=item_id)

    if request.method == 'POST':
        form = form_class(request.POST, instance=obj)
        if form.is_valid():
            try:
                with transaction.atomic():
                    saved_obj = form.save()
                    
                    # Se for transação, atualiza o embedding do RAG
                    if item_type == 'transaction':
                        try:
                            # Pega nomes das classificações
                            classification_names = [c.descricao for c in saved_obj.classificacoes.all()]
                            
                            # Recria embedding
                            mock_data = {
                                'numero_nota_fiscal': saved_obj.numero_nota_fiscal,
                                'valor_total': float(saved_obj.valor_total),
                                'data_emissao': str(saved_obj.data_emissao),
                                'data_vencimento': 'Mantido', # Não altera parcelas na edição simples
                                'quantidade_parcelas': saved_obj.parcelas.count(),
                                'descricao_produtos': [saved_obj.descricao]
                            }
                            
                            embedding_agent = EmbeddingAgent()
                            embedding_vector = embedding_agent.generate_transaction_embedding(
                                data=mock_data,
                                provider_name=saved_obj.fornecedor_cliente.razao_social,
                                invoiced_name=saved_obj.faturado.razao_social,
                                classifications=classification_names
                            )
                            
                            if embedding_vector:
                                saved_obj.descricao_embedding = embedding_vector
                                saved_obj.save(update_fields=['descricao_embedding'])
                        except Exception as e:
                            print(f"Erro ao atualizar embedding na edição: {e}")

                messages.success(request, f'{redirect_name} atualizado com sucesso!')
                return redirect('view_cadastros')
            except Exception as e:
                messages.error(request, f'Erro ao salvar: {str(e)}')
    else:
        form = form_class(instance=obj)

    context = {
        'form': form,
        'object_name': str(obj),
        'type_label': redirect_name
    }
    return render(request, 'registration/edit_registration.html', context)
