#!/bin/bash
# Install hermes_dashboard as a launchable command
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="$HOME/.local/bin/hermes_dashboard"

mkdir -p "$HOME/.local/bin"

cat > "$TARGET" << 'EOF'
#!/bin/bash
exec python3 "$HOME/hermes_dashboard/hermes_dashboard.py" "$@"
EOF

chmod +x "$TARGET"

if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
    echo "Added ~/.local/bin to PATH. Restart your shell or run:"
    echo '  export PATH="$HOME/.local/bin:$PATH"'
fi

echo "Installed. Run: hermes_dashboard"
