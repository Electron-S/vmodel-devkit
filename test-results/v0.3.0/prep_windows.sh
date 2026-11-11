#!/bin/bash
# usage: prep_windows.sh <commit>  -> %TEMP%\vmodel 한글 테스트\devkit-0.3.0-<commit> + win-0.3.0-<commit>.ps1 (UTF-16 BOM)
# The ps1 snapshots Windows python processes before and after the harness (leftover child check).
set -euo pipefail
C="$1"
SP=/tmp/claude-1000/-home-cyyoo-develop-vmodel-devkit/1a2fca38-b42f-4f6d-843b-ec75ea8760c9/scratchpad/win
REPO=/home/cyyoo/develop/vmodel-devkit
ROOT="/mnt/c/Users/cyyoo/AppData/Local/Temp/vmodel 한글 테스트"
DEST="$ROOT/devkit-0.3.0-$C"
rm -rf "$DEST"; mkdir -p "$DEST"
git -C "$REPO" archive "$C" | tar -x -C "$DEST"
mkdir -p "$DEST/dist"
for v in 0.1.3 0.1.4 0.1.5 0.2.0; do cp -r "$REPO/dist/vmodel-$v" "$DEST/dist/"; chmod -R u+w "$DEST/dist/vmodel-$v"; done
cat > "$SP/win.ps1" <<PS
\$root = Join-Path \$env:TEMP "vmodel 한글 테스트"
Set-Location (Join-Path \$root "devkit-0.3.0-$C")
\$py = Join-Path \$root ".venv\Scripts\python.exe"
function Snap(\$name) {
  Get-CimInstance Win32_Process | Where-Object { \$_.Name -match '^(python|pythonw|py|pytest|ruff)(\.exe)?\$' } |
    Select-Object ProcessId,ParentProcessId,CreationDate,Name,CommandLine |
    Format-List | Out-File -Encoding utf8 (Join-Path \$root "procs-$C-\$name.txt")
}
Snap "before"
\$code = @"
import sys, unittest, locale, platform
log = open(r'..\t18-harness-0.3.0-$C.log', 'w', encoding='utf-8')
log.write('python %s %s preferred=%s cwd=%s\n' % (sys.version.split()[0], platform.platform(), locale.getpreferredencoding(False), __import__('os').getcwd()))
sys.path.insert(0, 'tests')
suite = unittest.defaultTestLoader.discover('tests', pattern='test_*.py', top_level_dir='tests')
res = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
log.write('RESULT ran=%d failures=%d errors=%d skipped=%d\n' % (res.testsRun, len(res.failures), len(res.errors), len(res.skipped)))
log.close()
sys.exit(0 if res.wasSuccessful() else 1)
"@
& \$py -c \$code
"exit=\$LASTEXITCODE"
Snap "after0"
Start-Sleep -Seconds 60
Snap "after60"
PS
printf '\xff\xfe' > "$ROOT/win-0.3.0-$C.ps1"
iconv -f UTF-8 -t UTF-16LE "$SP/win.ps1" >> "$ROOT/win-0.3.0-$C.ps1"
echo "prepared $DEST and win-0.3.0-$C.ps1"
