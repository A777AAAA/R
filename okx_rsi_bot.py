import os
import logging
from datetime import datetime
from typing import Dict, List, Tuple
from dotenv import load_dotenv
import ccxt
import pandas as pd
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# Загрузка переменных окружения
load_dotenv()

# Конфигурация
TELEGRAM_TOKEN = os.getenv("7713878854:AAFEDuZNkxKyzRIzuIHzootvoChkqS6_t7E")
OKX_API_KEY = os.getenv("6a4d18db-08e7-4352-b897-3a9fa2abe80e", "")
OKX_SECRET = os.getenv("78290AEF605ADB6EF8D8F601387B4AE8", "")
OKX_PASSPHRASE = os.getenv("Art23031987!", "")

# Настройка логгирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
SELECT_PAIR, SELECT_TIMEFRAME, SELECT_RSI_LEVELS, CONFIRM_ALERT = range(4)

# Инициализация OKX API
exchange = ccxt.okx(
    {
        "apiKey": OKX_API_KEY,
        "secret": OKX_SECRET,
        "password": OKX_PASSPHRASE,
        "enableRateLimit": True,
    }
)

# База данных (в реальном проекте используйте PostgreSQL или другую СУБД)
user_alerts = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}!\n\n"
        "Я бот для мониторинга RSI на фьючерсах OKX.\n"
        "Я могу уведомлять вас, когда RSI достигает определенных уровней.\n\n"
        "Доступные команды:\n"
        "/add_alert - добавить новое оповещение\n"
        "/my_alerts - просмотреть текущие оповещения\n"
        "/remove_alert - удалить оповещение"
    )


async def add_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинаем процесс добавления оповещения"""
    # Получаем список доступных фьючерсов
    markets = exchange.load_markets()
    futures_pairs = [
        symbol for symbol in markets if markets[symbol]["future"] and "USDT" in symbol
    ]

    # Создаем клавиатуру с парами
    keyboard = [
        [InlineKeyboardButton(pair, callback_data=f"pair_{pair}")]
        for pair in futures_pairs[:50]  # Ограничиваем для удобства
    ]
    keyboard.append([InlineKeyboardButton("Отмена", callback_data="cancel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Выберите торговую пару:", reply_markup=reply_markup
    )

    return SELECT_PAIR


async def select_pair(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора торговой пары"""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text(text="Отменено.")
        return ConversationHandler.END

    # Сохраняем выбранную пару
    pair = query.data.replace("pair_", "")
    context.user_data["selected_pair"] = pair

    # Предлагаем выбрать таймфрейм
    timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
    keyboard = [
        [InlineKeyboardButton(tf, callback_data=f"timeframe_{tf}") for tf in timeframes]
    ]
    keyboard.append([InlineKeyboardButton("Отмена", callback_data="cancel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text=f"Выбрана пара: {pair}\n\nВыберите таймфрейм:",
        reply_markup=reply_markup,
    )

    return SELECT_TIMEFRAME


async def select_timeframe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора таймфрейма"""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text(text="Отменено.")
        return ConversationHandler.END

    # Сохраняем выбранный таймфрейм
    timeframe = query.data.replace("timeframe_", "")
    context.user_data["selected_timeframe"] = timeframe

    # Запрашиваем уровни RSI
    await query.edit_message_text(
        text=(
            f"Пара: {context.user_data['selected_pair']}\n"
            f"Таймфрейм: {timeframe}\n\n"
            "Введите уровни RSI для оповещения через запятую (например: 30,70):"
        )
    )

    return SELECT_RSI_LEVELS


async def select_rsi_levels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода уровней RSI"""
    try:
        levels = [float(level.strip()) for level in update.message.text.split(",")]
        if not all(0 <= level <= 100 for level in levels):
            raise ValueError("Уровни должны быть между 0 и 100")

        context.user_data["rsi_levels"] = levels

        # Подтверждение
        pair = context.user_data["selected_pair"]
        timeframe = context.user_data["selected_timeframe"]
        levels_str = ", ".join(map(str, levels))

        keyboard = [
            [
                InlineKeyboardButton("Подтвердить", callback_data="confirm"),
                InlineKeyboardButton("Отменить", callback_data="cancel"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            text=(
                f"Подтвердите настройки оповещения:\n\n"
                f"Пара: {pair}\n"
                f"Таймфрейм: {timeframe}\n"
                f"Уровни RSI: {levels_str}\n\n"
                "Подтвердить?"
            ),
            reply_markup=reply_markup,
        )

        return CONFIRM_ALERT

    except Exception as e:
        await update.message.reply_text(
            f"Ошибка: {str(e)}\nПожалуйста, введите уровни RSI через запятую (например: 30,70):"
        )
        return SELECT_RSI_LEVELS


async def confirm_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение и сохранение оповещения"""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text(text="Отменено.")
        return ConversationHandler.END

    user_id = update.effective_user.id
    pair = context.user_data["selected_pair"]
    timeframe = context.user_data["selected_timeframe"]
    levels = context.user_data["rsi_levels"]

    # Создаем уникальный ID для оповещения
    alert_id = f"{user_id}_{pair}_{timeframe}_{'_'.join(map(str, levels))}"

    # Сохраняем оповещение
    if user_id not in user_alerts:
        user_alerts[user_id] = {}

    user_alerts[user_id][alert_id] = {
        "pair": pair,
        "timeframe": timeframe,
        "levels": levels,
        "last_notification": {level: None for level in levels},
    }

    await query.edit_message_text(
        text="Оповещение успешно добавлено!\n\n"
        f"Пара: {pair}\n"
        f"Таймфрейм: {timeframe}\n"
        f"Уровни RSI: {', '.join(map(str, levels))}"
    )

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена текущей операции"""
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END


async def my_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать текущие оповещения пользователя"""
    user_id = update.effective_user.id
    if user_id not in user_alerts or not user_alerts[user_id]:
        await update.message.reply_text("У вас нет активных оповещений.")
        return

    message = "Ваши активные оповещения:\n\n"
    for alert_id, alert in user_alerts[user_id].items():
        message += (
            f"🔹 Пара: {alert['pair']}\n"
            f"   Таймфрейм: {alert['timeframe']}\n"
            f"   Уровни RSI: {', '.join(map(str, alert['levels']))}\n\n"
        )

    await update.message.reply_text(message)


async def remove_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удаление оповещения"""
    user_id = update.effective_user.id
    if user_id not in user_alerts or not user_alerts[user_id]:
        await update.message.reply_text("У вас нет активных оповещений для удаления.")
        return

    keyboard = [
        [InlineKeyboardButton(
            f"{alert['pair']} {alert['timeframe']} {alert['levels']}",
            callback_data=f"remove_{alert_id}",
        )]
        for alert_id, alert in user_alerts[user_id].items()
    ]
    keyboard.append([InlineKeyboardButton("Отмена", callback_data="cancel_remove")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Выберите оповещение для удаления:", reply_markup=reply_markup
    )


async def confirm_remove_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Подтверждение удаления оповещения"""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_remove":
        await query.edit_message_text(text="Отменено.")
        return

    user_id = update.effective_user.id
    alert_id = query.data.replace("remove_", "")

    if user_id in user_alerts and alert_id in user_alerts[user_id]:
        del user_alerts[user_id][alert_id]
        await query.edit_message_text(text="Оповещение успешно удалено!")
    else:
        await query.edit_message_text(text="Оповещение не найдено.")


def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """Вычисление RSI"""
    if len(prices) < period + 1:
        return 50  # Возвращаем нейтральное значение, если данных недостаточно

    deltas = pd.Series(prices).diff()
    gains = deltas.where(deltas > 0, 0)
    losses = -deltas.where(deltas < 0, 0)

    avg_gain = gains.rolling(window=period).mean().iloc[-1]
    avg_loss = losses.rolling(window=period).mean().iloc[-1]

    if avg_loss == 0:
        return 100 if avg_gain != 0 else 50

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


async def check_rsi_alerts(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Периодическая проверка RSI и отправка уведомлений"""
    for user_id, alerts in user_alerts.items():
        for alert_id, alert in alerts.items():
            try:
                # Получаем данные свечей
                candles = exchange.fetch_ohlcv(
                    alert["pair"], alert["timeframe"], limit=30
                )
                closes = [candle[4] for candle in candles]

                # Вычисляем RSI
                rsi = calculate_rsi(closes)

                # Проверяем уровни
                for level in alert["levels"]:
                    # Проверяем, пересек ли RSI уровень
                    if (
                        alert["last_notification"][level] is not None
                        and ((alert["last_notification"][level] < level and rsi >= level)
                        or (alert["last_notification"][level] > level and rsi <= level))
                    ):
                        # Отправляем уведомление
                        message = (
                            f"🚨 RSI ALERT 🚨\n\n"
                            f"Пара: {alert['pair']}\n"
                            f"Таймфрейм: {alert['timeframe']}\n"
                            f"Текущий RSI: {rsi:.2f}\n"
                            f"Уровень: {level}"
                        )
                        await context.bot.send_message(chat_id=user_id, text=message)

                    # Обновляем последнее известное значение RSI
                    alert["last_notification"][level] = rsi

            except Exception as e:
                logger.error(f"Ошибка при проверке RSI для {alert_id}: {str(e)}")


def main() -> None:
    """Запуск бота"""
    # Создаем Application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("my_alerts", my_alerts))
    application.add_handler(CommandHandler("remove_alert", remove_alert))

    # Обработчик для добавления оповещений
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add_alert", add_alert)],
        states={
            SELECT_PAIR: [CallbackQueryHandler(select_pair)],
            SELECT_TIMEFRAME: [CallbackQueryHandler(select_timeframe)],
            SELECT_RSI_LEVELS: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_rsi_levels)],
            CONFIRM_ALERT: [CallbackQueryHandler(confirm_alert)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(conv_handler)

    # Обработчик для удаления оповещений
    application.add_handler(
        CallbackQueryHandler(confirm_remove_alert, pattern="^remove_")
    )
    application.add_handler(
        CallbackQueryHandler(cancel, pattern="^cancel_remove$")
    )

    # Запускаем периодическую проверку RSI
    job_queue = application.job_queue
    job_queue.run_repeating(check_rsi_alerts, interval=60.0, first=10.0)

    # Запускаем бота
    application.run_polling()


if __name__ == "__main__":
    main()
