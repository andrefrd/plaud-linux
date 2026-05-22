#!/usr/bin/env python3
import sys
from plaud_linux import main, main_tray

if __name__ == "__main__":
    # Se receber o argumento --cli, inicia em modo terminal
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        sys.argv.pop(1)
        main()
    else:
        main_tray()
