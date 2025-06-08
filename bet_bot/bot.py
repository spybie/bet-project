import logging
import sqlite3
import re
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import os
from dotenv import load_dotenv

from bet_bot.apl_stats import apl_team_stats, apl_h2h_stats


load_dotenv()
logging.basicConfig(level=logging.INFO)
API_TOKEN = os.getenv('API_TOKEN')
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def get_bet_type_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/history"),  KeyboardButton(text="/teamstats"), KeyboardButton(text="/bet")]
        ],
        resize_keyboard=True
    )

def get_cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )


def init_db():
    with sqlite3.connect('bet_history.db') as conn:
        conn.execute('''
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bet_type TEXT NOT NULL,
            odds REAL NOT NULL,
            stats TEXT NOT NULL,
            quality INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')

def add_bet(user_id: int, bet_type: str, odds: float, stats: str, quality: int):
    with sqlite3.connect('bet_history.db') as conn:
        conn.execute('''
        INSERT INTO bets (user_id, bet_type, odds, stats, quality, timestamp)
        VALUES (?, ?, ?, ?, ?, datetime('now', '+3 hours'))
        ''', (user_id, bet_type, odds, stats, quality))

def get_last_bets(user_id: int, limit: int = 5):
    with sqlite3.connect('bet_history.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT bet_type, odds, stats, quality, 
               strftime('%d.%m.%Y %H:%M', timestamp) as formatted_time
        FROM bets 
        WHERE user_id = ? 
        ORDER BY timestamp DESC 
        LIMIT ?
        ''', (user_id, limit))
        return cursor.fetchall()

init_db()

class BetForm(StatesGroup):
    bet_type = State()
    odds = State()
    statistics = State()


@dp.message(Command("teamstats"))
async def cmd_teamstats(message: Message):
    team_names = sorted(apl_team_stats.keys())
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=name)] for name in team_names] + [[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer("Choose a team to see EPL 2024/25 stats:", reply_markup=keyboard)

@dp.message(lambda m: m.text in apl_team_stats)
async def show_team_stats(message: Message):
    stats = apl_team_stats[message.text]
    text = (
        f"🏟 Stats for {message.text} (EPL 2024/25)\n"
        f"------------------------------\n"
        f"🔹 Win percentage: {stats['win_percentage']}%\n"
        f"🔹 Avg goals scored per match: {stats['avg_goals_scored']}\n"
        f"🔹 Avg goals conceded per match: {stats['avg_goals_conceded']}\n"
        f"🔹 Top scorer: {stats['top_scorer']}\n"
        f"------------------------------\n"
        f"ℹ️ Use /teamstats for another team."
    )
    await message.answer(text, reply_markup=get_bet_type_keyboard())



class BetMatchForm(StatesGroup):
    match = State()
    bet_type = State()
    odds = State()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я бот для анализа ставок на АПЛ.\n"
        "Используйте /bet — анализ ставки по матчу\n"
        "Используйте /teamstats — статистика по команде\n"
        "Используйте /history — история ваших ставок\n"
    )

@dp.message(Command("bet"))
async def cmd_bet(message: Message, state: FSMContext):
    team_names = sorted(apl_team_stats.keys())
    await state.clear()
    await message.answer(
        "Введите матч в формате: <Команда1>-<Команда2>\n\n"
        "Например: Arsenal-Chelsea\n"
        "Доступные команды: " + ", ".join(team_names),
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(BetMatchForm.match)

@dp.message(BetMatchForm.match)
async def process_bet_match(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=get_bet_type_keyboard())
        return
    try:
        teams = message.text.replace('—', '-').split('-')
        if len(teams) != 2:
            raise ValueError
        team1 = teams[0].strip()
        team2 = teams[1].strip()
        if team1 not in apl_team_stats or team2 not in apl_team_stats:
            raise ValueError
        await state.update_data(team1=team1, team2=team2)
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="П1"), KeyboardButton(text="П2"), KeyboardButton(text="Ничья")],
                [KeyboardButton(text="ТБ 2.5"), KeyboardButton(text="ТМ 2.5")],
                [KeyboardButton(text="Отмена")]
            ],
            resize_keyboard=True
        )
        await message.answer("Выберите тип ставки: П1, П2, Ничья, ТБ 2.5, ТМ 2.5", reply_markup=keyboard)
        await state.set_state(BetMatchForm.bet_type)
    except Exception:
        await message.answer("Некорректный ввод. Формат: Команда1-Команда2. Попробуйте снова или нажмите Отмена.", reply_markup=get_cancel_keyboard())

@dp.message(BetMatchForm.bet_type)
async def process_bet_match_type(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=get_bet_type_keyboard())
        return
    bet_type = message.text.strip().upper()
    valid_types = ["П1", "П2", "НИЧЬЯ", "ТБ 2.5", "ТМ 2.5"]
    if bet_type not in valid_types:
        await message.answer("Выберите тип ставки из предложенных кнопок.", reply_markup=get_cancel_keyboard())
        return
    await state.update_data(bet_type=bet_type)
    await message.answer("Введите коэффициент (например, 2.5):", reply_markup=get_cancel_keyboard())
    await state.set_state(BetMatchForm.odds)

@dp.message(BetMatchForm.odds)
async def process_bet_match_odds(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=get_bet_type_keyboard())
        return
    try:
        odds = float(message.text.strip())
        if odds <= 1:
            raise ValueError
    except ValueError:
        await message.answer("Коэффициент должен быть положительным числом больше 1. Попробуйте еще раз.", reply_markup=get_cancel_keyboard())
        return

    data = await state.get_data()
    team1, team2 = data["team1"], data["team2"]
    bet_type = data["bet_type"]
    user_id = message.from_user.id

    h2h_key = f"{team1}-{team2}"
    h2h_key_rev = f"{team2}-{team1}"
    team1_stats = apl_team_stats[team1]
    team2_stats = apl_team_stats[team2]
    h2h = apl_h2h_stats.get(h2h_key) or {
        "team1_win_percentage": 50.0,
        "draw_percentage": 30.0
    }
    if not apl_h2h_stats.get(h2h_key) and apl_h2h_stats.get(h2h_key_rev):
        h2h = apl_h2h_stats[h2h_key_rev]
        h2h = {
            "team1_win_percentage": 100 - h2h.get("team1_win_percentage", 50.0) - h2h.get("draw_percentage", 30.0),
            "draw_percentage": h2h.get("draw_percentage", 30.0)
        }

    if bet_type == "П1":
        win_team = team1_stats["win_percentage"]
        win_opponent = team2_stats["win_percentage"]
        head_to_head_win = h2h["team1_win_percentage"]
        head_to_head_draw = h2h["draw_percentage"]
        quality = calculate_outcome_quality(odds, win_team, win_opponent, head_to_head_win, head_to_head_draw)
        stats_str = f"П1: {team1} vs {team2} ({win_team}%/{win_opponent}%), H2H: {head_to_head_win}% побед, {head_to_head_draw}% ничьих"
    elif bet_type == "П2":
        win_team = team2_stats["win_percentage"]
        win_opponent = team1_stats["win_percentage"]
        h2h_swapped = apl_h2h_stats.get(f"{team2}-{team1}")
        if h2h_swapped:
            head_to_head_win = h2h_swapped["team1_win_percentage"]
            head_to_head_draw = h2h_swapped["draw_percentage"]
        else:
            head_to_head_win = 100 - h2h["team1_win_percentage"] - h2h["draw_percentage"]
            head_to_head_draw = h2h["draw_percentage"]
        quality = calculate_outcome_quality(odds, win_team, win_opponent, head_to_head_win, head_to_head_draw)
        stats_str = f"П2: {team2} vs {team1} ({win_team}%/{win_opponent}%), H2H: {head_to_head_win}% побед, {head_to_head_draw}% ничьих"
    elif bet_type == "НИЧЬЯ":
        win_team = team1_stats["win_percentage"]
        win_opponent = team2_stats["win_percentage"]
        draw_perc = h2h["draw_percentage"]
        quality = calculate_draw_quality(odds, win_team, win_opponent, draw_perc)
        stats_str = f"Ничья: {team1} vs {team2} ({win_team}%/{win_opponent}%), H2H ничьи: {draw_perc}%"
    elif bet_type in ["ТБ 2.5", "ТМ 2.5"]:
        avg_goals_team = team1_stats["avg_goals_scored"]
        avg_goals_opponent = team2_stats["avg_goals_scored"]
        total_value = 2.5
        total_type = "больше" if "ТБ" in bet_type else "меньше"
        quality = calculate_total_quality(odds, avg_goals_team, avg_goals_opponent, total_value, total_type)
        stats_str = f"{bet_type}: {team1}({avg_goals_team}) vs {team2}({avg_goals_opponent}), тотал {total_type} {total_value}"
    else:
        await message.answer("Неизвестный тип ставки.", reply_markup=get_bet_type_keyboard())
        await state.clear()
        return

    response = (
        f"🎯 Ставка: {bet_type} на матч {team1} - {team2}\n"
        f"📊 Коэффициент: {odds}\n"
        f"📈 Статистика: {stats_str}\n"
        f"⭐ Качество ставки: {quality}/10"
    )
    add_bet(user_id, bet_type, odds, stats_str, quality)
    await message.answer(response, reply_markup=get_bet_type_keyboard())
    await state.clear()


@dp.message(Command("history"))
async def cmd_history(message: Message):
    bets = get_last_bets(message.from_user.id)
    if not bets:
        await message.answer("История ставок пуста.", reply_markup=get_bet_type_keyboard())
        return
    response = "📊 Ваши последние ставки:\n\n"
    for bet in bets:
        match = "-"
        match_search = re.search(r"(?:на матч\s*)?([A-Za-zА-Яа-яёЁ\s\-]+)[\-–—]\s*([A-Za-zА-Яа-яёЁ\s\-]+)", bet[2])
        if not match_search:
            match_search = re.search(r"([A-Za-zА-Яа-яёЁ\s\-]+)\s+vs\.?\s+([A-Za-zА-Яа-яёЁ\s\-]+)", bet[2], re.IGNORECASE)
        if match_search:
            match = f"{match_search.group(1).strip()} - {match_search.group(2).strip()}"
        else:
            # fallback: часть stats до первой запятой
            match = bet[2].split(",")[0].replace("П1:", "").replace("П2:", "").replace("Ничья:", "").strip()
        response += (
            f"▸ {bet[0]}\n"
            f"Матч: {match}\n"
            f"Коэффициент: {bet[1]}\n"
            f"Оценка: {bet[3]}/10\n"
            f"Дата: {bet[4]}\n\n"
        )
    await message.answer(response, reply_markup=get_bet_type_keyboard())

@dp.message(BetForm.bet_type)
async def process_bet_type(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=get_bet_type_keyboard())
        return
    bet_type = message.text.strip()
    if bet_type not in ["Победа команды", "Ничья", "Тотал больше", "Тотал меньше"]:
        await message.answer("Пожалуйста, выберите тип ставки из предложенных кнопок.")
        return
    await state.update_data(bet_type=bet_type)
    await message.answer(
        "Введите коэффициент ставки (например, 2.5):",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(BetForm.odds)

@dp.message(BetForm.odds)
async def process_odds(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=get_bet_type_keyboard())
        return
    try:
        odds = float(message.text.strip())
        if odds <= 1:
            raise ValueError
    except ValueError:
        await message.answer("Коэффициент должен быть положительным числом большим 1. Попробуйте еще раз.")
        return

    await state.update_data(odds=odds)
    data = await state.get_data()
    bet_type = data["bet_type"]

    if bet_type == "Победа команды":
        await message.answer(
            "Введите статистику в формате:\n"
            "<Процент побед вашей команды> <Процент побед соперника> "
            "<Процент побед в очных встречах> <Процент ничьих в очных встречах>\n"
            "Пример: 60 40 50 20",
            reply_markup=get_cancel_keyboard()
        )
    elif bet_type == "Ничья":
        await message.answer(
            "Введите статистику в формате:\n"
            "<Процент побед вашей команды> <Процент побед соперника> "
            "<Процент ничьих в очных встречах>\n"
            "Пример: 60 40 50",
            reply_markup=get_cancel_keyboard()
        )
    else:  # Тоталы
        await message.answer(
            "Введите статистику в формате:\n"
            "<Среднее кол-во вашей команды> <Среднее кол-во соперника> <Значение тотала>\n"
            "Пример: 1.6 2.4 2.5",
            reply_markup=get_cancel_keyboard()
        )
    await state.set_state(BetForm.statistics)

@dp.message(BetForm.statistics)
async def process_statistics(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=get_bet_type_keyboard())
        return
    data = await state.get_data()
    bet_type = data["bet_type"]
    odds = data["odds"]
    user_id = message.from_user.id
    try:
        if bet_type == "Победа команды":
            stats = list(map(float, message.text.strip().split()))
            if len(stats) != 4:
                raise ValueError("Нужно ввести 4 числа")
            win_team, win_opponent, head_to_head_win, head_to_head_draw = stats
            if not all(0 <= x <= 100 for x in stats):
                raise ValueError("Все значения должны быть в диапазоне 0-100")
            if (head_to_head_win + head_to_head_draw) > 100:
                raise ValueError("Сумма процентов побед и ничьих должна быть ≤ 100")
            quality = calculate_outcome_quality(odds, win_team, win_opponent, head_to_head_win, head_to_head_draw)
            stats_str = f"Победы: {win_team}%/{win_opponent}%, Очные: {head_to_head_win}%/{head_to_head_draw}%"
            response = (
                f"🎯 Ставка: {bet_type}\n"
                f"📊 Коэффициент: {odds}\n"
                f"📈 Статистика: {stats_str}\n"
                f"⭐ Качество ставки: {quality}/10"
            )
        elif bet_type == "Ничья":
            stats = list(map(float, message.text.strip().split()))
            if len(stats) != 3:
                raise ValueError("Нужно ввести 3 числа")
            win_team, win_opponent, head_to_head_draw = stats
            if not all(0 <= x <= 100 for x in stats):
                raise ValueError("Все значения должны быть в диапазоне 0-100")
            quality = calculate_draw_quality(odds, win_team, win_opponent, head_to_head_draw)
            stats_str = f"Победы: {win_team}%/{win_opponent}%, Ничьи: {head_to_head_draw}%"
            response = (
                f"🎯 Ставка: {bet_type}\n"
                f"📊 Коэффициент: {odds}\n"
                f"📈 Статистика: {stats_str}\n"
                f"⭐ Качество ставки: {quality}/10"
            )
        else:  # Тоталы
            stats = list(map(float, message.text.strip().split()))
            if len(stats) != 3:
                raise ValueError("Нужно ввести 3 числа")
            avg_goals_team, avg_goals_opponent, total_value = stats
            if avg_goals_team < 0 or avg_goals_opponent < 0:
                raise ValueError("Средние голы должны быть ≥ 0")
            if (total_value * 10) % 5 != 0:
                raise ValueError("Тотал должен быть вида X.5 (например, 2.5)")
            total_type = "больше" if "больше" in bet_type.lower() else "меньше"
            quality = calculate_total_quality(odds, avg_goals_team, avg_goals_opponent, total_value, total_type)
            stats_str = f"Голы: {avg_goals_team}/{avg_goals_opponent}, Тотал: {total_type} {total_value}"
            response = (
                f"🎯 Ставка: {bet_type}\n"
                f"📊 Коэффициент: {odds}\n"
                f"📈 Статистика: {stats_str}\n"
                f"⭐ Качество ставки: {quality}/10"
            )
        add_bet(user_id, bet_type, odds, stats_str, quality)
        await message.answer(response, reply_markup=get_bet_type_keyboard())
        await state.clear()
    except ValueError as e:
        await message.answer(f"❌ Ошибка: {str(e)}\nПопробуйте ввести данные еще раз.", reply_markup=get_cancel_keyboard())

# --- Функции расчета качества ставки ---
def calculate_outcome_quality(odds, win_team, win_opponent, head_to_head_win, head_to_head_draw):
    stat_adv = (win_team - win_opponent) / 100  
    h2h_score = (head_to_head_win * 0.6 + head_to_head_draw * 0.4) / 100  
    stat_prob = max(0, min(1, 0.5 * (win_team / 100) + 0.5 * h2h_score))  
    implied_prob = 1 / odds if odds > 0 else 0
    value = stat_prob - implied_prob  
    raw_score = (stat_adv * 0.2 + h2h_score * 0.2 + value * 0.6) * 10 + 5  
    normalized_quality = int(round(max(1, min(10, raw_score))))
    return normalized_quality

def calculate_draw_quality(odds, win_team, win_opponent, head_to_head_draw):
    base_draw_probability = 50 - abs(win_team - win_opponent) * 0.5
    head_to_head_factor = head_to_head_draw
    odds_factor = 1 + (odds - 1) / 5
    raw_score = (base_draw_probability * 0.6 + head_to_head_factor * 0.4) * odds_factor
    normalized_quality = max(1, min(10, int(5 + raw_score / 20)))
    return normalized_quality

def calculate_total_quality(odds, avg_goals_team, avg_goals_opponent, total_value, total_type):
    if (total_value * 10 % 5 != 0) or total_value < 0:
        raise ValueError("Значение тотала должно быть вида x.5, где x не отрицательный, например 2.5, 3.5 и т.д.")
    avg_goals = (avg_goals_team + avg_goals_opponent) / 2
    implied_probability = 1 / odds if odds > 0 else 0

    if total_type.lower() == "больше":
        goal_gap = avg_goals - total_value
    elif total_type.lower() == "меньше":
        goal_gap = total_value - avg_goals
    else:
        raise ValueError("Неверный тип тотала")

    probability_factor = 0.5 + (goal_gap * 0.2)
    probability_factor = max(0, min(1, probability_factor))

    value = probability_factor - implied_probability

    odds_impact = odds ** 0.7  

    quality = 5 + 4 * value + 2 * (odds_impact - 1) + 1 * (probability_factor - 0.5)
    quality = int(round(max(1, min(10, quality))))
    return quality

async def async_main():
    await dp.start_polling(bot)

def main():
    import asyncio
    asyncio.run(async_main())

if __name__ == "__main__":
    main()