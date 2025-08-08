from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from tinkoff.invest import AsyncClient, PortfolioPosition, InstrumentIdType
from tinkoff.invest.constants import INVEST_GRPC_API
from tinkoff.invest.schemas import InstrumentExchangeType
from tinkoff.invest.utils import now
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

import traceback
import os

TINKOFF_TOKEN = "t.gTlvYidRfnqsyM3mhVApSvnklIkhrqjRvFZKzUWldCLTT9kvimBGQLU_XURlB4pzhwTIvPq5-NfxDNuV1dA-Fw"
TELEGRAM_BOT_TOKEN = "8028781115:AAEJOCq5clBK3Nw9xb6g7KEPTvSf5h6CKUM"

bot = Bot(TELEGRAM_BOT_TOKEN)
dp = Dispatcher(bot=bot)

class Form(StatesGroup):
    waiting_for_ticker = State()

async def CountRealIncome(coupon, period, nominal, price, coupons_per_year):
    total_coupons = coupon * period
    total_return = total_coupons + nominal - price
    total_yield = (total_return / price) * 100  


    years = period / coupons_per_year
    annual_yield = total_yield / years

    return {
        "total_yield" : total_yield,
        "annual_yield" : annual_yield, 
        "years" : years
    }

async def GetCurrentPrice(ticker: str):
    bond_info = await GetInfoBySecurity(ticker=ticker)
    figi = bond_info["figi"]
    async with AsyncClient(TINKOFF_TOKEN) as client:
        info_last_price = await client.market_data.get_last_prices(figi=[figi])
        last_prices = info_last_price.last_prices
        last_price = last_prices[0]
        units = last_price.price.units
        nano = last_price.price.nano
        current_price = str(units) + str(nano/100000000)
        return float(current_price)

async def GetCouponByBond(ticker: str):
    bond_info = await GetInfoBySecurity(ticker=ticker)
    figi = bond_info["figi"]
    now_time = now()
    async with AsyncClient(TINKOFF_TOKEN) as client:
        instrument = await client.instruments.bond_by(id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, id=figi)
        
        date_from = instrument.instrument.placement_date 
        date_to = instrument.instrument.maturity_date
        coupons = await client.instruments.get_bond_coupons(figi=figi, from_=date_from, to=date_to)

        count_counpons = 0

        for coupon in coupons.events:
            if coupon.coupon_date > now_time:
                count_counpons +=1
            coupon_units = coupon.pay_one_bond.units
            coupon_nano = coupon.pay_one_bond.nano
            coupon_currency = coupon.pay_one_bond.currency
            coupon_period = coupon.coupon_period
        coupon = (coupon_units+(coupon_nano/1000000000))
        return {
            "count_counpons" : count_counpons,
            "coupon" : coupon,
            "coupon_period" : coupon_period, 
            "coupon_currency" : coupon_currency
        }

async def GetInfoBySecurity(ticker: str):
    async with AsyncClient(TINKOFF_TOKEN) as client:
        bonds = await client.instruments.bonds(
            instrument_exchange=InstrumentExchangeType.INSTRUMENT_EXCHANGE_UNSPECIFIED,
        )
        for bond in bonds.instruments:
            if bond.ticker == ticker:
                return {
                    "all" : bond,
                    "name" : bond.name,
                    "coupon_quantity_per_year" : bond.coupon_quantity_per_year,
                    "nominal_units" : bond.nominal.units,
                    "nominal_nano" : bond.nominal.nano,
                    "nominal_currency" : bond.nominal.currency,
                    "figi" : bond.figi
                }

def get_inline_keyboard_after_start():
    markup = InlineKeyboardMarkup()
    btn1 = InlineKeyboardButton("Рассчет доходности по тикеру", callback_data="Income_by_ticker")
    btn2 = InlineKeyboardButton("Рассчет доходности по моим данным", callback_data="Income_by_my_data")
    markup.add(btn1)
    markup.add(btn2)
    return markup
@dp.message_handler(commands=["start"])
async def StartMessage(message: types.Message):
    await message.answer("Привет, нажми на подходящую кнопку ниже\n"
                         "Приносим прощения, бот плохо работает с теми облигациями, которые имеют НЕ фиксированный купон", 
                         reply_markup=get_inline_keyboard_after_start())
@dp.message_handler(state=Form.waiting_for_ticker)
async def GetTicker(message: types.Message, state: FSMContext):
    ticker = message.text.upper().strip()
    try:
        bond_info = await GetInfoBySecurity(ticker=ticker)
        coupon_info = await GetCouponByBond(ticker=ticker)
        name = bond_info["name"]
        nominal = str(bond_info["nominal_units"]) + " " +str(bond_info["nominal_currency"])
        coupon = coupon_info["coupon"]
        count_counpons = coupon_info["count_counpons"]
        coupon_period = coupon_info["coupon_period"]
        coupon_quantity_per_year = bond_info["coupon_quantity_per_year"]
        coupon_currency = coupon_info["coupon_currency"]
        current_price = await GetCurrentPrice(ticker=ticker)
        info_income = await CountRealIncome(coupon, count_counpons, bond_info["nominal_units"], current_price, coupon_quantity_per_year)
        total_income = info_income["total_yield"]
        annual_income= info_income["annual_yield"]
        years = info_income["years"]


        await message.answer(f"Имя: {name}\n"
                             f"Текущая стоимость: {current_price}\n" 
                             f"Номинал: {nominal}\n"
                             f"Купон: {coupon} {coupon_currency}\n"
                             f"Количество оставшихся купонов: {count_counpons}\n"
                             f"Период купона: {coupon_period}\n"
                             f"Купонов в год: {coupon_quantity_per_year}\n"
                             f"\n"
                             f"Реальная доходность за все оставшееся время: {total_income:.2f}% ({years:.1f} лет)\n"
                             f"Реальная годовая доходность за год: {annual_income:.2f}%\n"
                             )
        await state.finish()

    except Exception as e:
        await message.answer("Попробуйте ввести тикер еще раз!")
        print("Ошибка:", e)
        traceback.print_exc()

@dp.callback_query_handler()
async def callback(call: types.CallbackQuery, state: FSMContext):
    if call.data == "Income_by_ticker":
        await call.answer()
        await call.message.answer("Отправь тикер, а я рассчитаю реальную доходность по облигации:")
        await Form.waiting_for_ticker.set()

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)