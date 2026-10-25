class TaskSettingException(Exception):
    ...

class IgnoreError(Exception):
    #退出
    pass

class YzmError(IgnoreError):
    #验证码错误
    pass



class LoginError(IgnoreError):
    #不知名登录错误
    #先忽略吧
    pass

class DriverApiError(IgnoreError):
    #请求错误
    pass


class ExitError(Exception):
    #退出
    pass

class PgServerHttpError(ExitError):
    #数据库请求错误
    pass

class PwdError(ExitError):
    #密码错误
    pass


class XpathError(ExitError):
    # 选择错误
    pass

