import sqlalchemy as sa
from db.db_setup import engine, async_session, Base
from sqlalchemy import select, update, insert

user_table = sa.Table(
    "user",
    Base.metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("threshold", sa.Integer, default=20)
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_user_threshold(user_id: int) -> int:
    async with async_session() as session:
        result = await session.execute(
            select(user_table.c.threshold).where(user_table.c.id == user_id)
        )
        row = result.scalar()
        return row if row is not None else 0

async def set_user_threshold(user_id: int, threshold: int):
    async with async_session() as session:
        await add_user_if_not_exists(user_id)
        await session.execute(
            update(user_table).where(user_table.c.id == user_id).values(threshold=threshold)
        )
        await session.commit()

async def add_user_if_not_exists(user_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(user_table.c.id).where(user_table.c.id == user_id)
        )
        if result.scalar() is None:
            await session.execute(
                insert(user_table).values(id=user_id)
            )
            await session.commit()
