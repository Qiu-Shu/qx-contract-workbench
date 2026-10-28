"""Explicit, memory-only personal Weixin probe; default execution is offline."""
import argparse
import getpass
import hashlib
import json
from pathlib import Path
import sys
import time

import httpx

from cn_contract.weixin_probe import ConnectionProbe, MAX_FILE_BYTES, ProbeError, REPLY_TEXT


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='显式连接官方微信助手，仅限本人和虚构测试文件')
    parser.add_argument('--expected-file', type=Path, help='唯一允许接收的虚构文件，读取文件名、大小和SHA256')
    parser.add_argument('--wait-seconds', type=int, default=180, help='每阶段最长等待秒数，范围30至300')
    args = parser.parse_args(argv)
    if not args.live:
        print('OFFLINE：未连接微信。本人通道验收需 --live --expected-file <虚构文件>。')
        print('运行时仅保存内存凭据；指定文件核验成功且收到本次明确测试口令后，才回一条固定文字。')
        return 0
    if args.expected_file is None or not 30 <= args.wait_seconds <= 300:
        parser.error('--live 需要 --expected-file，--wait-seconds 范围30至300')
    try:
        with args.expected_file.open('rb') as source:
            raw = source.read(MAX_FILE_BYTES + 1)
        if not 0 < len(raw) <= MAX_FILE_BYTES:
            raise ProbeError('EXPECTED_FILE_LIMIT')
        expected = {'name': args.expected_file.name, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    except (OSError, ProbeError):
        print('EXPECTED_FILE_ERROR：无法读取限定大小内的虚构文件。')
        return 2
    probe = None
    try:
        with httpx.Client(trust_env=False, follow_redirects=False) as client:
            probe = ConnectionProbe(client=client, expected_file=expected)
            print('QR：请律师本人用个人微信扫描官方二维码链接：', flush=True)
            print(probe.start_qr(), flush=True)
            deadline = time.monotonic() + args.wait_seconds
            verify_code = None
            while time.monotonic() < deadline:
                state = probe.poll_login(verify_code)
                verify_code = None
                print('LOGIN：' + state, flush=True)
                if state == 'confirmed':
                    break
                if state in {'expired', 'verify_code_blocked', 'binded_redirect'}:
                    print('登录停止：二维码过期、配对受限或已有绑定；本次未取得可用新会话。', flush=True)
                    return 3
                if state == 'need_verifycode':
                    verify_code = getpass.getpass('请在本机输入手机微信显示的配对数字（不回显）：')
                time.sleep(1)
            else:
                print('LOGIN_TIMEOUT：未确认连接；本次停止，不自动刷新二维码。')
                return 3
            print('CONNECTED：仅限扫码本人私聊；请发送指定虚构文件及本次口令：', flush=True)
            print('两者先后顺序均可；文件核验成功且口令收到后才会回复。', flush=True)
            print(probe.test_instruction, flush=True)
            print('预定回复：' + REPLY_TEXT, flush=True)
            print('EXPECTED_FILE：' + json.dumps(expected, ensure_ascii=False), flush=True)
            deadline = time.monotonic() + args.wait_seconds
            while time.monotonic() < deadline:
                for report in probe.poll_messages():
                    print(json.dumps(report, ensure_ascii=False), flush=True)
                summary = probe.summary()
                if summary['reply'] in {'unknown', 'rejected'}:
                    print('SEND_STOP：发送结果未知或被拒绝；不会重发，请本人核对微信。', flush=True)
                    return 4
                if summary['file_verified'] and summary['reply'] == 'submitted':
                    print('PROBE_SUBMITTED：文件摘要吻合，固定确认已提交；请本人在微信核对收到。')
                    return 0
                time.sleep(1)
            print('RECEIVE_TIMEOUT：收件验收未完成，本次停止。')
            return 3
    except ProbeError as exc:
        print('PROBE_STOP：' + str(exc), flush=True)
        return 2
    except (KeyboardInterrupt, EOFError):
        print('CANCELLED：已停止；已经提交或结果未知的发送不会重试。', flush=True)
        return 130
    finally:
        if probe is not None:
            print('SUMMARY：' + json.dumps(probe.summary(), ensure_ascii=False), flush=True)
            probe.close()


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
