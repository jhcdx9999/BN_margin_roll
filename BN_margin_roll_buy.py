import ccxt
import time
import schedule
import requests
import math
import logging
from pprint import pprint
from datetime import datetime


logging.basicConfig(
    filename='logfile.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Binance API
API_KEY = ""
SECRET_KEY = ""

# Telegram Bot
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""

# init ccxt Binance
binance = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True,
})

# 全局变量
token_price = None  # token price bought last time


# ======================= utils =======================
# fetch available USDT
def get_available_usdt_in_cross_margin(asset):
    try:
        account_info = binance.sapi_get_margin_account()
        # locate USDT info
        usdt_info = next((_asset for _asset in account_info['userAssets'] if _asset['asset'] == asset), None)
        if usdt_info is None:
            print(f"no {asset} in margin mode")
            return 0.0
        # available amount USDT
        free_usdt = float(usdt_info['free'])
        return free_usdt
    except ccxt.BaseError as e:
        # send_telegram_alert(f"fetch available {asset} balance fail: {e}")
        logging.info(f"fetch available {asset} balance fail: {e}")
        return 0.0


# fetch LOT_SIZE
def get_lot_size_limits(trading_pair):
    try:
        market = binance.load_markets()[trading_pair]
        limits = {
            "minQty": market["limits"]["amount"]["min"],  # min order amount
            "maxQty": market["limits"]["amount"]["max"],  # max order amount
            "stepSize": market["precision"]["amount"],  # precision
            "maxNotional": market["limits"]["cost"]["max"],  # max order limits
        }
        return limits
    except Exception as e:
        print(f"fetch {trading_pair} LOT_SIZE limit fail: {e}")
        return


# adjust LOT_SIZE
def adjust_quantity(trading_pair, quantity):
    limits = get_lot_size_limits(trading_pair)
    if limits is None:
        print(f"fetch {trading_pair} LOT_SIZE limit fail")
        return None

    min_qty = limits['minQty']
    max_qty = limits['maxQty']
    step_size = limits['stepSize']

    # ensure within range
    quantity = max(min_qty, min(max_qty, quantity))

    # adjust amount to stepSize multiple
    adjusted_quantity = math.floor(quantity / step_size) * step_size
    adjusted_quantity = round(adjusted_quantity, int(-math.log10(step_size)))

    print(f"amount before: {quantity}, amount after: {adjusted_quantity}")
    return adjusted_quantity


# cal token amount to buy
def calculate_quantity_to_buy(trading_pair, usdt_amount):
    current_price = get_price(trading_pair)
    if current_price is None:
        print("get current price fail")
        return
    quantity = usdt_amount / current_price
    print(f"with {usdt_amount} USDT and token price {current_price}，can buy {quantity:.8f}")
    return quantity


# fetch max borrow USDT
def get_max_borrowable_amount(asset):
    try:
        result = binance.sapi_get_margin_maxborrowable({'asset': asset})
        max_borrowable = float(result['amount'])
        print(f"{asset} max borrow: {max_borrowable}")
        return max_borrowable
    except ccxt.BaseError as e:
        print(f"fetch max borrow fail: {e}")
        # send_telegram_alert(f"fetch {asset} max borrow fail: {e}")
        logging.info(f"fetch {asset} max borrow fail: {e}")
        return 0.0


def get_margin_risk_level():
    try:
        # fetch margin account generanl info
        margin_account = binance.sapi_get_margin_account()
        #  ML
        margin_level = float(margin_account.get('marginLevel', 0))
        return margin_level
    except ccxt.BaseError as e:
        print(f"fetch info fail: {e}")
        return None


# ===================== execution =====================
# transfer to margin account
def transfer_to_cross_margin(asset, amount, type):
    try:
        result = binance.sapi_post_asset_transfer({
            'type': type,
            'asset': asset,
            'amount': amount,
        })
        print(f"{asset} transfer success: {result}")
        return result
    except ccxt.BaseError as e:
        print(f"{asset} transfer fail: {e}")
        # send_telegram_alert(f"{asset} transfer fail: {e}")
        logging.info(f"{asset} transfer fail: {e}")
        return None


# borrow asset
def borrow_asset(asset, leverage_level):
    try:
        # get margin account general info
        account_info = binance.sapi_get_margin_account()
        asset_info = next((a for a in account_info['userAssets'] if a['asset'] == asset), None)

        if asset_info is None:
            print(f"asset {asset} not in margin mode")
            return None

        # available balance
        free_balance = float(asset_info['free'])
        print(f"margin account {asset} balance available: {free_balance}")

        # cal borrow amount（2x + 1x）
        borrow_amount = free_balance * (leverage_level - 1)  # leverage_level = 3 -> borrow 2x of free_balance

        # borrow
        result = binance.sapi_post_margin_loan({
            'asset': asset,
            'amount': borrow_amount,
        })

        print(f"borrow {borrow_amount} {asset} success: {result}")
        # send_telegram_alert(f"borrow {borrow_amount} {asset} success: {result}")
        logging.info(f"borrow {borrow_amount} {asset} success: {result}")
        return borrow_amount
    except ccxt.BaseError as e:
        print(f"borrow {asset} fail: {e}")
        # send_telegram_alert(f"borrow {asset} fail: {e}")
        logging.info(f"borrow {asset} fail: {e}")
        return None


# margin buy
def margin_buy_target_asset(trading_pair, amount):
    try:
        token_amount = calculate_quantity_to_buy(trading_pair, amount)
        if not token_amount:
            return
        token_amount = adjust_quantity(trading_pair, token_amount)
        # execute margin buy
        order = binance.sapi_post_margin_order({
            'symbol': trading_pair.replace('/', ''),  # 'DOGE/USDT' to 'DOGEUSDT'
            'side': 'BUY',  # buy
            'type': 'MARKET',  # market taker
            'quantity': token_amount,  # buy token amount
            'isIsolated': 'false'  # cross margin mode
        })
        print(f"buy success {trading_pair}: {order}")
        # send_telegram_alert(f"bought {trading_pair}\ntoken amount: {token_amount} {trading_pair.split('/')[0]}\namount:{amount} USDT")
        logging.info(f"bought {trading_pair}\ntoken amount: {token_amount} {trading_pair.split('/')[0]}\namount:{amount} USDT")
        return order
    except ccxt.BaseError as e:
        print(f"buy success {trading_pair} fail: {e}")
        # send_telegram_alert(f"buy success {trading_pair} fail: {e}")
        logging.info(f"buy success {trading_pair} fail: {e}")
        return


# fetch token price
def get_price(trading_pair, n=3):
    i = 0
    try:
        while i < n:
            ticker = binance.fetch_ticker(trading_pair)
            price = ticker['last']
            if not price:
                time.sleep(0.5)
                i += 1
            else:
                return price
    except ccxt.BaseError as e:
        print(f"tried 3 times fetch {trading_pair} price fail: {e}")
        # send_telegram_alert(f"fetch {trading_pair} price fail: {e}")
        logging.info(f"fetch {trading_pair} price fail: {e}")
        return


# send Telegram alarm
def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    params = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
    }
    try:
        response = requests.post(url, params=params)
        if response.status_code == 200:
            print("Telegram alarmed!")
        else:
            print(f"Telegram alarm fail: {response.text}")
    except Exception as e:
        print(f"Telegram alarm fail: {e}")


# monitor token price
def monitor_and_trade(trading_pair, asset, leverage_level, price_increase_threshold):
    global token_price

    # fetch current price
    current_price = get_price(trading_pair)
    if current_price is None:
        return

    # record price
    if token_price is None:
        token_price = current_price
        print(f"init {trading_pair} price: {token_price}")
        return

    # cal price change
    try:
        price_change = (current_price - token_price) / token_price
    except Exception as e:
        print(f'cal price_change error:{e}')
        return

    # if token price
    if price_change >= price_increase_threshold:
        print(f"{datetime.now().strftime('%m-%d %H:%M:%S')} {trading_pair} price increases {price_change * 100:.2f}%, borrow & buy")
        borrow_amount = borrow_asset(asset, leverage_level)
        margin_buy_target_asset(trading_pair, borrow_amount)
        token_price = current_price  # update token price
        ml = get_margin_risk_level()
        # send_telegram_alert(f'{datetime.now().strftime("%m-%d %H:%M:%S")}\nprice increases by: {price_change * 100:.2f}%\nBought {borrow_amount} USDT, price {token_price}\nCurrent ML: {ml:.2f}')
        logging.info(f'{datetime.now().strftime("%m-%d %H:%M:%S")}\nprice increases by: {price_change * 100:.2f}%\nBought {borrow_amount} USDT, price {token_price}\nCurrent ML: {ml:.2f}')


# check risk
def check_liquidation_risk():
    try:
        risk_level = get_margin_risk_level()
        if risk_level < 1.3:  # liquidating value 1.3
            # send_telegram_alert(f"Attention！Current ML: {risk_level}")
            logging.info(f"Attention！Current ML: {risk_level}")
    except ccxt.BaseError as e:
        print(f"Fetch ML failure: {e}")
        # send_telegram_alert(f"Failure reason: {e}")
        logging.info(f"Failure reason: {e}")


# main execution func
def main(asset, amount_to_transfer: float, type, trading_pair, leverage_level, price_increase_threshold):
    # 1. transfer to cross margin
    transfer_to_cross_margin(asset, amount_to_transfer, type)

    # 2. borrow 3x
    borrow_asset(asset, leverage_level)

    # 3. buy token
    amount = get_available_usdt_in_cross_margin('USDT')
    margin_buy_target_asset(trading_pair, amount)
    time.sleep(1)

    # 4. scheduled task
    send_telegram_alert(f'start to monitor>>>')
    schedule.every(1).minutes.do(monitor_and_trade, trading_pair, asset, leverage_level, price_increase_threshold)
    schedule.every(5).minutes.do(check_liquidation_risk)

    # 5. run tasks
    while True:
        schedule.run_pending()
        time.sleep(1)


# fetch total cross margin account value
def get_margin_account_total_value():
    try:
        margin_account = binance.sapi_get_margin_account()

        # fetch total cross margin account value
        total_asset_of_btc = float(margin_account.get('totalAssetOfBtc', 0))
        print(f"margin account value（BTC）：{total_asset_of_btc}")

        # get BTC/USDT price
        btc_ticker = binance.fetch_ticker('BTC/USDT')
        btc_price = btc_ticker['last']
        print(f"BTC/USDT price：{btc_price}")

        # cal USDT value
        total_asset_of_usdt = total_asset_of_btc * btc_price
        print(f"margin account value（USDT）：{total_asset_of_usdt}")

        return total_asset_of_usdt
    except ccxt.BaseError as e:
        print(f"get margin account value fail: {e}")
        return None


if __name__ == "__main__":
    logging.info('program starts...')

    main(
        asset="USDT",
        amount_to_transfer=100,  # transfer USDT amount
        type='MAIN_MARGIN',
        trading_pair="ETH/USDT",  # pair
        leverage_level=3,  # margin level
        price_increase_threshold=0.01  # price increase threshold (1%)
    )
