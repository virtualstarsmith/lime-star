"""Windows 控制台宿主：在一个隐藏的新控制台里运行一条命令，并按命令向这个控制台投递输入。

只供 test_cli_console.py 使用，只在 Windows 上运行。用法：
    python console_host.py <命令> <工作目录> <stdout 文件> <stderr 文件>

宿主自己的标准输入是管道，每行一条命令：
    text <文字>   把文字和回车作为按键写进控制台的输入缓冲区
    ctrlc         对这个控制台发出一次真实的 Ctrl+C 事件
命令管道关闭表示调用方要收尾，宿主结束被测进程并以它的退出码退出。
宿主启动被测进程后，先把它的进程号写到自己的标准输出。

它补上管道驱动补不到的证据：真实的 Ctrl+C 事件，以及真实控制台上的输入读取。
"""

import ctypes
import os
import signal
import subprocess
import sys
import threading
from ctypes import wintypes

if sys.platform != "win32":
    raise SystemExit("console_host.py 只在 Windows 上运行")

GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
FILE_SHARE_READ, FILE_SHARE_WRITE = 1, 2
OPEN_EXISTING = 3
KEY_EVENT, LEFT_CTRL_PRESSED, CTRL_C_EVENT = 0x0001, 0x0008, 0
VK_RETURN = 0x0D
PROCESS_TERMINATE, PROCESS_SET_QUOTA = 0x0001, 0x0100
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JobObjectExtendedLimitInformation = 9


class KEY_EVENT_RECORD(ctypes.Structure):
    _fields_ = [
        ("bKeyDown", wintypes.BOOL),
        ("wRepeatCount", wintypes.WORD),
        ("wVirtualKeyCode", wintypes.WORD),
        ("wVirtualScanCode", wintypes.WORD),
        ("UnicodeChar", wintypes.WCHAR),
        ("dwControlKeyState", wintypes.DWORD),
    ]


class EVENT_UNION(ctypes.Union):
    _fields_ = [("KeyEvent", KEY_EVENT_RECORD)]


class INPUT_RECORD(ctypes.Structure):
    _fields_ = [("EventType", wintypes.WORD), ("Event", EVENT_UNION)]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
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


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
kernel32.WriteConsoleInputW.restype = wintypes.BOOL
kernel32.WriteConsoleInputW.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(INPUT_RECORD),
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.GenerateConsoleCtrlEvent.restype = wintypes.BOOL
kernel32.GenerateConsoleCtrlEvent.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateJobObjectW.restype = wintypes.HANDLE
kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
kernel32.SetInformationJobObject.restype = wintypes.BOOL
kernel32.SetInformationJobObject.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int,
    wintypes.LPVOID,
    wintypes.DWORD,
]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def _win_error(call: str) -> OSError:
    return OSError(f"{call} 失败，Windows 错误码 {ctypes.get_last_error()}")


def _key(vk: int, char: str) -> list[INPUT_RECORD]:
    def record(down: bool) -> INPUT_RECORD:
        return INPUT_RECORD(KEY_EVENT, EVENT_UNION(KEY_EVENT_RECORD(down, 1, vk, 0, char, 0)))

    return [record(True), record(False)]


def _type_text(console: wintypes.HANDLE, text: str) -> None:
    records = [record for char in text for record in _key(0, char)]
    records.extend(_key(VK_RETURN, "\r"))
    array = (INPUT_RECORD * len(records))(*records)
    written = wintypes.DWORD()
    if not kernel32.WriteConsoleInputW(console, array, len(records), ctypes.byref(written)):
        raise _win_error("WriteConsoleInputW")


def _tie_to_this_process(child: subprocess.Popen[bytes]) -> None:
    """把被测进程放进一个随本进程结束而关闭的作业。

    本进程一退出（哪怕是被强行结束的），作业就关闭，被测进程随之结束，
    不会留在隐藏控制台里一直等输入。
    """
    job = kernel32.CreateJobObjectW(None, None)
    if job is None:
        raise _win_error("CreateJobObjectW")
    limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(
        job, JobObjectExtendedLimitInformation, ctypes.byref(limits), ctypes.sizeof(limits)
    ):
        raise _win_error("SetInformationJobObject")
    process = kernel32.OpenProcess(PROCESS_TERMINATE | PROCESS_SET_QUOTA, False, child.pid)
    if process is None:
        raise _win_error("OpenProcess")
    try:
        if not kernel32.AssignProcessToJobObject(job, process):
            raise _win_error("AssignProcessToJobObject")
    finally:
        kernel32.CloseHandle(process)
    # 作业的句柄有意不关：它随本进程结束而关闭，那正是结束被测进程的时刻。


def _serve(console: wintypes.HANDLE, child: subprocess.Popen[bytes]) -> None:
    for raw in sys.stdin.buffer:
        command = raw.decode("utf-8").rstrip("\r\n")
        if command == "ctrlc":
            if not kernel32.GenerateConsoleCtrlEvent(CTRL_C_EVENT, 0):
                raise _win_error("GenerateConsoleCtrlEvent")
        elif command.startswith("text "):
            _type_text(console, command[5:])
    # 命令管道关闭：结束被测进程，本进程随后以它的退出码退出。
    child.kill()


def main() -> None:
    command, cwd, out_path, err_path = sys.argv[1:5]
    if ctypes.sizeof(INPUT_RECORD) != 20:
        raise RuntimeError(f"INPUT_RECORD 的大小不对：{ctypes.sizeof(INPUT_RECORD)}")
    # 同一次 Ctrl+C 也会发到本进程。本进程只负责投递，收到后照常运行。
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    console = kernel32.CreateFileW(
        "CONIN$",
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        0,
        None,
    )
    if console is None:
        raise _win_error("CreateFileW(CONIN$)")
    with open(out_path, "wb") as out, open(err_path, "wb") as err:
        child = subprocess.Popen(
            [command], cwd=cwd, stdin=open("CONIN$", "rb"), stdout=out, stderr=err
        )
        _tie_to_this_process(child)
        threading.Thread(target=_serve, args=(console, child), daemon=True).start()
        # 调用方凭这个进程号在收尾时确认被测进程已经结束。
        print(child.pid, flush=True)
        code = child.wait()
    # 命令线程可能还阻塞在读 stdin 上。解释器收尾时若去关它占着的流，CPython 会报致命错误；
    # 输出都已落盘，所以直接结束进程，退出码就是被测进程的退出码。
    os._exit(code)


try:
    main()
except Exception as exc:
    print(f"console_host failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
    os._exit(97)
