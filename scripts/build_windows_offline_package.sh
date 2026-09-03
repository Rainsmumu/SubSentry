#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-$(date +%Y.%m.%d)-windows-offline}"
RELEASE_DIR="$ROOT/release"
BUILD_DIR="$RELEASE_DIR/.build-$VERSION"
FULL_ROOT="$BUILD_DIR/full/SubSentry"
UPDATE_ROOT="$BUILD_DIR/update/SubSentry_Update_$VERSION"
FULL_ZIP="$RELEASE_DIR/SubSentry_${VERSION}_FULL.zip"
UPDATE_ZIP="$RELEASE_DIR/SubSentry_${VERSION}_UPDATE.zip"
WHEEL_CACHE="$ROOT/wheels/win312"

PYTHON_INSTALLER="python-installer/python-3.12.10-amd64.exe"
BOOTSTRAP_SOURCE="上海ITMC电路槽路表0407改进版.xlsx"
# 可用环境变量指定引导槽路表的实际文件路径（打包后文件名仍为 BOOTSTRAP_SOURCE）
BOOTSTRAP_FILE="${SUBSENTRY_BOOTSTRAP_FILE:-$ROOT/$BOOTSTRAP_SOURCE}"
REFERENCE_DIR="海缆路由中断分析结果"

APP_ITEMS=(
  app.py
  cable_config.py
  circuit_analyzer.py
  comparison.py
  data_source.py
  deploy_check.py
  excel_builder.py
  fault_workflow.py
  report_builder.py
  supervisor_excel.py
  requirements.txt
  windows_manage.py
  README.md
  templates
  static
  tests/test_cable_config.py
  tests/test_comparison.py
  tests/test_excel_builder.py
  tests/test_fault_workflow.py
  tests/test_report_builder.py
  tests/test_supervisor_excel.py
  tests/test_windows_manage.py
)

ROOT_ITEMS=(
  backup.bat
  check_env.bat
  install_offline_deps.bat
  install_python_312.bat
  resolve_python.bat
  rollback.bat
  set_env.bat
  start.bat
  stop_subsentry.bat
  windows_manage.py
  WINDOWS_OFFLINE_DEPLOY.md
)

if [[ ! "$VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]]; then
  echo "Invalid version: $VERSION" >&2
  exit 1
fi

for path in "$PYTHON_INSTALLER" "$REFERENCE_DIR"; do
  if [[ ! -e "$ROOT/$path" ]]; then
    echo "Missing required package input: $ROOT/$path" >&2
    exit 1
  fi
done
if [[ ! -f "$BOOTSTRAP_FILE" ]]; then
  echo "Missing bootstrap circuit table: $BOOTSTRAP_FILE" >&2
  exit 1
fi

if [[ -e "$BUILD_DIR" || -e "$FULL_ZIP" || -e "$UPDATE_ZIP" ]]; then
  echo "Release output already exists for $VERSION. Use a new version." >&2
  exit 1
fi

mkdir -p "$RELEASE_DIR" "$BUILD_DIR" "$WHEEL_CACHE"

echo "Downloading Windows Python 3.12 x64 wheels..."
python3 -m pip download \
  --requirement "$ROOT/requirements.txt" \
  --dest "$WHEEL_CACHE" \
  --only-binary=:all: \
  --platform win_amd64 \
  --implementation cp \
  --python-version 312 \
  --trusted-host pypi.org \
  --trusted-host files.pythonhosted.org

# pip evaluates platform markers on the macOS build host, so include the
# Windows-only terminal dependency explicitly.
python3 -m pip download \
  colorama==0.4.6 \
  --dest "$WHEEL_CACHE" \
  --only-binary=:all: \
  --platform win_amd64 \
  --implementation cp \
  --python-version 312 \
  --trusted-host pypi.org \
  --trusted-host files.pythonhosted.org

copy_items() {
  local destination="$1"
  shift
  mkdir -p "$destination"
  for item in "$@"; do
    mkdir -p "$destination/$(dirname "$item")"
    cp -R "$ROOT/$item" "$destination/$item"
  done
}

write_version_file() {
  local path="$1"
  cat >"$path" <<EOF
SubSentry
Version: $VERSION
Git Commit: $(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)
Build Time: $(date '+%Y-%m-%d %H:%M:%S %z')
Windows Port: 18765
EOF
}

write_checksums() {
  local package_root="$1"
  (
    cd "$package_root"
    find . -type f ! -name SHA256SUMS.txt -exec shasum -a 256 {} \; \
      | sort >SHA256SUMS.txt
  )
}

normalize_batch_files() {
  local package_root="$1"
  find "$package_root" -type f -name "*.bat" -exec \
    perl -pi -e 's/\r?\n/\r\n/g' {} \;
}

run_packaged_tests() {
  local app_root="$1"
  (
    cd "$app_root"
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
  )
}

echo "Assembling complete first-install package..."
VERSION_APP="$FULL_ROOT/versions/$VERSION"
copy_items "$VERSION_APP" "${APP_ITEMS[@]}"
copy_items "$FULL_ROOT" "${ROOT_ITEMS[@]}"
printf '%s\n' "$VERSION" >"$FULL_ROOT/PACKAGE_VERSION.txt"
write_version_file "$FULL_ROOT/VERSION.txt"
mkdir -p \
  "$FULL_ROOT/bootstrap/reference" \
  "$FULL_ROOT/data/uploads" \
  "$FULL_ROOT/reference" \
  "$FULL_ROOT/backups" \
  "$FULL_ROOT/logs"
cp "$BOOTSTRAP_FILE" "$FULL_ROOT/bootstrap/$BOOTSTRAP_SOURCE"
cp -R "$ROOT/$REFERENCE_DIR/." "$FULL_ROOT/bootstrap/reference/"
mkdir -p "$FULL_ROOT/python-installer"
cp "$ROOT/$PYTHON_INSTALLER" "$FULL_ROOT/$PYTHON_INSTALLER"
cp -R "$WHEEL_CACHE" "$FULL_ROOT/wheels"
normalize_batch_files "$FULL_ROOT"
run_packaged_tests "$VERSION_APP"
write_checksums "$FULL_ROOT"

echo "Assembling code-only update package..."
copy_items "$UPDATE_ROOT/app" "${APP_ITEMS[@]}"
copy_items "$UPDATE_ROOT/root_files" "${ROOT_ITEMS[@]}"
cp "$ROOT/install_update.bat" "$UPDATE_ROOT/install_update.bat"
cp "$ROOT/windows_manage.py" "$UPDATE_ROOT/windows_manage.py"
printf '%s\n' "$VERSION" >"$UPDATE_ROOT/PACKAGE_VERSION.txt"
write_version_file "$UPDATE_ROOT/VERSION.txt"
cp -R "$WHEEL_CACHE" "$UPDATE_ROOT/wheels"
normalize_batch_files "$UPDATE_ROOT"
run_packaged_tests "$UPDATE_ROOT/app"
write_checksums "$UPDATE_ROOT"

echo "Creating ZIP archives..."
(
  cd "$BUILD_DIR/full"
  python3 -m zipfile -c "$FULL_ZIP" SubSentry
)
(
  cd "$BUILD_DIR/update"
  python3 -m zipfile -c "$UPDATE_ZIP" "SubSentry_Update_$VERSION"
)

python3 "$ROOT/scripts/verify_windows_package.py" \
  --full "$FULL_ZIP" \
  --update "$UPDATE_ZIP" \
  --version "$VERSION"

echo
echo "$FULL_ZIP"
echo "$UPDATE_ZIP"
