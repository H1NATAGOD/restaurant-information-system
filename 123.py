import asyncio
import re
import logging
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy import Column, Integer, String, LargeBinary, ForeignKey, select, delete, update


# Настройки
class Settings:
    BOT_TOKEN: str = "8088763245:AAH7tLRsaILTlXnUgGeySCud7LNvmN6T3qo"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:1234@localhost/postgres"


settings = Settings()

# Логирование
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Подключение к БД
engine = create_async_engine(settings.DATABASE_URL, echo=True)
async_session_maker = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()


# Определение моделей

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_user_id = Column(Integer, unique=True, nullable=False)  # Связываем с Telegram ID
    name = Column(String, nullable=True)



    subscribers = relationship("Subscriber", back_populates="user")  # Добавил связь с абонентами


class Subscriber(Base):
    __tablename__ = "subscribers"

    id = Column(Integer, primary_key=True, index=True)
    last_name = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    phone = Column(String, unique=True, nullable=False)
    address = Column(String, nullable=True)
    photo = Column(LargeBinary, nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Теперь обязательно связываем с User

    user = relationship("User", back_populates="subscribers")


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    company_type = Column(String, nullable=False)  # Должно быть в модели
    inn = Column(String, unique=True, nullable=False)


# Функция создания таблиц
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_user(user_id: int, session: AsyncSession):
    result = await session.execute(select(User).where(User.telegram_user_id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(telegram_user_id=user_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user



# Клавиатура
menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📋 Список абонентов"), KeyboardButton(text="🔍 Поиск абонента")],
    [KeyboardButton(text="👤 Действия с абонентами"), KeyboardButton(text="🏢 Действия с юридическими лицами")],
    [KeyboardButton(text="🔄 Перезапуск")]
], resize_keyboard=True)

actions_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="➕ Добавить абонента"), KeyboardButton(text="✏ Изменить абонента")],
    [KeyboardButton(text="🏢 Добавить в юр. лицо"), KeyboardButton(text="❌ Удалить абонента")],
    [KeyboardButton(text="🔙 Назад")]
], resize_keyboard=True)

company_actions_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="➕ Добавить юр. лицо"), KeyboardButton(text="✏ Изменить юр. лицо")],
    [KeyboardButton(text="❌ Удалить юр. лицо"), KeyboardButton(text="📋 Список юр. лиц")],
    [KeyboardButton(text="🔙 Назад")]
], resize_keyboard=True)


# Стейт для FSM
class SubscriberForm(StatesGroup):
    waiting_for_last_name = State()
    waiting_for_first_name = State()
    waiting_for_phone = State()
    waiting_for_address = State()
    waiting_for_company_assignment = State()
    waiting_for_update = State()
    waiting_for_delete = State()
    waiting_for_search = State()
    waiting_for_update_first_name = State()

class CompanyForm(StatesGroup):
    waiting_for_name = State()
    waiting_for_company_type = State()
    waiting_for_inn = State()
    waiting_for_update = State()
    waiting_for_delete = State()
    waiting_for_update_name = State()
    waiting_for_update_to = State()





# Обработчик команды /start
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("Привет! Выберите действие:", reply_markup=menu)


# 📌 Действия с абонентами
@dp.message(lambda message: message.text == "👤 Действия с абонентами")
async def subscriber_actions(message: types.Message):
    await message.answer("Выберите действие с абонентом:", reply_markup=actions_menu)


# 📌 Действия с юридическими лицами
@dp.message(lambda message: message.text == "🏢 Действия с юридическими лицами")
async def company_actions(message: types.Message):
    await message.answer("Выберите действие с юридическим лицом:", reply_markup=company_actions_menu)


# 📌 Возвращение в главное меню
@dp.message(lambda message: message.text == "🔙 Назад")
async def back_to_menu(message: types.Message):
    await message.answer("Главное меню:", reply_markup=menu)


# 📌 Получение списка абонентов
@dp.message(lambda message: message.text == "📋 Список абонентов")
async def get_subscribers(message: types.Message):
    async with async_session_maker() as session:
        user = await get_user(message.from_user.id, session)  # Получаем текущего пользователя
        result = await session.execute(
            select(Subscriber).where(Subscriber.user_id == user.id).order_by(Subscriber.last_name)
        )
        subscribers = result.scalars().all()

    if not subscribers:
        await message.answer("У вас нет абонентов.")
        return

    for s in subscribers:
        text = f"{s.last_name} {s.first_name} - {s.phone}\nАдрес: {s.address or 'Нет адреса'}"
        await message.answer(text)



# 📌 Получение списка юридических лиц
@dp.message(lambda message: message.text.strip() == "📋 Список юр. лиц")
async def get_companies(message: types.Message):
    async with async_session_maker() as session:
        result = await session.execute(select(Company).order_by(Company.name))
        companies = result.scalars().all()

    print(f"Найдено компаний: {len(companies)}")  # Логируем количество компаний

    if not companies:
        await message.answer("Юридических лиц нет.")
        return

    for company in companies:
        text = f"{company.name} ({company.company_type})\nИНН: {company.inn}"
        print(f"Отправка сообщения: {text}")  # Логируем отправляемое сообщение
        await message.answer(text)  # Отправляем каждую компанию отдельным сообщением



# 📌 Добавить абонента

@dp.message(lambda message: message.text == "➕ Добавить абонента")
async def add_subscriber(message: types.Message, state: FSMContext):
    logging.info("Начали добавление Абонента")
    await message.answer("Введите фамилию Абонента:")
    await state.update_data()
    await state.set_state(SubscriberForm.waiting_for_last_name)


# 📌 Обработка введенных данных для абонента
@dp.message(State(SubscriberForm.waiting_for_last_name))
async def process_last_name(message: types.Message, state: FSMContext):
    logging.info(f"Получена фамилия: {message.text}")
    await state.update_data(last_name=message.text)
    await message.answer("Введите имя Абонента:")
    await state.set_state(SubscriberForm.waiting_for_first_name)


@dp.message(State(SubscriberForm.waiting_for_first_name))
async def process_first_name(message: types.Message, state: FSMContext):
    logging.info(f"Получено имя: {message.text}")
    await state.update_data(first_name=message.text)
    await message.answer("Введите телефон Абонента:")
    await state.set_state(SubscriberForm.waiting_for_phone)


@dp.message(State(SubscriberForm.waiting_for_phone))
async def process_phone_number(message: types.Message, state: FSMContext):
    phone_pattern = r"^\+7\(\d{3}\)\d{3} \d{2}-\d{2}$"

    if not re.match(phone_pattern, message.text):
        await message.answer("⚠️ Неверный формат номера телефона! Введите в формате: +7(999)999 99-99")
        return

    logging.info(f"Получен телефон: {message.text}")
    await state.update_data(phone_number=message.text)
    await message.answer("Введите Адрес проживания Абонента:")
    await state.set_state(SubscriberForm.waiting_for_address)


@dp.message(State(SubscriberForm.waiting_for_address))
async def process_address(message: types.Message, state: FSMContext):
    logging.info(f"Получен адрес: {message.text}")
    data = await state.get_data()

    async with async_session_maker() as session:
        user = await get_user(message.from_user.id, session)  # Получаем текущего пользователя

        subscriber = Subscriber(
            last_name=data['last_name'],
            first_name=data['first_name'],
            phone=data['phone_number'],
            address=message.text,
            user_id=user.id  # Привязываем абонента к пользователю
        )
        session.add(subscriber)
        await session.commit()

    await message.answer("Абонент успешно добавлен!")
    await state.clear()


# 📌 Добавить юридическое лицо
@dp.message(lambda message: message.text == "➕ Добавить юр. лицо")
async def add_company(message: types.Message, state: FSMContext):
    logging.info("Начали добавление юр. лица")
    await message.answer("Введите название юридического лица:")
    await state.update_data()
    await state.set_state(CompanyForm.waiting_for_name)

# 📌 Обработка введенных данных для юридического лица
@dp.message(State(CompanyForm.waiting_for_name))
async def process_company_name(message: types.Message, state: FSMContext):
    logging.info(f"Получено название: {message.text}")
    await state.update_data(name=message.text)
    await message.answer("Введите тип юридического лица:")
    await state.set_state(CompanyForm.waiting_for_company_type)


@dp.message(State(CompanyForm.waiting_for_company_type))
async def process_company_type(message: types.Message, state: FSMContext):
    await state.update_data(company_type=message.text)
    await message.answer("Введите ИНН юридического лица:")
    await state.set_state(CompanyForm.waiting_for_inn)


@dp.message(State(CompanyForm.waiting_for_inn))
async def process_inn(message: types.Message, state: FSMContext):
    data = await state.get_data()
    inn = message.text

    async with async_session_maker() as session:
        company = Company(
            name=data['name'],
            company_type=data['company_type'],  #
            inn=inn
        )

        session.add(company)
        await session.commit()

    await message.answer("Юридическое лицо успешно добавлено!")
    await state.clear()



# Поиск абонента
# Обработчик команды для начала поиска абонента
@dp.message(lambda message: message.text == "🔍 Поиск абонента")
async def search_subscriber(message: types.Message, state: FSMContext):
    await message.answer("Введите номер телефона абонента:")
    await state.set_state(SubscriberForm.waiting_for_search.state)


# Обработчик для обработки номера телефона после его ввода
@dp.message(State(SubscriberForm.waiting_for_search))
async def process_search(message: types.Message, state: FSMContext):
    phone_number = message.text.strip()



    # Обработка поиска абонента в базе данных
    async with async_session_maker() as session:
        result = await session.execute(select(Subscriber).where(Subscriber.phone == phone_number))
        subscriber = result.scalars().first()

    # Если абонент найден
    if subscriber:
        text = f"{subscriber.last_name} {subscriber.first_name} - {subscriber.phone}\nАдрес: {subscriber.address or 'Нет адреса'}"
        await message.answer(text)
    else:
        await message.answer("Абонент не найден.")

    # Завершаем состояние после выполнения
    await state.finish()

    # Удаление абонента
@dp.message(lambda message: message.text == "❌ Удалить абонента")
async def delete_subscriber(message: types.Message, state: FSMContext):
    await message.answer("Введите номер телефона абонента для удаления:")
    await state.set_state(SubscriberForm.waiting_for_delete)  # Убираем "State()"

    @dp.message(SubscriberForm.waiting_for_delete)
    async def process_delete(message: types.Message, state: FSMContext):
        async with async_session_maker() as session:
            stmt = delete(Subscriber).where(Subscriber.phone == message.text)
            result = await session.execute(stmt)
            await session.commit()

            if result.rowcount == 0:  # Проверяем, был ли удалён абонент
                await message.answer("Абонент с таким номером не найден.")
            else:
                await message.answer("Абонент удален.")

        await state.clear()

@dp.message(lambda message: message.text == "❌ Удалить юр. лицо")
async def delete_company(message: types.Message, state: FSMContext):
    await message.answer("Введите ИНН юридического лица для удаления:")
    await state.set_state(CompanyForm.waiting_for_delete)  # Устанавливаем состояние

@dp.message(CompanyForm.waiting_for_delete)
async def process_delete_company(message: types.Message, state: FSMContext):
    async with async_session_maker() as session:
        stmt = delete(Company).where(Company.inn == message.text)
        result = await session.execute(stmt)
        await session.commit()

        if result.rowcount == 0:  # Проверяем, было ли удаление
            await message.answer("Юридическое лицо с таким ИНН не найдено.")
        else:
            await message.answer("Юридическое лицо удалено.")

    await state.clear()

# Обновление абонента
@dp.message(lambda message: message.text == "✏ Изменить абонента")
async def update_subscriber(message: types.Message, state: FSMContext):
    await message.answer("Введите номер телефона абонента:")
    await state.set_state(SubscriberForm.waiting_for_update)

@dp.message(SubscriberForm.waiting_for_update)
async def process_update_subscriber(message: types.Message, state: FSMContext):
    async with async_session_maker() as session:
        result = await session.execute(select(Subscriber).where(Subscriber.phone == message.text))
        subscriber = result.scalar_one_or_none()

    if not subscriber:
        await message.answer("Абонент не найден.")
        return

    await state.update_data(subscriber_id=subscriber.id)
    await message.answer("Введите новое имя абонента:")
    await state.set_state(SubscriberForm.waiting_for_update_first_name)

@dp.message(SubscriberForm.waiting_for_update_first_name)
async def update_subscriber_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with async_session_maker() as session:
        await session.execute(
            update(Subscriber).where(Subscriber.id == data['subscriber_id']).values(first_name=message.text)
        )
        await session.commit()
    await message.answer("Имя абонента обновлено!")
    await state.clear()

# Добавление абонента к юридическому лицу
@dp.message(lambda message: message.text == "🏢 Добавить в юр. лицо")
async def assign_subscriber_to_company(message: types.Message, state: FSMContext):
    await message.answer("Введите номер телефона абонента:")
    await state.set_state(SubscriberForm.waiting_for_company_assignment)

@dp.message(SubscriberForm.waiting_for_company_assignment)
async def process_assign_subscriber(message: types.Message, state: FSMContext):
    async with async_session_maker() as session:
        result = await session.execute(select(Subscriber).where(Subscriber.phone == message.text))
        subscriber = result.scalar_one_or_none()

    if not subscriber:
        await message.answer("Абонент не найден.")
        return

    await state.update_data(subscriber_id=subscriber.id)
    await message.answer("Введите ИНН юридического лица:")
    await state.set_state(CompanyForm.waiting_for_update)


@dp.message(CompanyForm.waiting_for_update_to)
async def process_assign_company(message: types.Message, state: FSMContext):
    data = await state.get_data()

    async with async_session_maker() as session:
        company = await session.execute(select(Company).where(Company.inn == message.text))
        company = company.scalar_one_or_none()

        if not company:
            await message.answer("Юридическое лицо не найдено. Попробуйте снова.")
            return

        await session.execute(
            update(Subscriber).where(Subscriber.id == data['subscriber_id']).values(company_id=company.id)
        )
        await session.commit()

    await message.answer("Абонент привязан к юридическому лицу!")
    await state.clear()

@dp.errors()
async def error_handler(update: types.Update, exception: Exception):
    logging.error(f"Ошибка {exception}")
    return True

# Обновление юридического лица
@dp.message(lambda message: message.text == "✏ Изменить юр. лицо")
async def update_company(message: types.Message, state: FSMContext):
    await message.answer("Введите ИНН юридического лица:")
    await state.set_state(CompanyForm.waiting_for_update)

@dp.message(CompanyForm.waiting_for_update)
async def process_update_company(message: types.Message, state: FSMContext):
    async with async_session_maker() as session:
        result = await session.execute(select(Company).where(Company.inn == message.text))
        company = result.scalar_one_or_none()

    if not company:
        await message.answer("Юридическое лицо не найдено.")
        return

    await state.update_data(company_id=company.id)
    await message.answer("Введите новое название юридического лица:")
    await state.set_state(CompanyForm.waiting_for_update_name)

@dp.message(CompanyForm.waiting_for_update_name)
async def update_company_name(message: types.Message, state: FSMContext):
    data = await state.get_data()

    # Check for 'subscriber_id' key existence before proceeding
    company_id = data.get('company_id')
    if not company_id:
        await message.answer("Не найден ID юридического лица. Попробуйте снова.")
        return

    async with async_session_maker() as session:
        await session.execute(
            update(Company).where(Company.id == company_id).values(name=message.text)
        )
        await session.commit()

    await message.answer("Название юридического лица обновлено!")
    await state.clear()



# Запуск бота
async def main():
    await create_tables()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

dp.message.register(add_company, lambda message: message.text == "➕ Добавить юридическое лицо")
dp.message.register(process_company_name, CompanyForm.waiting_for_name)
dp.message.register(process_company_type, CompanyForm.waiting_for_company_type)
dp.message.register(process_inn, CompanyForm.waiting_for_inn)
dp.message.register(add_subscriber, lambda message: message.text == "➕ Добавить подписчика")
dp.message.register(process_last_name, SubscriberForm.waiting_for_last_name)
dp.message.register(process_first_name, SubscriberForm.waiting_for_first_name)
dp.message.register(process_phone_number, SubscriberForm.waiting_for_phone)
dp.message.register(process_address, SubscriberForm.waiting_for_address   )


if __name__ == "__main__":
    asyncio.run(main())
