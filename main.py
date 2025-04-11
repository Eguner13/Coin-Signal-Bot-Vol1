import requests
import logging
import time
import asyncio
from binance import AsyncClient
from telegram import Bot

# Telegram yapılandırması
TELEGRAM_TOKEN = "7962272013:AAF-8vRKukZtktCyDiyP-qZr8cPHMtFpiF0"
TELEGRAM_CHAT_ID = "6205477705"

# Sinyal eşikleri
LONG_RSI_THRESHOLD = 45
SHORT_RSI_THRESHOLD = 55
VOLUME_CHANGE_THRESHOLD = 2

# İzlenen coinler
symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT"]
logging.basicConfig(level=logging.INFO)


def calculate_rsi(prices, period=14):
    gains, losses = [], []
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i - 1]
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(prices)):
        delta = prices[i] - prices[i - 1]
        gain = max(delta, 0)
        loss = abs(min(delta, 0))

        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_macd(prices, short_period=12, long_period=26, signal_period=9):
    def ema(data, period):
        k = 2 / (period + 1)
        ema_vals = [sum(data[:period]) / period]
        for price in data[period:]:
            ema_vals.append(price * k + ema_vals[-1] * (1 - k))
        return ema_vals

    short_ema = ema(prices, short_period)
    long_ema = ema(prices, long_period)
    macd_line = [s - l for s, l in zip(short_ema[-len(long_ema):], long_ema)]
    signal_line = ema(macd_line, signal_period)

    return macd_line[-1] - signal_line[-1]


async def fetch_ohlcv(client, symbol, interval="1h", limit=100):
    try:
        klines = await client.get_klines(symbol=symbol, interval=interval, limit=limit)
        closes = [float(k[4]) for k in klines]
        volumes = [float(k[5]) for k in klines]
        return closes, volumes
    except Exception as e:
        logging.error(f"{symbol} verileri alınamadı: {e}")
        return None, None


async def analyze_symbol(client, bot, symbol):
    try:
        closes, volumes = await fetch_ohlcv(client, symbol)
        if not closes or not volumes:
            return

        rsi = calculate_rsi(closes)
        macd = calculate_macd(closes)
        volume_change = ((volumes[-1] - volumes[-2]) / volumes[-2]) * 100

        direction = "WAIT"
        if rsi < LONG_RSI_THRESHOLD and macd > 0 and volume_change > VOLUME_CHANGE_THRESHOLD:
            direction = "LONG"
        elif rsi > SHORT_RSI_THRESHOLD and macd < 0 and volume_change < -VOLUME_CHANGE_THRESHOLD:
            direction = "SHORT"

        if direction == "WAIT":
            logging.info(f"{symbol}: WAIT")
            return

        leverage = "10x"
        price = closes[-1]
        tp = round(price * (1.015 if direction == "LONG" else 0.985), 2)
        sl = round(price * (0.985 if direction == "LONG" else 1.015), 2)

        message = (
            f"{symbol} | Yön: {direction} | Kaldıraç: {leverage}\n"
            f"Fiyat: {price}\nTP: {tp} | SL: {sl}"
        )
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        logging.error(f"{symbol} analiz hatası: {e}")


async def main_loop():
    client = await AsyncClient.create()
    bot = Bot(token=TELEGRAM_TOKEN)

    logging.info("Bot başlatıldı.")
    try:
        while True:
            logging.info("Yeni analiz döngüsü başlatılıyor...")
            await asyncio.gather(*(analyze_symbol(client, bot, symbol) for symbol in symbols))
            await asyncio.sleep(3600)  # 1 saat bekle
    except Exception as e:
        logging.error(f"Ana döngü hatası: {e}")
    finally:
        await client.close_connection()


if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logging.info("Bot kullanıcı tarafından durduruldu.")
    except Exception as e:
        logging.error(f"Genel hata: {e}")
