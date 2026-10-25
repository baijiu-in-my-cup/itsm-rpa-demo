from pydantic import BaseModel, field_validator, Field, PrivateAttr, WrapValidator, ValidatorFunctionWrapHandler,ValidationInfo, model_validator,UUID4,computed_field
from typing import Any, List, Dict, Optional, Union, Callable, Coroutine, get_args, Type, Literal, Set, TypedDict,TypeVar,Tuple
from pydantic_core import PydanticUseDefault
from typing_extensions import Annotated
from datetime import datetime,time
from uuid import uuid4
from pydantic.dataclasses import dataclass
from  enum import Enum

def _str_to_obj(v: Any, handler: ValidatorFunctionWrapHandler, info: ValidationInfo):
    if isinstance(v, type(None)):
        raise PydanticUseDefault
    if isinstance(v, str):
        if '|' in v:
            return handler(v.strip().split(' | '))
        elif '\n' in v:
            return handler(v.strip().split('\n'))
        else:
            return handler([v.strip()])
    return handler(v)
T = TypeVar('T')
StrToObj = Annotated[T, WrapValidator(_str_to_obj)]


class GroupData(BaseModel):
    accept_user_name: Optional[str] = None
    business_key: str
    create_time: Optional[str] = None
    expiration_time: Optional[str] = None
    orgName: Optional[str] = None
    process_base_id: Optional[int] = None
    systemName: Optional[str] = None
    task_info_id: Optional[str] = None
    task_name: Optional[str] = None
    worksheet_title: str
    worksheet_desc: Optional[str] = None


# 待办工单列表接口返回示例:
# GET {base_url}/admin/Workindex/worklistGro?taskType=active&event=Gro&time=...&page=1&limit=...
class GroupJson(BaseModel):
    code: int
    count: int
    data: List[GroupData]
    msg: str

# 反馈信息行示例(字段名为示意,与 Mock 服务返回保持一致):
# {
#     "business_key": "TK2025040201808",
#     "contact_phone": "13800000000",
#     "feedbak_content": "支持中心【权限申请】已处理,以实施环节时间为开始时间,有效期 5 个自然日.",
#     "feedbak_org_id": 5722,
#     "feedbak_org_path": "示例公司/技术支持中心",
#     "feedbak_time": "2025-04-15 15:20:49",
#     "feedbak_user_id": 263615,
#     "feedbak_user_name": "系统支持",
#     "id": 1825033,
#     "real_name": "系统支持",
#     "orgName": "示例公司/技术支持中心",
#     "mobile": "13800000000"
# }
class FeedRow(BaseModel):
    business_key:str
    contact_phone:str
    feedbak_content:str
    feedbak_org_id:int
    feedbak_org_path:str
    feedbak_time:str
    feedbak_user_id:int
    feedbak_user_name:str
    id:int
    real_name:str
    orgName:str
    mobile:str

class FeedJson(BaseModel):
    total:int
    rows:List[FeedRow]

class FileRow(BaseModel):
    create_by_name: str
    create_date: str
    file_id: int
    file_name: str
    file_type: str
    file_size: str
    md5: str
    rela_id: str


class FileListJson(BaseModel):
    total: int
    rows: List[FileRow]


class TrackTrace(BaseModel):
    status: str = Field(alias="状态")
    operation: str = Field(alias="操作")
    step_name: str = Field(alias="环节名称")
    handler: str = Field(alias="环节处理组/人")
    department: str = Field(alias="所属行政部门")
    start_time: str = Field(alias="开始时间")
    end_time: str = Field(alias="完成时间")
    comment: str = Field(alias="处理意见")
    attachment: str = Field(alias="环节附件", default="")

class FilterContentConfig(BaseModel):
    class Config:
        populate_by_name = True

    def model_dump_text(self,is_edit:bool=False,exclude_none:bool=True):
        data={}
        for k,v in self.model_dump(by_alias=True, exclude_none=exclude_none, exclude={'filter_desc','is_or_not'}).items():
            if isinstance(v,list):
                if is_edit and v:
                    data[k] = '\n'.join(v) if len(v) > 1 else v[0]
                elif is_edit and not v:
                    data[k] =''
                elif v:
                    data[k]=' | '.join(v) if len(v) >1 else v[0]
            elif v or not exclude_none:
                data[k]=v
        return data

FILTER_DESC_LIST=['处理跟踪','工单信息','文件','判断条件']

class TrackTraceFilterContent(FilterContentConfig):
    # _id: str = Field(default_factory=lambda :str(uuid4()))

    is_or_not: bool = Field(alias="是否存在")
    filter_desc: Literal['处理跟踪', '历史记录'] = Field('处理跟踪', alias="过滤描述")
    step_name: Optional[str] = Field(None, alias="环节名称")
    handler: Optional[str] = Field(None, alias="环节处理人")
    department: Optional[str] = Field(None, alias="所属行政部门")
    comment: Optional[str] = Field(None, alias="处理意见")
    str_fuzzy_match_key: StrToObj[List[str]] = Field(default_factory=lambda:[], alias="模糊匹配")

class FileFilterContent(FilterContentConfig):
    # id: str = Field(default_factory=lambda :str(uuid4()))

    is_or_not: bool = Field(alias="是否存在")
    filter_desc: Literal['文件'] = Field('文件', alias="过滤描述")
    file_type: StrToObj[Optional[List[str]]] = Field(None, alias="文件类型")
    file_key: StrToObj[Optional[List[str]]] = Field(None, alias="文件关键字")
    file_len: Optional[int] = Field(None, alias="文件数目")
    str_fuzzy_match_key: StrToObj[List[str]] = Field(default_factory=lambda:[], alias="模糊匹配")

class WorkSheetFilterContent(FilterContentConfig):
    # id: str = Field(default_factory=lambda :str(uuid4()))

    is_or_not: bool = Field(alias="是否存在")
    filter_desc: Literal['工单信息'] = Field('工单信息', alias="过滤描述")
    worksheet_title: Optional[str] = Field(None, alias="需求标题")
    worksheet_desc: Optional[str] = Field(None, alias="需求描述")
    str_fuzzy_match_key: StrToObj[List[str]]= Field(default_factory=lambda:[], alias="模糊匹配")

class FeedFilterContent(FilterContentConfig):
    # id: str = Field(default_factory=lambda :str(uuid4()))
    is_or_not: bool = Field(alias="是否存在")
    filter_desc: Literal['反馈信息'] = Field('反馈信息', alias="过滤描述")
    feedbak_content: Optional[List[str]] = Field([], alias="反馈内容")
    feedbak_user_name: Optional[List[str]] = Field([], alias="反馈用户")
    str_fuzzy_match_key: StrToObj[List[str]]= Field(default_factory=lambda:[], alias="模糊匹配")

# class ParentChildContent(FilterContentConfig):
#     filter_desc: Literal['父子过滤'] = Field('父子过滤')
#     parent_content:"TrackTraceFilterContent"=Field(alias="父过滤内容")
#     child_contents:List[Union["TrackTraceFilterContent"]]=Field(alias="子过滤内容")

class FilterContent(BaseModel):
    # id: str = Field(default_factory=lambda :str(uuid4()))
    filter_type: str
    filter_content: List[
        Union["FilterContent", "FileFilterContent", "TrackTraceFilterContent", "WorkSheetFilterContent","FeedFilterContent"]]

class TaskTypeAndPersonRoleEnum(Enum):
    COMMON=1
    RING_SEND=2
    UNTREAD=3

class Person(BaseModel):
    name: str
    department: List[str]
    role:Optional[int]=Field(default=1,description='1普通/2派单')
    sign:Optional[int]=Field(default=0,description='轮次标记')

class Task(BaseModel):
    task_id: Optional[str] = None
    task_desc: str
    submit_person: Optional[List[Person]]=None
    submit_reply: str
    condition: FilterContent
    total: Optional[int] = 0
    end_time:Optional[str]=None
    task_type:Optional[int]=Field(default=1,description='任务标记，1普通，2转一线团队轮询，3退回')
    is_activate:Optional[int]=Field(default=1,description='1启用，0不启用')

class RecordLog(BaseModel):
    record_id: str
    business_key: str
    task_desc: str
    order_desc: Optional[str] = ''
    create_time: datetime
    submit_name:str=''
    screenshot_base64:str=''


class TaskCount(BaseModel):
    task_desc: str
    count: int = 0


class RecordLogItems(BaseModel):
    total: int = 0
    task_count: List[TaskCount] = []
    data: Optional[List[RecordLog]] = None



