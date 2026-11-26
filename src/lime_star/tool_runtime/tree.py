"""一条命令连同它派生的全部进程：能一次结束它们，本进程结束时它们也随之结束。

Windows 上把命令的进程放进一个作业对象：它的子进程自动入内，结束作业就是结束整棵树；
作业的句柄一关（包括本进程被强制结束的时候），圈里的进程全部结束（需求 R7.4、R12.5）。
其他平台上命令启动时自成一个进程组，结束时对整组发信号。
"""

import os
import signal
import subprocess
import sys

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _Limits(ctypes.Structure):
        """作业的基本限制，这里只用 LimitFlags。"""

        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _Counts(ctypes.Structure):
        """作业的 I/O 计数，这里不用，占位让结构体的大小对得上。"""

        _fields_ = [
            (name, ctypes.c_ulonglong)
            for name in (
                "ReadOperations",
                "WriteOperations",
                "OtherOperations",
                "ReadBytes",
                "WriteBytes",
                "OtherBytes",
            )
        ]

    class _Extended(ctypes.Structure):
        """JOBOBJECT_EXTENDED_LIMIT_INFORMATION。"""

        _fields_ = [
            ("Basic", _Limits),
            ("Io", _Counts),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.TerminateJobObject.restype = wintypes.BOOL
    _kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    _SET_QUOTA_AND_TERMINATE = 0x0100 | 0x0001
    _KILL_ON_JOB_CLOSE = 0x2000
    _EXTENDED_LIMIT_INFORMATION = 9

    class Tree:
        """Windows：一个作业对象。句柄关掉时圈里的进程全部结束。"""

        def __init__(self, process: subprocess.Popen[bytes]) -> None:
            job = _kernel32.CreateJobObjectW(None, None)
            if not job:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                limits = _Extended()
                limits.Basic.LimitFlags = _KILL_ON_JOB_CLOSE
                if not _kernel32.SetInformationJobObject(
                    job,
                    _EXTENDED_LIMIT_INFORMATION,
                    ctypes.byref(limits),
                    ctypes.sizeof(limits),
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
                handle = _kernel32.OpenProcess(_SET_QUOTA_AND_TERMINATE, False, process.pid)
                if not handle:
                    raise ctypes.WinError(ctypes.get_last_error())
                try:
                    if not _kernel32.AssignProcessToJobObject(job, handle):
                        raise ctypes.WinError(ctypes.get_last_error())
                finally:
                    _kernel32.CloseHandle(handle)
            except BaseException:
                _kernel32.CloseHandle(job)
                raise
            self._job = job

        def end(self) -> None:
            """结束圈里的全部进程。圈是空的时候什么都不做。"""
            _kernel32.TerminateJobObject(self._job, 1)

        def close(self) -> None:
            """关掉作业。圈里如果还有进程（命令留下的后台进程），它们随之结束。"""
            _kernel32.CloseHandle(self._job)

else:

    class Tree:
        """其他平台：命令启动时自成的进程组，组号就是命令进程的进程号。"""

        def __init__(self, process: subprocess.Popen[bytes]) -> None:
            self._group = process.pid

        def end(self) -> None:
            """结束组里的全部进程。组已经不存在时什么都不做。"""
            try:
                os.killpg(self._group, signal.SIGKILL)
            except ProcessLookupError:
                pass

        def close(self) -> None:
            self.end()
