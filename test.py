import json,os,sys
import aiosqlite
from sqlalchemy.ext.asyncio import create_async_engine
from itsm_collect_app.infrastructure.database import create_database
from itsm_collect_app.infrastructure.sql_api import SqlApi
from contextlib import asynccontextmanager
from itsm_collect_app.infrastructure.database import Database
from itsm_collect_app.settings import Config
from loguru import logger
from itsm_collect_app.rpa_app.handler import Handler

@asynccontextmanager
async def lifespan(database:'Database'):
    await database.connect()
    yield
    await database.disconnect()

async def main():
    config=Config()
    engine = create_async_engine(
        config.app.database_url,
        json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
        json_deserializer=json.loads,
    )
    database = create_database(engine)
    async with lifespan(database):
        sql_api = SqlApi(database)
        await sql_api.load_task_data()
        await sql_api.load_person_data()
        rpa_handler=await Handler(sql_api,config).start()
        await rpa_handler.val_login()
        await rpa_handler.test_run('XQDG2025042501640','号码授权')
        await rpa_handler.stop()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
