from django.shortcuts import render
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.conf import settings
from django.db import transaction
from ...agents.extraction.invoice_extractor import PDFExtractorAgent
from ...agents.simple_rag import SimpleRAGAgent
from ...agents.embedding.embedding_agent import EmbeddingAgent
from .models.rag import query_semantic_rag, query_semantic_rag_with_history
from .models.person import Person
from .models.classification import Classification
from .models.account_transaction import AccountTransaction
from .models.installment import Installment
from .forms import PersonForm, ClassificationForm, TransactionForm
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
    # Busca simples de todos os dados
    people = Person.objects.all().order_by('-id')[:50]
    classifications = Classification.objects.all().order_by('tipo', 'descricao')
    transactions = AccountTransaction.objects.all().order_by('-data_emissao')[:50]
    
    context = {
        'people': people,
        'classifications': classifications,
        'transactions': transactions
    }
    return render(request, 'registration/view_registrations.html', context)
