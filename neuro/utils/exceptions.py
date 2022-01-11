class FileNotWiki(BaseException):
    pass


class InternalError(BaseException):
    pass


class ScopeError(BaseException):
    pass


class TiddlerDoesNotExist(BaseException):
    pass


class InvalidHeader(BaseException):
    pass


class MissingTitle(BaseException):
    pass


# NETWORK
class InvalidURL(BaseException):
    pass


class UnhandledStatusCode(BaseException):
    pass

