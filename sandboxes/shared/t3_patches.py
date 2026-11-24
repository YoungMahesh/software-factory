"""Length-preserving binary patches and patch script for T3 Code SEA binary."""

# Length-preserving in-place patches on Node SEA binary /opt/t3/t3 without shifting byte offsets:
# 1. RemoteOpenTargets SSH Host patch (248 -> 248 bytes): checks process.env.T3_SSH_HOST
#    or process.env.SANDBOX_NAME for the SSH host alias instead of defaulting to modal.local.
T3_SSH_PATCH_TARGET = (
    "Y29uc3Qgc2hvcnRIb3N0bmFtZSA9ICh5aWVsZCogSG9zdG5hbWUpLnNwbGl0KCIuIilbMF0/LnRyaW0o"
    "KTsKCQkJaWYgKHNob3J0SG9zdG5hbWUgIT09IHZvaWQgMCAmJiBzaG9ydEhvc3RuYW1lLmxlbmd0aCA+"
    "IDApIHRhcmdldHMucHVzaCh7CgkJCQlraW5kOiAibWRucyIsCgkJCQlob3N0OiBgJHtzaG9ydEhvc3Ru"
    "YW1lfS5sb2NhbGAsCgkJCQkuLi51c2VybmFtZSA9PT0gbnVsbCA/IHt9IDogeyB1c2VybmFtZSB9CgkJ"
    "CX0pOwoJCQk="
)
T3_SSH_PATCH_REPLACEMENT = (
    "Y29uc3QgaCA9IHByb2Nlc3MuZW52LlQzX1NTSF9IT1NUfHwgcHJvY2Vzcy5lbnYuU0FOREJPWF9OQU1F"
    "OwoJCQljb25zdCBzID0gaCB8fCAoeWllbGQqIEhvc3RuYW1lKS5zcGxpdCgiLiIpWzBdPy50cmltKCk7"
    "CgkJCWlmIChzKSB0YXJnZXRzLnB1c2goewoJCQkJa2luZDogIm1kbnMiLAoJCQkJaG9zdDogaCB8fCBg"
    "JHtzfS5sb2NhbGAsCgkJCQkuLi51c2VybmFtZSA9PT0gbnVsbCA/IHt9IDogeyB1c2VybmFtZSB9CgkJ"
    "CX0pOwoJCQk="
)

# 2. Provider Order patch (127 -> 127 bytes): ranks antigravity ahead of opencode in BUILT_IN_DRIVER_ORDER.
T3_DRIVER_ORDER_PATCH_TARGET = (
    "QlVJTFRfSU5fRFJJVkVSX09SREVSID0gWwoJCSJjb2RleCIsCgkJImNsYXVkZUFnZW50IiwKCQkiY3Vyc29y"
    "IiwKCQkiZ3JvayIsCgkJIm9wZW5jb2RlIiwKCQkiYW50aWdyYXZpdHkiLAoJCSJmeCIsCgkJImtpcm8iCgld"
    "Ow=="
)
T3_DRIVER_ORDER_PATCH_REPLACEMENT = (
    "QlVJTFRfSU5fRFJJVkVSX09SREVSID0gWwoJCSJjb2RleCIsCgkJImNsYXVkZUFnZW50IiwKCQkiY3Vyc29y"
    "IiwKCQkiZ3JvayIsCgkJImFudGlncmF2aXR5IiwKCQkib3BlbmNvZGUiLAoJCSJmeCIsCgkJImtpcm8iCgld"
    "Ow=="
)

T3_PATCH_SCRIPT = (
    "python3 -c '"
    'import base64; p = "/opt/t3/t3"; '
    f't1 = base64.b64decode("{T3_SSH_PATCH_TARGET}"); '
    f'r1 = base64.b64decode("{T3_SSH_PATCH_REPLACEMENT}"); '
    f't2 = base64.b64decode("{T3_DRIVER_ORDER_PATCH_TARGET}"); '
    f'r2 = base64.b64decode("{T3_DRIVER_ORDER_PATCH_REPLACEMENT}"); '
    "assert len(t1) == len(r1) == 248; "
    "assert len(t2) == len(r2) == 127; "
    'c = open(p, "rb").read(); '
    'c = c.replace(t1, r1, 1) if t1 in c else c; '
    'c = c.replace(t2, r2, 1) if t2 in c else c; '
    'open(p, "wb").write(c)\''
)
