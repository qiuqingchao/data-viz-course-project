"""数据库访问层。

对外只暴露"该用到的"，避免上层 import 一堆内部细节：

    from ..db import bootstrap, connection, data, users
"""
