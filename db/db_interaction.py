import sqlalchemy as sa
from db.db_setup import engine, async_session, Base
from sqlalchemy import select, update, insert, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload
from sqlalchemy.ext.asyncio import AsyncSession

association_table = sa.Table(
    "user_session",
    Base.metadata,
    sa.Column("user_id", sa.Integer, ForeignKey("user_table.id"), primary_key=True),
    sa.Column("kpp_id", sa.Integer, ForeignKey("kpp_table.id"), primary_key=True),
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


class User(Base):
    __tablename__ = "user_table"

    id: Mapped[int] = mapped_column(primary_key=True)
    sessions = relationship(
        "KPP", secondary=association_table, back_populates="users"
    )


class KPP(Base):
    __tablename__ = "kpp_table"

    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column()
    threshold: Mapped[int] = mapped_column()
    users = relationship(
        "User", secondary=association_table, back_populates="sessions"
    )

async def add_user_if_not_exists(user_id: int, session: AsyncSession):
    """Тут фікс"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(id=user_id)
        session.add(user)
        await session.commit()
    return user


async def get_user_thresholds_database(user_id: int) -> list[dict]:
    """Get all KPPs linked to a user with thresholds and country_ids."""
    async with async_session() as session:
        statement = (
            select(KPP.id, KPP.country_id, KPP.threshold)
            .join(association_table)
            .join(User)
            .where(User.id == user_id)
        )
        result = await session.execute(statement)
        rows = result.all()
        return [
            {"kpp_id": row.id, "country_id": row.country_id, "threshold": row.threshold}
            for row in rows
        ]



async def set_user_threshold_database(user_id: int, threshold: int, kpp_id: int, kpp_country_id: int):
    """Set threshold for a KPP and link it to a user."""
    async with async_session() as session:
        # ensure user exists
        await add_user_if_not_exists(user_id, session)

        # get or create KPP
        result = await session.execute(select(KPP).where((KPP.id == kpp_id) & (KPP.country_id == kpp_country_id)))

        kpp = result.scalar_one_or_none()
        if kpp is None:
            kpp = KPP(id=kpp_id, country_id=kpp_country_id, threshold=threshold)
            session.add(kpp)
            await session.flush()
        else:
            kpp.threshold = threshold  # Зміна значення

        result = await session.execute(
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.sessions))
        )
        user = result.scalar_one()
        if kpp not in user.sessions:
            user.sessions.append(kpp)

        await session.commit()

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
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.sessions))
        )
        user = result.scalar_one_or_none()
        if not user:
            return []

        return [
            {"id": kpp.id, "country_id": kpp.country_id, "threshold": kpp.threshold}
            for kpp in user.sessions
        ]


