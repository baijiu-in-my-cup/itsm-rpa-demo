from itsm_collect_app.infrastructure.database import Base
from sqlalchemy import Column, String, TEXT, DateTime, INTEGER
from sqlalchemy.dialects.sqlite import JSON  # 对于 SQLite


class Person(Base):
    __tablename__ = "person"
    name = Column(String(36), primary_key=True, comment='姓名')
    department = Column(JSON, comment='部门信息')
    role=Column(INTEGER,comment='1普通/2派单')
    sign=Column(INTEGER,comment='0/1轮次标志')
# class Condition(Base):
#     id= Column(String(36), primary_key=True, comment='判断ID')
#     filter_type= Column(String(36),nullable=True,comment='判断规则')#OR。AND
#     filter_content=Column(JSON, comment="判断内容")
#     priority=Column(INTEGER,default=0, comment='优先级')
#     parent=Column(String(36), comment='父亲ID')

class Task(Base):
    __tablename__ = "task"
    task_id = Column(String(36), primary_key=True, comment='任务ID')
    task_desc = Column(String(36), comment="任务描述")
    submit_reply = Column(TEXT, comment="提交回复")
    submit_person= Column(JSON, comment="提交部门人员")
    condition = Column(JSON, comment="任务判断")
    total = Column(INTEGER, comment='累计数目')
    end_time = Column(String(6), comment='截止时间', nullable=True)
    task_type=Column(INTEGER, comment='')
    is_activate=Column(INTEGER,comment='是否启用 1 是 0 否')

class RecordLog(Base):
    __tablename__ = "record_log"
    record_id = Column(String(36), primary_key=True, comment='记录ID')
    business_key = Column(String(36), comment="工单编号")
    task_desc = Column(String(36), comment="任务描述")
    create_time = Column(DateTime, comment="提交时间")
    order_desc = Column(TEXT, comment="工单需求描述")
    screenshot_base64 = Column(TEXT, comment="工单表格截图")
    submit_name=Column(String(36),comment='提交人')


