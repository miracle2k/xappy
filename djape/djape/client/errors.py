
class SearchClientError(Exception):
    def __init__(self, msg, errtype):
        self.msg = msg
        self.errtype = errtype

    def __str__(self):
        return "%s: %s" % (self.errtype, self.msg)

