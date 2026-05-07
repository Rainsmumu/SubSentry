#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-$(date +%Y.%m.%d)-windows-offline}"
OUT_DIR="$ROOT/release/SubSentry_${VERSION}"
ZIP_FILE="$ROOT/release/SubSentry_${VERSION}.zip"

ensure_wheels() {
  mkdir -p "$ROOT/wheels"
  for pyver in 38 39 310 311 312 313; do
    python3 -m pip download -r "$ROOT/requirements.txt" -d "$ROOT/wheels" \
      --only-binary=:all: --platform win_amd64 --implementation cp \
      --python-version "$pyver" --trusted-host pypi.org \
      --trusted-host files.pythonhosted.org >/dev/null
  done

  # pip evaluates environment markers on the build machine. These are needed on
  # Windows/Python 3.8-3.9 even if the package builder runs on macOS.
  python3 -m pip download importlib-metadata==6.8.0 zipp==3.20.2 colorama==0.4.6 \
    -d "$ROOT/wheels" --only-binary=:all: --platform win_amd64 \
    --implementation cp --python-version 39 --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org >/dev/null
}

ensure_wheels

rm -rf "$OUT_DIR" "$ZIP_FILE"
mkdir -p "$OUT_DIR/data"

copy_item() {
  local src="$1"
  if [ -e "$ROOT/$src" ]; then
    mkdir -p "$OUT_DIR/$(dirname "$src")"
    cp -R "$ROOT/$src" "$OUT_DIR/$src"
  fi
}

copy_item app.py
copy_item cable_config.py
copy_item circuit_analyzer.py
copy_item excel_builder.py
copy_item report_builder.py
copy_item deploy_check.py
copy_item requirements.txt
copy_item README.md
copy_item WINDOWS_OFFLINE_DEPLOY.md
copy_item install_offline_deps.bat
copy_item check_env.bat
copy_item start.bat
copy_item stop_subsentry.bat
copy_item templates
copy_item static
copy_item "海缆路由图"
copy_item "金桥机房电路表-数据源说明.md"

if [ -f "$ROOT/金桥机房电路表.xlsx" ]; then
  cp "$ROOT/金桥机房电路表.xlsx" "$OUT_DIR/金桥机房电路表.xlsx"
fi

if [ -d "$ROOT/wheels" ]; then
  cp -R "$ROOT/wheels" "$OUT_DIR/wheels"
fi

cat > "$OUT_DIR/VERSION.txt" <<EOF
SubSentry
Version: $VERSION
Git Commit: $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)
Build Time: $(date '+%Y-%m-%d %H:%M:%S')
EOF

python3 -m zipfile -c "$ZIP_FILE" "$OUT_DIR"
echo "$ZIP_FILE"
