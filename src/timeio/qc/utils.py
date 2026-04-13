#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from __future__ import annotations

import typing
from timeio.qc.qctest import QcTest, StreamInfo, Param

if typing.TYPE_CHECKING:
    from timeio import feta

__all__ = [
    "collect_params",
    "collect_tests",
]


def collect_params(test: feta.QAQCTest):
    params = []
    for stream in test.streams or []:
        params.append(
            StreamInfo(
                stream["arg_name"],
                stream["alias"],
                stream["sta_thing_id"],
                stream["sta_stream_id"],
            )
        )
    for key, value in (test.args or {}).items():
        params.append(Param(key, value))
    return params


def collect_tests(conf: feta.QAQC) -> list[QcTest]:
    context_window = conf.context_window
    tests = []
    for i, test in enumerate(conf.get_tests(), start=1):  # type: int, feta.QAQCTest
        try:
            params = collect_params(test)
            qctest = QcTest(
                name=test.name,
                func_name=test.function,
                params=params,
                context_window=context_window,
                qctool="saqc",
            )
        except Exception as e:
            e.add_note(f"Qc test {i} ({test})")
            e.add_note(f"Config {conf}")
            raise e

        tests.append(qctest)

    return tests
