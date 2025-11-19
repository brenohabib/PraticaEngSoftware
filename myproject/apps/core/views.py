from django.shortcuts import render
from django.contrib import messages
from django.http import JsonResponse
from ...agents.extraction.invoice_extractor import PDFExtractorAgent
from ...agents.simple_rag import SimpleRAGAgent
from .models.rag import query_semantic_rag, query_semantic_rag_with_history
from .services import process_extracted_invoice
import json
import os
from django.conf import settings

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
