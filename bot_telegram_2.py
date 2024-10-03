import os
import pandas as pd
from dotenv import load_dotenv
from io import BytesIO
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler
import maritalk
import matplotlib.pyplot as plt

# Definindo os estados da conversa como constantes
ASKING_DATA_CLEANING = 1
ASKING_ANALYSIS = 2

# Função que recebe o arquivo e converte para DataFrame
async def handle_file(update: Update, context) -> int:
    file = update.message.document

    if file.mime_type in ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:  # Arquivo Excel
        file_id = file.file_id
        new_file = await context.bot.get_file(file_id)
        file_stream = BytesIO(await new_file.download_as_bytearray())
        
        # Leitura de arquivo Excel
        df = pd.read_excel(file_stream)
        context.user_data['df'] = df  # Armazenando o DataFrame no contexto do usuário
        await update.message.reply_text(f"Arquivo Excel convertido para DataFrame:\n{df.head()}")
        
    elif file.mime_type == 'text/csv':  # Arquivo CSV
        file_id = file.file_id
        new_file = await context.bot.get_file(file_id)
        file_stream = BytesIO(await new_file.download_as_bytearray())
        
        # Leitura de arquivo CSV
        df = pd.read_csv(file_stream)
        context.user_data['df'] = df  # Armazenando o DataFrame no contexto do usuário
        await update.message.reply_text(f"Arquivo CSV convertido para DataFrame:\n{df.head()}")
    
    else:
        await update.message.reply_text("Por favor, envie um arquivo .xlsx ou .csv.")
        return ConversationHandler.END

    # Pergunta ao usuário sobre o tratamento de dados
    await update.message.reply_text("Agora que o dataset foi carregado, que tipo de tratamento de dados você gostaria de fazer? (Exemplo: remover valores nulos, normalizar colunas, etc.)")
    
    return ASKING_DATA_CLEANING  # Avança para o próximo estado

# Função para gerar e executar o código de tratamento de dados usando IA
async def handle_data_cleaning(update: Update, context) -> int:
    df = context.user_data.get('df')
    
    if df is not None:
        user_input = update.message.text  # Pega a instrução do usuário
        
        # Aqui você faria a chamada à API de IA com o input do usuário para gerar o código
        # Exemplo: resposta_da_IA = chamada_para_IA(user_input)
        # Vamos simular a resposta da IA com um exemplo simples:
        resposta_da_IA = """
df.dropna(inplace=True)
print("Valores nulos removidos")
"""
        # Executa o código gerado pela IA
        try:
            exec(resposta_da_IA, globals(), locals())
            await update.message.reply_text("Código de tratamento executado com sucesso!")
        except Exception as e:
            await update.message.reply_text(f"Houve um erro ao executar o código: {str(e)}")
        
        # Mostra o DataFrame atualizado
        await update.message.reply_text(f"DataFrame após o tratamento:\n{df.head()}")
        
        # Pergunta ao usuário sobre as análises ou gráficos
        await update.message.reply_text("Agora, gostaria de gerar algum tipo de análise ou gráfico? (Exemplo: gráfico de barras, análise de correlação, etc.)")
        
        return ASKING_ANALYSIS  # Avança para o próximo estado

    else:
        await update.message.reply_text("Nenhum DataFrame foi carregado ainda.")
        return ConversationHandler.END

# Função para gerar e executar código de análise e gráficos usando IA
async def handle_analysis(update: Update, context) -> int:
    df = context.user_data.get('df')
    
    if df is not None:
        user_input = update.message.text  # Pega a instrução do usuário
        
        # Aqui você faria a chamada à API de IA para gerar o código de análise ou gráfico
        # Exemplo: resposta_da_IA = chamada_para_IA(user_input)
        # Vamos simular a resposta da IA com um exemplo simples:
        resposta_da_IA = """
df['Estado'].value_counts().plot(kind='bar')
plt.show()
"""
        # Executa o código gerado pela IA
        try:
            exec(resposta_da_IA, globals(), locals())
            await update.message.reply_text("Gráfico gerado com sucesso!")
        except Exception as e:
            await update.message.reply_text(f"Houve um erro ao executar o código: {str(e)}")
        
        return ConversationHandler.END
    
    else:
        await update.message.reply_text("Nenhum DataFrame foi carregado ainda.")
        return ConversationHandler.END

# Função de cancelamento
async def cancel(update: Update, context) -> int:
    await update.message.reply_text("Operação cancelada.")
    return ConversationHandler.END

# Função de start
async def start(update: Update, context) -> None:
    await update.message.reply_text('Olá! Envie um arquivo .xlsx ou .csv para começar.')

def main():
    # Coloque seu token do bot aqui
    load_dotenv('.env')
    TOKEN = os.getenv('BOT_TOKEN')
    KEY = os.getenv('MARITACA_KEY')
    
    # Criando a aplicação
    application = Application.builder().token(TOKEN).connect_timeout(20).build()

    # Configurando o ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Document.MimeType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") | 
                                     filters.Document.MimeType("application/vnd.ms-excel") | 
                                     filters.Document.MimeType("text/csv"), handle_file)],
        
        states={
            ASKING_DATA_CLEANING: [MessageHandler(filters.TEXT, handle_data_cleaning)],
            ASKING_ANALYSIS: [MessageHandler(filters.TEXT, handle_analysis)]
        },
        
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)

    # Iniciando o bot
    application.run_polling()

if __name__ == '__main__':
    main()

    # prompt_inicial = f'''Hoje você será uma IA especializada em análise de dados que conversará com um usuário
    # como um chatbot do Telegram, que enviará um conjunto de dados para análise. Vou te enviar comandos e análises
    # pedidas por mim ou pelo usuário e você responderá precisamente meus comandos e conversará com o usuário de forma 
    # eficiente e precisa. 
    # '''

    # prompt = f'''Dado as primeiras 5 colunas de um conjunto de dados:\n{head}\n
    # Caso todas as colunas esteja com bons nomes, pergunte ao usuário se ele confirma essa tabela.
    # Se não, para cada coluna sem nome, sugira um nome que descreva os dados.
    # Não há necessidade de mostrar os dados.
    # Em seguida, pergunte ao usuário quais colunas ele deseja trocar e para quais nomes.
    # Peça a resposta final do usuário e assuma que não haverá mais interação com você.
    # '''

    # model = maritalk.MariTalk(
    #     key = KEY,
    #     model = "sabia-3"  # No momento, suportamos os modelos sabia-3, sabia-2-medium e sabia-2-small
    # )
