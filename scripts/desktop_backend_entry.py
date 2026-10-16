"""PyInstaller entry; the protocol is shared with the tested module entry."""
from cn_contract.desktop_entry import main

if __name__ == '__main__':
    raise SystemExit(main())
