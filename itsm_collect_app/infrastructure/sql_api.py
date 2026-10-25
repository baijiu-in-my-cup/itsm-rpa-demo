from itsm_collect_app.infrastructure.database import Database
from itsm_collect_app.infrastructure import models
from sqlalchemy.sql import insert, select, delete, desc, or_, func
import os
import pathlib
from uuid import uuid4
from itsm_collect_app.schema import *
from itsm_collect_app.rpa_app.common import walk_document_files, load_data_from_file,dump_data_to_file
from contextlib import asynccontextmanager
from collections import defaultdict
from datetime import date


class SqlApi:
    def __init__(self, database: 'Database',persons_path:str,tasks_dir:str):
        self.database = database
        self.persons_path=str(pathlib.Path(persons_path).absolute().resolve())
        self.tasks_dir=str(pathlib.Path(tasks_dir).absolute().resolve())

    @asynccontextmanager
    async def get_session(self):
        async with self.database.session() as session:
            try:
                yield session
                await session.commit()  # Commit the transaction
            except Exception:
                await session.rollback()  # Rollback in case of error
                raise

    async def load_task_data(self):
        task_files = walk_document_files(self.tasks_dir)
        task_models = [Task(**load_data_from_file(file_path)) for file_path in task_files]
        async with self.get_session() as session:
            await session.execute(delete(models.Task))  # Delete all rows in the Task table
            tasks_data = [
                {
                    "task_id": str(uuid4()),
                    "task_desc": task_row.task_desc,
                    "submit_reply": task_row.submit_reply,
                    "submit_person": [p.model_dump() for p in task_row.submit_person],
                    "condition": task_row.condition.model_dump(),
                    "total": task_row.total,
                    'end_time': task_row.end_time,
                    'is_activate':task_row.is_activate,
                    'task_type':task_row.task_type,
                }
                for task_row in task_models
            ]
            stmt = insert(models.Task).values(tasks_data)
            await session.execute(stmt)

    async def load_person_data(self):
        persons = [Person.model_validate(p) for p in load_data_from_file(self.persons_path)['data']]
        async with self.get_session() as session:
            await session.execute(delete(models.Person))
            data = [
                row.model_dump()
                for row in persons
            ]
            stmt = insert(models.Person).values(data)
            await session.execute(stmt)

    async def dump_person_data(self):
        async with self.get_session() as session:
            stmt = select(models.Person)
            result = await session.execute(stmt)
            records = result.scalars().all()
            data = {
                "data": [
                    {
                        "name": record.name,
                        "department": record.department,
                        "role": record.role,
                        "sign": record.sign,
                    } for record in records
                ]
            }
            dump_data_to_file(data,self.persons_path)

    async def get_task_data(self, task_id: Optional[str] = None) -> Optional[List[Task]]:
        async with self.get_session() as session:
            stmt = select(models.Task)
            if task_id:
                stmt = stmt.filter(models.Task.task_id == task_id)
            result = await session.execute(stmt)
            records = result.scalars().all()
            if records:
                return [Task.model_validate(record.__dict__) for record in records]
    
    async def get_person_data(self) -> Optional[List[Person]]:
        async with self.get_session() as session:
            stmt = select(models.Person)
            result = await session.execute(stmt)
            records = result.scalars().all()
            return [Person(**record.__dict__) for record in records]

    async def add_person_data(self, name: str, department: List[str],role:Optional[int]=1) -> None:
        async with self.get_session() as session:
            stmt = insert(models.Person).values(name=name,
                                                department=department,role=role,sign=0)
            await session.execute(stmt)

    async def update_submit_person(self, task_id: str, submit_person: List[Any]) -> None:
        async with self.get_session() as session:
            stmt = select(models.Task).filter_by(
                task_id=task_id
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if record:
                record.submit_person = submit_person

    async def update_task_end_time(self, task_id: str, end_time: str) -> None:
        async with self.get_session() as session:
            stmt = select(models.Task).filter_by(
                task_id=task_id
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if record:
                record.end_time = end_time
    async def update_task_is_activate(self,task_id: str, is_activate: int)->None:
        async with self.get_session() as session:
            stmt = select(models.Task).filter_by(
                task_id=task_id
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if record:
                record.is_activate = is_activate
    async def add_record_log(self, data: RecordLog) -> None:
        async with self.get_session() as session:
            stmt = insert(models.RecordLog).values(
                **data.model_dump()
            )
            await session.execute(stmt)

    async def get_record_log(self, business_key: str = '', task_desc: str = '', start_time: Optional[date] = None,
                             end_time: Optional[date] = None) -> Optional[RecordLogItems]:
        async with self.get_session() as session:
            stmt = select(models.RecordLog).filter(
                models.RecordLog.business_key.ilike(f'%{business_key}%'),
                models.RecordLog.task_desc.ilike(f'%{task_desc}%'),
            )
            if start_time:
                stmt = stmt.filter(
                    func.date(models.RecordLog.create_time) >= start_time
                )
            if end_time:
                stmt = stmt.filter(
                    func.date(models.RecordLog.create_time) <= end_time
                )
            stmt = stmt.order_by(desc(models.RecordLog.create_time))
            result = await session.execute(stmt)
            records = result.scalars().all()
            task_data = defaultdict(int)
            data = []
            for record in records:
                task_data[record.task_desc] += 1
                data.append(RecordLog(**record.__dict__))
            return RecordLogItems(total=len(records), data=data,
                                  task_count=[TaskCount(task_desc=k, count=c) for k, c in task_data.items()])
