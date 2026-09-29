# Pre-baked Android Toolchain in Standard Sandbox

React Native projects require OpenJDK 17, Android SDK command-line tools, target platforms, build tools, NDK, and CMake to compile Android native bundles. We decided to pre-install and license-accept this entire toolchain into a cached Modal image layer when `--react-native` is passed, rather than downloading components on-demand during `./gradlew assembleDebug` or container startup. This eliminates multi-gigabyte download latency and build failures caused by transient network disruptions during developer sessions.

## Considered Options

- **Download on demand during Gradle build**: Keep the container image minimal and let Android Gradle Plugin download NDK and CMake at runtime. Rejected because downloading 3+ GB on fresh sandbox launches causes long startup stalls and flaky builds.
- **Pre-baked Android Toolchain in Image Layer**: Install JDK 17, Android SDK platforms (34, 35), build-tools (34.0.0, 35.0.0), NDK (26.1.10909125), and CMake (3.22.1) in Modal's cached image layer. Accepted because Modal caches image layers indefinitely, yielding near-instant container startup.

## Consequences

- Sandboxes started with `--react-native` have the Android toolchain available immediately in both non-interactive and interactive SSH shells via `/etc/environment` and `~/.bashrc`.
- First-time image build takes several minutes to assemble the layer, but all subsequent sandbox starts are instant.
- Project-level dependencies (such as monorepo autolinking packages) remain the responsibility of the repository's package manifest.
