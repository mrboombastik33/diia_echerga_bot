import sqlalchemy as sa
from db.db_setup import engine, async_session, Base
from sqlalchemy import select, update
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


class User(Base):
    __tablename__ = "user_table"

    id: Mapped[int] = mapped_column(primary_key=True)
    status_message_id: Mapped[int | None] = mapped_column(nullable=True)


class UserSession(Base):
    __tablename__ = "user_session"

    user_id: Mapped[int] = mapped_column(sa.ForeignKey("user_table.id"), primary_key=True)
    kpp_id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column()
    threshold: Mapped[int] = mapped_column()


async def add_user_if_not_exists(user_id: int, session: AsyncSession):
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(id=user_id)
        session.add(user)
        await session.commit()
    return user


async def get_user_thresholds_database(user_id: int) -> list[dict]:
    async with async_session() as session:
        result = await session.execute(
            select(UserSession).where(UserSession.user_id == user_id)
        )
        return [
            {"kpp_id": us.kpp_id, "country_id": us.country_id, "threshold": us.threshold}
            for us in result.scalars().all()
        ]


async def set_user_threshold_database(user_id: int, threshold: int, kpp_id: int, kpp_country_id: int):
    async with async_session() as session:
        try:
            await add_user_if_not_exists(user_id, session)

            result = await session.execute(
                select(UserSession).where(
                    (UserSession.user_id == user_id) & (UserSession.kpp_id == kpp_id)
                )
            )
            us = result.scalar_one_or_none()
            if us is None:
                us = UserSession(user_id=user_id, kpp_id=kpp_id, country_id=kpp_country_id, threshold=threshold)
                session.add(us)
            else:
                us.threshold = threshold
                us.country_id = kpp_country_id

            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def add_user_if_not_exists_simple(user_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        if result.scalar_one_or_none() is None:
            session.add(User(id=user_id))
            await session.commit()


async def show_user_data(user_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(UserSession).where(UserSession.user_id == user_id)
        )
        return [
            {"id": us.kpp_id, "country_id": us.country_id, "threshold": us.threshold}
            for us in result.scalars().all()
        ]


async def get_status_message_id(user_id: int) -> int | None:
    async with async_session() as session:
        result = await session.execute(select(User.status_message_id).where(User.id == user_id))
        return result.scalar_one_or_none()


async def set_status_message_id(user_id: int, message_id: int | None):
    async with async_session() as session:
        await session.execute(update(User).where(User.id == user_id).values(status_message_id=message_id))
        await session.commit()
