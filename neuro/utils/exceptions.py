class FileNotWiki(BaseException):
    pass


class InternalError(BaseException):
    pass


class TiddlerDoesNotExist(BaseException):
    pass


class InvalidHeader(BaseException):
    pass


class InvalidPath(BaseException):
    pass


class MissingTitle(BaseException):
    pass


# NETWORK
class InvalidURL(BaseException):
    pass


class UnhandledStatusCode(BaseException):
    pass


class NoAPI(BaseException):
    pass


class PortInUse(BaseException):
    pass


class NfxViolation(BaseException):
    pass


class NfxCycle(BaseException):
    pass


class AmbiguousModule(NfxViolation):
    """A stem or name that modules of several trees share; `candidates` are
    their qualified names, `<namespace>-<stem>`."""

    def __init__(self, key, candidates):
        super().__init__(f"{key!r} names {len(candidates)} modules: {', '.join(candidates)} - "
                         f"write the one you mean as <namespace>-<stem>")
        self.key, self.candidates = key, list(candidates)


class NoOntology(BaseException):
    pass
