from django.shortcuts import render
from django.contrib import messages
from django.http import JsonResponse
from ...agents.extraction.invoice_extractor import PDFExtractorAgent
from ...agents.simple_rag import SimpleRAGAgent
from .models.rag import query_semantic_rag
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

            # Valida e salva dados no banco de dados
            result = process_extracted_invoice(extracted_data)

            # === 3. Mostra o relatório de verificação ===
            for line in result.get("mensagens", []):
                messages.info(request, line)

            if result.get("success"):
                messages.success(request, f"Registro criado com sucesso! "
                                          f"Nota: {result['numero_nota_fiscal']} | "
                                          f"Fornecedor: {result['fornecedor']} | "
                                          f"Valor Total: R$ {result['valor_total']:.2f}")
            else:
                messages.error(request, f"Erro ao salvar: {result.get('error')}")

            # Converte o resultado para JSON formatado
            context['json_result'] = json.dumps(extracted_data, indent=2, ensure_ascii=False)
            messages.success(request, f'Arquivo "{pdf_file.name}" processado com sucesso!')
        except Exception as e:
            messages.error(request, f'Erro ao processar o arquivo: {str(e)}')
        finally:
            # Remove o arquivo temporário
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    return render(request, 'upload/upload.html', context)


def simple_rag(request):
    if request.method == 'POST':
        question = (request.POST.get('question') or '').strip()

        # Usa SimpleRAGAgent com Function Calling integrado
        # O agente decide autonomamente se precisa consultar o banco de dados
        agent = SimpleRAGAgent()
        result = agent.query(question=question)

        return JsonResponse({
            'question': question,
            'response': result.get('response'),
            'tools_used': result.get('tools_used', []),
            'db_query_performed': result.get('db_query_performed', False),
            'error': result.get('error'),
        })

    context = {
        'title': 'Assistente (Agente Simples)',
        'subtitle': 'O agente decide automaticamente quando consultar o banco de dados.'
    }
    return render(request, 'rag/rag.html', context)

def embedding_rag_view(request):
    if request.method == 'POST':
        question = (request.POST.get('question') or '').strip()

        if not question:
            return JsonResponse({'error': 'Nenhuma pergunta fornecida.'}, status=400)

        try:
            answer = query_semantic_rag(question=question)
            
            return JsonResponse({
                'question': question,
                'response': answer,
                'error': None
            })
        except Exception as e:
            print(f"Erro na view embedding_rag_view: {e}")
            return JsonResponse({
                'question': question,
                'response': None,
                'error': f'Erro interno no servidor ao processar o RAG com embedding: {str(e)}'
            }, status=500)
            
    context = {
        'title': 'Assistente (RAG Semântico)',
        'subtitle': 'Busca inteligente com "super-contexto" e embeddings.'
    }
    return render(request, 'rag/rag.html', context)
