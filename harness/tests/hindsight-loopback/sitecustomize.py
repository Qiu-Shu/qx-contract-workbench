"""Test-only Python network boundary; loaded only by the native restore test."""
import ipaddress
import os
import sys


def guard(event, args):
    if event not in ('socket.connect', 'socket.getaddrinfo'):
        return
    address = args[1][0] if event == 'socket.connect' else args[0]
    if isinstance(address, bytes):
        address = address.decode('ascii')
    try:
        local = ipaddress.ip_address(address).is_loopback
    except ValueError:
        local = address == 'localhost'
    if not local:
        with open(os.environ['QX_TEST_NETWORK_DENIALS'], 'a', encoding='utf-8') as log:
            log.write(event + '\n')
        raise PermissionError('Native restore test permits only loopback networking')


sys.addaudithook(guard)
