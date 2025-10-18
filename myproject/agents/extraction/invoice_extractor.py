import os
import json
import time
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Carrega variáveis de ambiente
load_dotenv()

# Configura a API do Gemini
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    logger.error("GEMINI_API_KEY não encontrada nas variáveis de ambiente")
    raise ValueError("GEMINI_API_KEY não configurada")

client = genai.Client(api_key=api_key)


class PDFExtractorAgent:
    def __init__(self, model_name='gemini-2.5-flash-lite'):
        """
        Inicializa o agente extrator de PDFs.
        
        Args:
            model_name (str): Nome do modelo Gemini a ser utilizado
        """
        self.model_name = model_name
        self.prompt_template = """
            Você é um especialista em análise de documentos fiscais. Analise a nota fiscal fornecida e extraia apenas as informações solicitadas, retornando um **JSON válido** no formato especificado abaixo.

            ### Campos a extrair:

            1. **Fornecedor (Emitente)**
            - razão_social
            - fantasia (ou null, se não houver)
            - cnpj

            2. **Faturado (Destinatário/Cliente)**
            - nome_completo
            - cpf_cnpj

            3. **Número da Nota Fiscal**
            4. **Data de Emissão** (DD/MM/AAAA)
            5. **Descrição dos Produtos** (array de strings)
            6. **Classificação de Despesa** (array de categorias, conforme critérios abaixo)
            7. **Quantidade de Parcelas** (1 se à vista)
            8. **Data de Vencimento** (DD/MM/AAAA)
            9. **Valor Total** (número decimal)

            ### Formato de Resposta:
            Retorne **apenas** um objeto JSON com a seguinte estrutura:
            {
            "fornecedor": {
                "razao_social": "string",
                "fantasia": "string ou null",
                "cnpj": "string"
            },
            "faturado": {
                "nome_completo": "string",
                "cpf_cnpj": "string"
            },
            "numero_nota_fiscal": "string",
            "data_emissao": "DD/MM/AAAA",
            "descricao_produtos": ["string"],
            "classificacao_despesa": ["string"],
            "quantidade_parcelas": número,
            "data_vencimento": "DD/MM/AAAA",
            "valor_total": número
            }

            ### Critério para “classificacao_despesa”:
            Associe `descricao_produtos` à categoria correspondente entre as opções abaixo (sem duplicar valores):

            - INSUMOS AGRÍCOLAS : Sementes, Fertilizantes, Defensivos (Apenas produtos associados à agricultura, não infraestrutura)
            - MANUTENÇÃO E OPERAÇÃO : Combustíveis, Peças, Pneus, Ferramentas, Parafusos, Infraestrutura, etc.
            - RECURSOS HUMANOS : Mão de obra, Salários
            - SERVIÇOS OPERACIONAIS : Frete, Transporte, Colheita, Armazenagem, Secagem
            - INFRAESTRUTURA E UTILIDADES : Energia, Arrendamento, Materiais de construção
            - ADMINISTRATIVAS : Honorários, Despesas bancárias, Contabilidade
            - SEGUROS E PROTEÇÃO : Seguros agrícolas ou de veículos
            - IMPOSTOS E TAXAS : ITR, IPTU, IPVA, INCRA, etc.
            - INVESTIMENTOS : Aquisição de máquinas, veículos, imóveis  
            - OUTRAS DESPESAS : Se não se enquadrar em nenhuma das anteriores

            ### Regras Gerais:
            - Retorne somente o JSON, sem explicações.  
            - Campos não encontrados → **null**
            - Datas → formato **DD/MM/AAAA**
            - Valores monetários → **número decimal (ex: 1500.50)**
            - Lista de classificações sem duplicatas

        """

    def _clean_json_response(self, response_text):
        """
        Limpa a resposta da API para extrair apenas o JSON válido.
        
        Args:
            response_text (str): Texto da resposta da API
            
        Returns:
            str: JSON limpo
        """
        json_str = response_text.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        elif json_str.startswith("```"):
            json_str = json_str[3:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        
        return json_str.strip()

    def extract_pdf_to_json(self, pdf_path, max_retries=3, retry_delay=2):
        """
        Extrai informações de um PDF e retorna em formato JSON usando upload direto do arquivo
        
        Args:
            pdf_path (str): Caminho para o arquivo PDF
            max_retries (int): Número máximo de tentativas em caso de falha
            retry_delay (int): Tempo de espera entre tentativas em segundos
            
        Returns:
            dict: Dados extraídos em formato JSON ou mensagem de erro
        """
        uploaded_file = None
        
        # Validação inicial do arquivo
        if not os.path.exists(pdf_path):
            logger.error(f"Arquivo não encontrado: {pdf_path}")
            return {"error": f"Arquivo não encontrado: {pdf_path}"}
        
        # Tenta fazer upload do arquivo
        try:
            logger.info(f"Fazendo upload do arquivo: {pdf_path}")
            uploaded_file = client.files.upload(file=pdf_path)
            logger.info(f"Arquivo enviado com sucesso. URI: {uploaded_file.uri}")
        except Exception as e:
            logger.error(f"Erro ao fazer upload do arquivo: {str(e)}")
            return {"error": f"Falha no upload do arquivo: {str(e)}"}
        
        # Loop de tentativas para processar o PDF
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Tentativa {attempt}/{max_retries} - Processando PDF...")
                
                # Gera o conteúdo usando o arquivo já carregado
                response = client.models.generate_content(
                    model=self.model_name,
                    contents=[self.prompt_template, uploaded_file]
                )
                
                # Extrai o texto da resposta
                if not response or not response.text:
                    raise ValueError("Resposta vazia da API")
                
                response_text = response.text
                
                # Limpa e valida o JSON
                cleaned_json = self._clean_json_response(response_text)
                
                # Tenta fazer o parse do JSON
                extracted_data = json.loads(cleaned_json)
                
                logger.info("Extração concluída com sucesso!")
                return extracted_data
                
            except json.JSONDecodeError as e:
                logger.error(f"Tentativa {attempt}/{max_retries} - Erro ao decodificar JSON: {str(e)}")
                logger.debug(f"Resposta que causou erro: {response_text[:500]}...")
                
                if attempt < max_retries:
                    logger.info(f"Aguardando {retry_delay}s antes da próxima tentativa...")
                    time.sleep(retry_delay)
                else:
                    return {
                        "error": "Falha ao decodificar JSON após todas as tentativas",
                        "raw_response": response_text,
                        "attempts": max_retries
                    }
                    
            except ValueError as e:
                logger.error(f"Tentativa {attempt}/{max_retries} - Erro de validação: {str(e)}")
                
                if attempt < max_retries:
                    logger.info(f"Aguardando {retry_delay}s antes da próxima tentativa...")
                    time.sleep(retry_delay)
                else:
                    return {
                        "error": f"Erro de validação após todas as tentativas: {str(e)}",
                        "attempts": max_retries
                    }
                    
            except Exception as e:
                logger.error(f"Tentativa {attempt}/{max_retries} - Erro inesperado: {str(e)}")
                
                if attempt < max_retries:
                    logger.info(f"Aguardando {retry_delay}s antes da próxima tentativa...")
                    time.sleep(retry_delay)
                else:
                    return {
                        "error": f"Erro inesperado após todas as tentativas: {str(e)}",
                        "attempts": max_retries
                    }
        
        # Se chegou aqui, todas as tentativas falhar
        return {
            "error": "Todas as tentativas de extração falharam",
            "attempts": max_retries
        }