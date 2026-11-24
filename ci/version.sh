#!/usr/bin/env bash
#
# version.sh - print the version this build reports, without a leading v
#
# Used by the Jenkins Package and Release stages.  The source of truth is
# gui/__init__.py, which the About box and the package name also read, so a
# release can never carry a GUI that reports another version.
#

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
sed -n 's/^__version__ *= *"\([^"]*\)".*/\1/p' gui/__init__.py | head -n 1
