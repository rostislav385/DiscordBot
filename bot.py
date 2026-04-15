import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import datetime
import requests
import json
import os

# --- НАСТРОЙКИ ---
TOKEN = "OTE4ODY2MDE2Nzg2ODcwMzQ0.YbNeqg.ldcYDqcZHqpt6eOKHU_AqjO6ABQ"
WEATHER_KEY = "8df66ea034d465bc4d48dec3664d8ebb"
YOUTUBE_KEY = "AIzaSy..."  # Твой ключ
ADMIN_ID = 602963814119374877
TRUSTED_ADMINS = [602963814119374877, 586956501491384335]  # Твой ID и ID других админов
TICKET_ROLES = {
    "Перемещалка": 937795813080436767, # Роль, которую нельзя выдать просто так
    "Типо админ": 938876508674609242,
    "Stream unlocker" : 1479509836747116576
}
AUTO_ROLES = {
    "CS 2 | Player": 1169984781107335168,
    "Dota 2 | Player": 1169984533551132773,
    "PUBG | Player": 1415653400414257232,
    "Valorant | Player": 1158675689734668328
}


# --- БАЗА ДАННЫХ (JSON) ---
def load_data(file):
    if not os.path.exists(file): return {}
    with open(file, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_data(file, data):
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="#", intents=intents)

    async def setup_hook(self):
        # Теперь бот увидит этот таск, так как он внутри класса
        self.check_games.start()
        await self.tree.sync()

    # Переносим таск внутрь класса и добавляем (self)
    @tasks.loop(seconds=60)
    async def check_games(self):
        # 1. Получаем текущее время ПК
        now = datetime.datetime.now()
        current_hour = now.hour
        current_minute = now.minute

        # 2. Загружаем данные из JSON
        data = load_data("play.json")
        if not data:
            return

        updated_data = data.copy()  # Копия для безопасного удаления
        was_changed = False

        # 3. Перебираем все запланированные игры
        for guild_id, info in data.items():
            target_hour = info['hour']
            target_minute = info['minute']

            # Сравниваем: если текущее время больше или равно запланированному
            # (Обычно проверяют на строгое равенство, чтобы бот не спамил,
            # если игра была в 12:00, а сейчас уже 12:05)
            if current_hour == target_hour and current_minute == target_minute:

                # Ищем канал по ID (подставь свой ID)
                channel_id = 1378115489376768102
                channel = self.get_channel(channel_id)

                if channel:
                    game_name = info['game']
                    await channel.send(f"@everyone, время пришло! Начинаем играть в **{game_name}**!")

                # 4. Удаляем событие из памяти (копии словаря)
                del updated_data[guild_id]
                was_changed = True

        # 5. Если были удаления, перезаписываем файл
        if was_changed:
            save_data("play.json", updated_data)
            print(f"[{now.strftime('%H:%M')}] Событие обработано и удалено из базы.")


bot = MyBot()

# --- ЛОГИКА ИГРЫ (Крестики-Нолики) ---
# Храним игры для каждого канала отдельно
active_games = {}


class TicTacToe:
    def __init__(self):
        self.board = [str(i) for i in range(1, 10)]
        self.turn = "X"
        self.winner = None

    def check_winner(self):
        win_coords = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
        for combo in win_coords:
            if self.board[combo[0]] == self.board[combo[1]] == self.board[combo[2]]:
                self.winner = self.board[combo[0]]
                return True
        if all(x in ["X", "O"] for x in self.board):
            self.winner = "Draw"
            return True
        return False


class RoleSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=name, description="Получить сразу") for name in AUTO_ROLES.keys()]
        options += [discord.SelectOption(label=name, description="Через тикет") for name in TICKET_ROLES.keys()]
        super().__init__(placeholder="Выберите роль...", options=options)

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]

        if choice in AUTO_ROLES:
            role = interaction.guild.get_role(AUTO_ROLES[choice])
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ Роль {choice} выдана!", ephemeral=True)

        elif choice in TICKET_ROLES:
            # Открываем модальное окно для тикета
            await interaction.response.send_modal(TicketModal(choice, TICKET_ROLES[choice]))

class RoleView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(RoleSelect())


class TicketModal(discord.ui.Modal, title="Заявка на получение роли"):
    info = discord.ui.TextInput(label="Полезная информация", style=discord.TextStyle.paragraph,
                                placeholder="Что нам надо знать?", required=False)
    reason = discord.ui.TextInput(label="Причина получения", style=discord.TextStyle.short,
                                  placeholder="Почему именно вы?", required=True)

    def __init__(self, role_name, role_id):
        super().__init__()
        self.role_name = role_name
        self.role_id = role_id

    async def on_submit(self, interaction: discord.Interaction):
        tickets = load_data("tickets.json")
        id_data = load_data("important_values.json")
        user_data = load_data("user_date.json")
        user_id_str = str(interaction.user.id)  # JSON ключи всегда строки

        # 2. Проверяем, создавал ли он тикеты раньше
        if user_id_str in user_data:
            # Если есть, увеличиваем на 1
            user_data[user_id_str]["tickets"] += 1
        else:
            # Если нет, создаем структуру с первым тикетом
            user_data[user_id_str] = {"tickets": 1}

        # 3. Сохраняем обновленную статистику
        save_data("user_date.json", user_data)

        # 2. Вычисляем новый ID
        new_ticket_id = int(id_data.get("last_ticket_id", 0)) + 1

        # 3. СРАЗУ сохраняем обновленный ID обратно в файл
        id_data["last_ticket_id"] = new_ticket_id
        save_data("important_values.json", id_data)
        #ticket_id = str(len(tickets) + 1)

        tickets[new_ticket_id] = {
            "user_name": interaction.user.name,
            "user_id": interaction.user.id,
            "role_name": self.role_name,
            "role_id": self.role_id,
            "info": self.info.value,
            "reason": self.reason.value,
            "status": "pending"
        }
        save_data("tickets.json", tickets)

        await interaction.response.send_message(f"✅ Тикет #{new_ticket_id} создан! Ожидайте решения администрации.",
                                                ephemeral=True)

class AdminTicketView(discord.ui.View):
    def __init__(self, ticket_id):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Проверяем, есть ли ID пользователя в списке доверенных
        if interaction.user.id in TRUSTED_ADMINS:
            return True  # Доступ разрешен, кнопка сработает

        # Если ID нет в списке, отправляем скрытое сообщение
        await interaction.response.send_message(
            "🛑 У вас нет доступа к управлению тикетами!",
            ephemeral=True
        )
        return False

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_ticket(interaction, "accepted")

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.red)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_ticket(interaction, "rejected")

    async def process_ticket(self, interaction: discord.Interaction, status):
        tickets = load_data("tickets.json")
        t = tickets.get(self.ticket_id)
        if not t: return

        # 2. Подготовка данных для архива (добавляем новые значения)
        t['closed_by'] = interaction.user.name  # Кто обработал
        t['final_status'] = status  # Итоговый статус
        t['closed_at'] = str(interaction.created_at)

        # 3. Сохранение в архив
        archive = load_data("archive.json")  # Загружаем (или создаем пустой) архив
        archive[self.ticket_id] = t  # Добавляем наш дополненный тикет
        save_data("archive.json", archive)

        user = interaction.guild.get_member(t['user_id'])
        if status == "accepted" and user:
            role = interaction.guild.get_role(t['role_id'])
            await user.add_roles(role)
            try: await user.send(f"🎉 Ваша заявка на роль **{t['role_name']}** принята!")
            except: pass
        elif status == "rejected" and user:
            try: await user.send(f"❌ Ваша заявка на роль **{t['role_name']}** была отклонена.")
            except: pass

        del tickets[self.ticket_id]
        save_data("tickets.json", tickets)
        await interaction.response.edit_message(content=f"Тикет #{self.ticket_id} обработан: **{status}**", view=None)


# --- КОМАНДЫ ---

@bot.tree.command(name="ping", description="Проверка пинга")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency * 1000)}ms")


@bot.tree.command(name="tickets_check", description="Проверка активных тикетов (только для админов)")
async def tickets_check(interaction: discord.Interaction):
    if interaction.user.id not in TRUSTED_ADMINS:
        return await interaction.response.send_message("⛔ У вас нет прав для этой команды!", ephemeral=True)

    tickets = load_data("tickets.json")
    if not tickets:
        return await interaction.response.send_message("Активных тикетов нет.", ephemeral=True)

    await interaction.response.send_message("Список тикетов:", ephemeral=True)

    for tid, t in tickets.items():
        embed = discord.Embed(title=f"Тикет #{tid}", color=discord.Color.blue())
        embed.add_field(name="От", value=f"{t['user_name']} (<@{t['user_id']}>)")
        embed.add_field(name="Роль", value=t['role_name'])
        embed.add_field(name="Инфо", value=t['info'], inline=False)
        embed.add_field(name="Причина", value=t['reason'], inline=False)

        await interaction.channel.send(embed=embed, view=AdminTicketView(tid))

@bot.tree.command(name="add_role", description="Открыть меню выбора ролей")
async def add_role(interaction: discord.Interaction):
    await interaction.response.send_message("Выберите роль из списка ниже:", view=RoleView(), ephemeral=True)


@bot.tree.command(name="profile", description="Показывает инфу про тебя")
async def profile(interaction: discord.Interaction):
    # Добавим try-except, чтобы если команда упадет, ты увидел ошибку в консоли
    try:
        data = load_data("stats.json")
        user_data = load_data("user_date.json")
        user_id = interaction.user.id
        user_name = interaction.user.name
        total_tickets = user_data.get(str(user_id), {}).get("tickets", 0)

        # Если юзера нет в базе, вернем 0 вместо None
        user_message_count = data.get(str(user_id), 0)

        await interaction.response.send_message(
            f"👤 **Профиль: {user_name}**\n"
            f"🆔 Ваш ID: `{user_id}`\n"
            f"📝 Сообщений отправлено: `{user_message_count}`\n"
            f"🎫 Создано тикетов: `{total_tickets}`"
        )
    except Exception as e:
        print(f"Ошибка в команде profile: {e}")
        await interaction.response.send_message("Произошла ошибка при загрузке профиля.", ephemeral=True)

@bot.tree.command(name="weather", description="Узнать погоду")
@app_commands.describe(city="Название города")
async def weather(interaction: discord.Interaction, city: str):
    url = f'http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_KEY}&units=metric'
    res = requests.get(url).json()
    if res.get("cod") == 200:
        temp = res["main"]["temp"]
        desc = res["weather"][0]["description"]
        await interaction.response.send_message(f"В {city}: {desc}, {temp}°C")
    else:
        await interaction.response.send_message("Город не найден.", ephemeral=True)


@bot.tree.command(name="createplay", description="Запланировать игру")
@app_commands.choices(region=[
    app_commands.Choice(name="Ukraine (UA)", value="ua"),
    app_commands.Choice(name="Europe (EU)", value="eu")
])
async def createplay(interaction: discord.Interaction, game: str, hour: int, minute: int,
                     region: app_commands.Choice[str]):
    # Расчет времени (твоя логика)
    offset = 2 if region.value == "ua" else 1
    server_hour = (hour - offset) % 24

    data = load_data("play.json")
    data[str(interaction.guild_id)] = {
        "game": game,
        "hour": server_hour,
        "minute": minute,
        "region": region.value
    }
    save_data("play.json", data)

    await interaction.response.send_message(f"🎮 Игра **{game}** создана на {hour:02d}:{minute:02d} ({region.name})")


@bot.tree.command(name="tictactoe", description="Начать крестики-нолики")
async def tictactoe(interaction: discord.Interaction):
    game = TicTacToe()
    active_games[interaction.channel_id] = game
    board_str = f"```\n{game.board[0]} | {game.board[1]} | {game.board[2]}\n--+---+--\n{game.board[3]} | {game.board[4]} | {game.board[5]}\n--+---+--\n{game.board[6]} | {game.board[7]} | {game.board[8]}\n```"
    await interaction.response.send_message(f"Игра началась! Ход X. Напиши число от 1 до 9.\n{board_str}")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot: return

    # Логика игры (если в канале идет игра)
    if message.channel.id in active_games:
        game = active_games[message.channel.id]
        if message.content.isdigit() and 1 <= int(message.content) <= 9:
            idx = int(message.content) - 1
            if game.board[idx] not in ["X", "O"]:
                game.board[idx] = game.turn
                if game.check_winner():
                    res = f"Победил {game.winner}!" if game.winner != "Draw" else "Ничья!"
                    await message.channel.send(res)
                    del active_games[message.channel.id]
                else:
                    game.turn = "O" if game.turn == "X" else "X"
                    # Вывод доски (как в твоем коде)
                    board_str = f"```\n{game.board[0]} | {game.board[1]} | {game.board[2]}\n--+---+--\n{game.board[3]} | {game.board[4]} | {game.board[5]}\n--+---+--\n{game.board[6]} | {game.board[7]} | {game.board[8]}\n```"
                    await message.channel.send(f"Ход {game.turn}:\n{board_str}")

    # Статистика сообщений (вместо stat.py)
    stats = load_data("stats.json")
    user_id = str(message.author.id)
    stats[user_id] = stats.get(user_id, 0) + 1
    save_data("stats.json", stats)

    await bot.process_commands(message)


# --- ФОНОВЫЕ ЗАДАЧИ ---
@tasks.loop(seconds=60)
async def check_games():
    now = datetime.datetime.now()
    data = load_data("play.json")
    for guild_id, info in list(data.items()):
        if now.hour == info['hour'] and now.minute == info['minute']:
            channel = bot.get_channel(936726172828577855)  # Твой ID канала
            if channel:
                await channel.send(f"@everyone, пора играть в {info['game']}!")
                del data[guild_id]
                save_data("play.json", data)


@bot.event
async def on_ready():
    # ПОДСТАВЬ СВОЙ ID ТУТ:
    MY_GUILD_ID = 936726172828577853  # Пример
    guild = discord.Object(id=MY_GUILD_ID)

    # Копируем команды именно на этот сервер
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)

    print(f'--- Бот {bot.user} запущен! ---')
    print(f'Команды принудительно обновлены на сервере: {MY_GUILD_ID}')


# Запуск
bot.run(TOKEN)