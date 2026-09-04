"""Test whether Foxmail opens an RFC 822 .eml file as an editable draft."""

from __future__ import annotations

import json
import os
import platform
import struct
import sys
import tempfile
from datetime import datetime
from email import policy
from email.message import EmailMessage
from pathlib import Path


SUBJECT = "[SubSentry测试] Foxmail EML草稿兼容性验证（请勿发送）"
BODY = (
    "这是SubSentry生成的本地EML兼容性测试邮件。\n\n"
    "请检查以下内容：\n"
    "1. Foxmail是否打开了邮件；\n"
    "2. 邮件是否处于可编辑的写信状态，而不是只读查看状态；\n"
    "3. 中文标题和正文是否完整；\n"
    "4. 收件人和中文附件是否完整。\n\n"
    "请勿发送，检查完成后直接关闭窗口。"
)
RECIPIENT = "test@example.invalid"
ATTACHMENT_NAME = "SubSentry_Foxmail_EML兼容性测试附件.txt"
EML_NAME = "SubSentry_Foxmail_EML_Test.eml"
RESULT_NAME = "Foxmail_EML_测试结果.txt"


def _read_registry_value(root, path: str, name: str = "") -> str:
    try:
        import winreg

        with winreg.OpenKey(root, path) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value)
    except (ImportError, FileNotFoundError, OSError):
        return "未设置"


def collect_environment() -> dict:
    info = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "python": sys.version.replace("\n", " "),
        "python_bits": struct.calcsize("P") * 8,
        "is_windows": os.name == "nt",
        "test_method": "local_eml_x_unsent",
    }
    if os.name != "nt":
        return info

    import winreg

    eml_progid = _read_registry_value(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.eml\UserChoice",
        "ProgId",
    )
    info["eml_progid"] = eml_progid
    if eml_progid != "未设置":
        info["eml_open_command"] = _read_registry_value(
            winreg.HKEY_CLASSES_ROOT,
            rf"{eml_progid}\shell\open\command",
        )
    else:
        info["eml_open_command"] = "未设置"
    info["mailto_progid"] = _read_registry_value(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\mailto\UserChoice",
        "ProgId",
    )
    return info


def create_eml() -> Path:
    message = EmailMessage(policy=policy.SMTP)
    message["X-Unsent"] = "1"
    message["X-SubSentry-Test"] = "1"
    message["To"] = RECIPIENT
    message["Subject"] = SUBJECT
    message.set_content(BODY, charset="utf-8")
    message.add_attachment(
        "SubSentry Foxmail EML兼容性测试附件。\n请勿发送本测试邮件。\n".encode(
            "utf-8-sig"
        ),
        maintype="text",
        subtype="plain",
        filename=ATTACHMENT_NAME,
    )

    preferred = Path(__file__).resolve().parent / EML_NAME
    try:
        preferred.write_bytes(message.as_bytes())
        return preferred
    except OSError:
        fallback = Path(tempfile.gettempdir()) / EML_NAME
        fallback.write_bytes(message.as_bytes())
        return fallback


def _ask(prompt: str) -> bool:
    while True:
        answer = input(f"{prompt} [Y/N]：").strip().lower()
        if answer in {"y", "yes", "是"}:
            return True
        if answer in {"n", "no", "否"}:
            return False
        print("请输入 Y 或 N。")


def write_result(environment: dict, eml_path: Path, checks: dict) -> Path:
    passed = all(checks.values())
    lines = [
        "SubSentry Foxmail EML草稿兼容性测试",
        f"测试结论：{'通过' if passed else '未通过'}",
        "测试方式：本地EML文件（X-Unsent: 1），未调用任何发送接口",
        f"EML文件：{eml_path}",
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
    environment = collect_environment()
    print("=== 环境检查 ===")
    print(json.dumps(environment, ensure_ascii=False, indent=2))

    if os.name != "nt":
        print("\n[ERROR] 该测试只能在Windows值班机上运行。")
        return 2

    print("\n=== 安全说明 ===")
    print("本测试只生成一个本地EML文件，并使用Windows文件关联打开它。")
    print("程序不调用MAPI、SMTP或其他发送接口，不会自动发送邮件。")
    print("测试收件人是保留测试域example.invalid，不是真实邮箱。")
    if input("\n输入 Y 生成并打开测试邮件，输入其他内容取消：").strip().lower() != "y":
        print("测试已取消。")
        return 0

    eml_path = create_eml()
    print(f"\n已生成本地邮件文件：{eml_path}")
    try:
        os.startfile(str(eml_path))
    except OSError as exc:
        print(f"[ERROR] Windows无法打开EML文件：{exc}")

    print("\n请检查刚才打开的窗口。不要发送邮件，然后回答：")
    checks = {
        "Foxmail已打开该EML文件": _ask("是否由Foxmail打开"),
        "邮件处于可编辑写信状态": _ask("标题、正文和收件人是否可以直接编辑"),
        "中文标题和正文完整": _ask("中文标题和正文是否完整且没有乱码"),
        "测试收件人正确": _ask(f"收件人是否为{RECIPIENT}"),
        "中文测试附件存在": _ask(f"是否看到附件{ATTACHMENT_NAME}"),
        "邮件没有自动发送": _ask("邮件是否没有自动进入发件箱或已发送"),
    }
    result_path = write_result(environment, eml_path, checks)
    passed = all(checks.values())

    print("\n=== 测试结果 ===")
    print("EML草稿兼容性测试通过。" if passed else "测试未通过，请保留结果文件。")
    print(f"结果文件：{result_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
