"""Test whether the Windows default mail client can open a complete MAPI draft."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import struct
import sys
import tempfile
from datetime import datetime
from pathlib import Path


SUBJECT = "[SubSentry测试] Foxmail草稿兼容性验证（请勿发送）"
BODY = (
    "这是SubSentry生成的Foxmail兼容性测试草稿。\r\n\r\n"
    "请检查以下内容：\r\n"
    "1. 中文标题是否完整；\r\n"
    "2. 中文正文是否完整；\r\n"
    "3. 收件人是否为 test@example.invalid；\r\n"
    "4. 是否存在中文文件名的测试附件。\r\n\r\n"
    "请勿发送此邮件，检查完成后直接关闭写信窗口。"
)
RECIPIENT_NAME = "test@example.invalid"
RECIPIENT_ADDRESS = "SMTP:test@example.invalid"
ATTACHMENT_NAME = "SubSentry_Foxmail兼容性测试附件.txt"
RESULT_NAME = "Foxmail_MAPI_测试结果.txt"

MAPI_DIALOG = 0x00000008
MAPI_FORCE_UNICODE = 0x00040000
MAPI_TO = 1

MAPI_RESULTS = {
    0: "SUCCESS_SUCCESS",
    1: "MAPI_E_USER_ABORT（关闭或取消草稿时通常属于正常结果）",
    2: "MAPI_E_FAILURE",
    3: "MAPI_E_LOGIN_FAILURE",
    5: "MAPI_E_INSUFFICIENT_MEMORY",
    9: "MAPI_E_TOO_MANY_FILES",
    10: "MAPI_E_TOO_MANY_RECIPIENTS",
    11: "MAPI_E_ATTACHMENT_NOT_FOUND",
    12: "MAPI_E_ATTACHMENT_OPEN_FAILURE",
    14: "MAPI_E_UNKNOWN_RECIPIENT",
    15: "MAPI_E_BAD_RECIPTYPE",
    18: "MAPI_E_TEXT_TOO_LARGE",
    21: "MAPI_E_AMBIGUOUS_RECIPIENT",
    25: "MAPI_E_INVALID_RECIPS",
    27: "MAPI_E_UNICODE_NOT_SUPPORTED",
    28: "MAPI_E_ATTACHMENT_TOO_LARGE",
}


def _result_label(code: int) -> str:
    return MAPI_RESULTS.get(code, f"未知返回码 {code}")


def _read_registry_value(root, path: str, name: str = "") -> str:
    try:
        import winreg

        with winreg.OpenKey(root, path) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value)
    except (ImportError, FileNotFoundError, OSError):
        return "未设置"


def _pe_bitness(path_value: str) -> str:
    path_text = os.path.expandvars(path_value).strip().strip('"')
    path = Path(path_text)
    if not path.is_file():
        return "文件不存在"
    try:
        with path.open("rb") as stream:
            if stream.read(2) != b"MZ":
                return "不是PE文件"
            stream.seek(0x3C)
            pe_offset = struct.unpack("<I", stream.read(4))[0]
            stream.seek(pe_offset + 4)
            machine = struct.unpack("<H", stream.read(2))[0]
    except (OSError, struct.error):
        return "无法读取"
    return {
        0x014C: "32位 (x86)",
        0x8664: "64位 (x64)",
        0xAA64: "64位 (ARM64)",
    }.get(machine, f"未知PE架构 0x{machine:04X}")


def _read_mail_provider(root, path: str) -> dict:
    try:
        import winreg

        with winreg.OpenKey(root, path) as key:
            values = {"registered": True, "registry_path": path}
            for name in ("DLLPath", "DLLPathEx", "MSIComponentID"):
                try:
                    value, _ = winreg.QueryValueEx(key, name)
                except FileNotFoundError:
                    continue
                values[name] = str(value)
                if name in {"DLLPath", "DLLPathEx"}:
                    expanded = os.path.expandvars(str(value)).strip().strip('"')
                    values[f"{name}_expanded"] = expanded
                    values[f"{name}_exists"] = Path(expanded).is_file()
                    values[f"{name}_bits"] = _pe_bitness(expanded)
            return values
    except (ImportError, FileNotFoundError, OSError) as exc:
        return {
            "registered": False,
            "registry_path": path,
            "error": str(exc),
        }


def collect_environment() -> dict:
    info = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "python": sys.version.replace("\n", " "),
        "python_bits": struct.calcsize("P") * 8,
        "is_windows": os.name == "nt",
    }
    if os.name != "nt":
        return info

    import winreg

    info.update({
        "default_mail_client_hkcu": _read_registry_value(
            winreg.HKEY_CURRENT_USER, r"Software\Clients\Mail"
        ),
        "default_mail_client_hklm": _read_registry_value(
            winreg.HKEY_LOCAL_MACHINE, r"Software\Clients\Mail"
        ),
        "default_mail_client_hklm_32bit": _read_registry_value(
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\WOW6432Node\Clients\Mail",
        ),
        "mailto_progid": _read_registry_value(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\mailto\UserChoice",
            "ProgId",
        ),
        "mapi32_exists": Path(os.environ.get("WINDIR", r"C:\Windows"))
        .joinpath("System32", "MAPI32.DLL")
        .is_file(),
        "foxmail_provider_hkcu": _read_mail_provider(
            winreg.HKEY_CURRENT_USER, r"Software\Clients\Mail\Foxmail"
        ),
        "foxmail_provider_hklm": _read_mail_provider(
            winreg.HKEY_LOCAL_MACHINE, r"Software\Clients\Mail\Foxmail"
        ),
        "foxmail_provider_hklm_32bit": _read_mail_provider(
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\WOW6432Node\Clients\Mail\Foxmail",
        ),
    })
    mail_values = (
        info["default_mail_client_hkcu"],
        info["default_mail_client_hklm"],
        info["default_mail_client_hklm_32bit"],
        info["mailto_progid"],
    )
    info["foxmail_detected_as_default"] = any(
        "foxmail" in value.lower() for value in mail_values
    )
    return info


def create_test_attachment() -> Path:
    directory = Path(tempfile.gettempdir()) / "SubSentry_Foxmail_MAPI_Test"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ATTACHMENT_NAME
    path.write_text(
        "SubSentry Foxmail兼容性测试附件。\n请勿将本测试邮件发送。\n",
        encoding="utf-8-sig",
    )
    return path


def _load_system_mapi():
    mapi_path = Path(os.environ.get("WINDIR", r"C:\Windows")).joinpath(
        "System32", "MAPI32.DLL"
    )
    return ctypes.WinDLL(str(mapi_path))


def open_mapi_draft_unicode(attachment_path: Path) -> int:
    if os.name != "nt":
        raise RuntimeError("该测试只能在Windows值班机上运行")

    from ctypes import wintypes

    class MapiRecipDescW(ctypes.Structure):
        _fields_ = [
            ("ulReserved", wintypes.ULONG),
            ("ulRecipClass", wintypes.ULONG),
            ("lpszName", wintypes.LPWSTR),
            ("lpszAddress", wintypes.LPWSTR),
            ("ulEIDSize", wintypes.ULONG),
            ("lpEntryID", ctypes.c_void_p),
        ]

    class MapiFileDescW(ctypes.Structure):
        _fields_ = [
            ("ulReserved", wintypes.ULONG),
            ("flFlags", wintypes.ULONG),
            ("nPosition", wintypes.ULONG),
            ("lpszPathName", wintypes.LPWSTR),
            ("lpszFileName", wintypes.LPWSTR),
            ("lpFileType", ctypes.c_void_p),
        ]

    class MapiMessageW(ctypes.Structure):
        _fields_ = [
            ("ulReserved", wintypes.ULONG),
            ("lpszSubject", wintypes.LPWSTR),
            ("lpszNoteText", wintypes.LPWSTR),
            ("lpszMessageType", wintypes.LPWSTR),
            ("lpszDateReceived", wintypes.LPWSTR),
            ("lpszConversationID", wintypes.LPWSTR),
            ("flFlags", wintypes.ULONG),
            ("lpOriginator", ctypes.c_void_p),
            ("nRecipCount", wintypes.ULONG),
            ("lpRecips", ctypes.POINTER(MapiRecipDescW)),
            ("nFileCount", wintypes.ULONG),
            ("lpFiles", ctypes.POINTER(MapiFileDescW)),
        ]

    recipients = (MapiRecipDescW * 1)(
        MapiRecipDescW(
            0, MAPI_TO, RECIPIENT_NAME, RECIPIENT_ADDRESS, 0, None
        )
    )
    attachments = (MapiFileDescW * 1)(
        MapiFileDescW(
            0, 0, 0xFFFFFFFF, str(attachment_path), ATTACHMENT_NAME, None
        )
    )
    message = MapiMessageW(
        0,
        SUBJECT,
        BODY,
        None,
        None,
        None,
        0,
        None,
        len(recipients),
        ctypes.cast(recipients, ctypes.POINTER(MapiRecipDescW)),
        len(attachments),
        ctypes.cast(attachments, ctypes.POINTER(MapiFileDescW)),
    )

    mapi = _load_system_mapi()
    try:
        send_mail = mapi.MAPISendMailW
    except AttributeError as exc:
        raise RuntimeError("系统MAPI32.DLL未提供MAPISendMailW接口") from exc

    send_mail.argtypes = [
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.POINTER(MapiMessageW),
        wintypes.ULONG,
        wintypes.ULONG,
    ]
    send_mail.restype = wintypes.ULONG
    return int(
        send_mail(
            0,
            0,
            ctypes.byref(message),
            MAPI_DIALOG | MAPI_FORCE_UNICODE,
            0,
        )
    )


def open_mapi_draft_ansi(attachment_path: Path) -> int:
    if os.name != "nt":
        raise RuntimeError("该测试只能在Windows值班机上运行")

    from ctypes import wintypes

    class MapiRecipDescA(ctypes.Structure):
        _fields_ = [
            ("ulReserved", wintypes.ULONG),
            ("ulRecipClass", wintypes.ULONG),
            ("lpszName", ctypes.c_char_p),
            ("lpszAddress", ctypes.c_char_p),
            ("ulEIDSize", wintypes.ULONG),
            ("lpEntryID", ctypes.c_void_p),
        ]

    class MapiFileDescA(ctypes.Structure):
        _fields_ = [
            ("ulReserved", wintypes.ULONG),
            ("flFlags", wintypes.ULONG),
            ("nPosition", wintypes.ULONG),
            ("lpszPathName", ctypes.c_char_p),
            ("lpszFileName", ctypes.c_char_p),
            ("lpFileType", ctypes.c_void_p),
        ]

    class MapiMessageA(ctypes.Structure):
        _fields_ = [
            ("ulReserved", wintypes.ULONG),
            ("lpszSubject", ctypes.c_char_p),
            ("lpszNoteText", ctypes.c_char_p),
            ("lpszMessageType", ctypes.c_char_p),
            ("lpszDateReceived", ctypes.c_char_p),
            ("lpszConversationID", ctypes.c_char_p),
            ("flFlags", wintypes.ULONG),
            ("lpOriginator", ctypes.c_void_p),
            ("nRecipCount", wintypes.ULONG),
            ("lpRecips", ctypes.POINTER(MapiRecipDescA)),
            ("nFileCount", wintypes.ULONG),
            ("lpFiles", ctypes.POINTER(MapiFileDescA)),
        ]

    def ansi(value: str) -> bytes:
        try:
            return value.encode("mbcs")
        except UnicodeEncodeError as exc:
            raise RuntimeError(f"当前Windows系统编码无法表示测试文本：{exc}") from exc

    recipient_name = ansi(RECIPIENT_NAME)
    recipient_address = ansi(RECIPIENT_ADDRESS)
    attachment_path_bytes = ansi(str(attachment_path))
    attachment_name = ansi(ATTACHMENT_NAME)
    subject = ansi(SUBJECT)
    body = ansi(BODY)

    recipients = (MapiRecipDescA * 1)(
        MapiRecipDescA(
            0, MAPI_TO, recipient_name, recipient_address, 0, None
        )
    )
    attachments = (MapiFileDescA * 1)(
        MapiFileDescA(
            0, 0, 0xFFFFFFFF, attachment_path_bytes, attachment_name, None
        )
    )
    message = MapiMessageA(
        0,
        subject,
        body,
        None,
        None,
        None,
        0,
        None,
        len(recipients),
        ctypes.cast(recipients, ctypes.POINTER(MapiRecipDescA)),
        len(attachments),
        ctypes.cast(attachments, ctypes.POINTER(MapiFileDescA)),
    )

    mapi = _load_system_mapi()
    try:
        send_mail = mapi.MAPISendMail
    except AttributeError as exc:
        raise RuntimeError("系统MAPI32.DLL未提供MAPISendMail接口") from exc

    send_mail.argtypes = [
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.POINTER(MapiMessageA),
        wintypes.ULONG,
        wintypes.ULONG,
    ]
    send_mail.restype = wintypes.ULONG
    return int(send_mail(0, 0, ctypes.byref(message), MAPI_DIALOG, 0))


def _ask(prompt: str) -> bool:
    while True:
        answer = input(f"{prompt} [Y/N]：").strip().lower()
        if answer in {"y", "yes", "是"}:
            return True
        if answer in {"n", "no", "否"}:
            return False
        print("请输入 Y 或 N。")


def _write_result(environment: dict, mode: str, code: int, checks: dict) -> Path:
    passed = code in {0, 1} and all(checks.values())
    lines = [
        "SubSentry Foxmail Simple MAPI兼容性测试",
        f"测试结论：{'通过' if passed else '未通过'}",
        f"调用模式：{mode}",
        f"MAPI返回：{code} - {_result_label(code)}",
        "",
        "环境信息：",
        json.dumps(environment, ensure_ascii=False, indent=2),
        "",
        "人工检查：",
    ]
    lines.extend(f"{label}：{'是' if value else '否'}" for label, value in checks.items())
    content = "\n".join(lines) + "\n"

    preferred = Path(__file__).resolve().parent / RESULT_NAME
    try:
        preferred.write_text(content, encoding="utf-8-sig")
        return preferred
    except OSError:
        fallback = Path(tempfile.gettempdir()) / RESULT_NAME
        fallback.write_text(content, encoding="utf-8-sig")
        return fallback


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--diagnose-only", action="store_true", help="只输出环境信息，不打开草稿"
    )
    parser.add_argument(
        "--mode",
        choices=("ansi", "unicode"),
        default="ansi",
        help="MAPI调用模式；默认使用兼容旧客户端的ANSI模式",
    )
    args = parser.parse_args()

    environment = collect_environment()
    environment["test_mode"] = args.mode
    print("=== 环境检查 ===")
    print(json.dumps(environment, ensure_ascii=False, indent=2))

    if os.name != "nt":
        print("\n[ERROR] 该测试只能在Windows值班机上运行。")
        return 2
    if args.diagnose_only:
        return 0

    if not environment.get("foxmail_detected_as_default"):
        print("\n[WARNING] 注册表中未明确检测到Foxmail是默认邮件客户端。")
        print("如果测试打开了其他邮件软件，请先在Windows默认应用中选择Foxmail。")

    print("\n=== 测试说明 ===")
    print(f"程序将使用{args.mode.upper()} Simple MAPI请求打开一封测试草稿。")
    print("收件人是保留测试域 example.invalid，不会使用真实邮箱。")
    print("请勿点击发送。检查标题、正文、收件人和附件后，直接关闭草稿窗口。")
    if input("\n输入 Y 开始测试，输入其他内容取消：").strip().lower() != "y":
        print("测试已取消。")
        return 0

    attachment = create_test_attachment()
    print(f"\n测试附件：{attachment}")
    print("正在调用Windows Simple MAPI，请观察Foxmail是否打开写信窗口……")
    try:
        if args.mode == "ansi":
            code = open_mapi_draft_ansi(attachment)
        else:
            code = open_mapi_draft_unicode(attachment)
    except Exception as exc:
        print(f"\n[ERROR] 调用失败：{exc}")
        code = -1

    print(f"\nMAPI返回：{code} - {_result_label(code)}")
    print("请根据刚才看到的Foxmail窗口回答：")
    checks = {
        "Foxmail写信窗口已打开": _ask("Foxmail写信窗口是否打开"),
        "中文标题完整": _ask("中文标题是否完整且没有乱码"),
        "中文正文完整": _ask("中文正文是否完整且没有乱码"),
        "测试收件人正确": _ask("收件人是否为 test@example.invalid"),
        "中文测试附件存在": _ask(f"是否看到附件 {ATTACHMENT_NAME}"),
    }
    result_path = _write_result(environment, args.mode, code, checks)
    passed = code in {0, 1} and all(checks.values())

    print("\n=== 测试结果 ===")
    print("兼容性测试通过。" if passed else "兼容性测试未通过，需要分析结果文件。")
    print(f"结果文件：{result_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
