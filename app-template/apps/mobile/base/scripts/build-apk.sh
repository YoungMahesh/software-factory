#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOBILE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ANDROID_DIR="${MOBILE_DIR}/android"
DIST_DIR="${MOBILE_DIR}/dist"

mkdir -p "${DIST_DIR}"

# Pure Continuous Native Generation check
if [ ! -d "${ANDROID_DIR}" ]; then
  echo "Android native folder not found. Running expo prebuild..."
  (cd "${MOBILE_DIR}" && npx expo prebuild --platform android --no-install)
fi

echo "Building Android APK..."
cd "${ANDROID_DIR}"
./gradlew assembleDebug

# Copy output APK to dist
BUILD_OUTPUT="${ANDROID_DIR}/app/build/outputs/apk/debug/app-debug.apk"
if [ -f "${BUILD_OUTPUT}" ]; then
  cp "${BUILD_OUTPUT}" "${DIST_DIR}/app-debug.apk"
  echo "APK build successful: ${DIST_DIR}/app-debug.apk"
else
  echo "Build completed, output in ${ANDROID_DIR}/app/build/outputs/apk"
fi
