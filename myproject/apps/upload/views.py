from django.shortcuts import render
from django.contrib import messages
from ...agents.extraction.invoice_extractor import PDFExtractorAgent
from ..models.services import process_extracted_invoice
import json
import os
from django.conf import settings

def upload_pdf(request):
    context = {}
    if request.method == 'POST' and request.FILES.get('pdf_file'):
        pdf_file = request.FILES['pdf_file']

        # Salva o arquivo temporariamente
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
                messages.success(request, f"✅ Registro criado com sucesso! "
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
