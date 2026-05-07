name: Bima Core WSL
version: 0.0.1
schema: v1
mcpServers:
  - name: Bima Core WSL
    command: wsl.exe
    args:
      - -d
      - Ubuntu
      - --
      - /home/bima_lucian/BIMA_CORE/bima_env/bin/python
      - /home/bima_lucian/BIMA_CORE/mcp_server.py
    env: {}