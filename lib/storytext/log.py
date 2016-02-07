
"""
LoggerAdapter to impart contextual information
see https://docs.python.org/3/howto/logging-cookbook.html#using-loggeradapters-to-impart-contextual-information
"""

import logging


class ExtraAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        kwargs["extra"] = kwargs.get("extra", {"task": "Default"})
        return msg, kwargs

def getLogger(name):
    logger = logging.getLogger(name)
    return ExtraAdapter(logger, {})
