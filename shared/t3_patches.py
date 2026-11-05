"""Length-preserving binary patches and patch script for T3 Code SEA binary."""

# Length-preserving in-place patches on Node SEA binary /opt/t3/t3 without shifting byte offsets:
# 1. Antigravity ACP IPv6 patch (426 -> 426 bytes): passes --enforce_kernel_ipv6_support=false
#    to Antigravity ACP runtime on Linux without changing file size or shifting Node SEA offsets.
T3_IPV6_PATCH_TARGET = (
    "ZnVuY3Rpb24gYnVpbGRBbnRpZ3Jhdml0eUFjcFNwYXduSW5wdXQoaW5wdXQpIHsKCXJldHVybiB7CgkJ"
    "Y29tbWFuZDogaW5wdXQuaW5zdGFsbGF0aW9uLmV4ZWN1dGFibGVQYXRoLAoJCWFyZ3M6IGlucHV0LnBy"
    "b2ZpbGUucGxhdGZvcm0gPT09ICJsaW51eCIgPyBbIi0tdWlkPSJdIDogW10sCgkJY3dkOiBpbnB1dC5j"
    "d2QsCgkJZW52OiB7CgkJCS4uLmFudGlncmF2aXR5RW52aXJvbm1lbnQoaW5wdXQucHJvZmlsZSwgaW5w"
    "dXQuYmFzZUVudiA/PyBwcm9jZXNzLmVudiwgaW5wdXQuYXV0aCA/PyBBTlRJR1JBVklUWV9QRVJTT05B"
    "TF9BVVRILCBpbnB1dC5ydW50aW1lVGVtcERpcmVjdG9yeSksCgkJCUFOVElHUkFWSVRZX0hBUk5FU1Nf"
    "UEFUSDogaW5wdXQuaW5zdGFsbGF0aW9uLmhhcm5lc3NQYXRoCgkJfSwKCQlleHRlbmRFbnY6IGZhbHNl"
    "Cgl9Owp9"
)
T3_IPV6_PATCH_REPLACEMENT = (
    "ZnVuY3Rpb24gYnVpbGRBbnRpZ3Jhdml0eUFjcFNwYXduSW5wdXQoaW5wdXQpewpyZXR1cm57CmNvbW1h"
    "bmQ6aW5wdXQuaW5zdGFsbGF0aW9uLmV4ZWN1dGFibGVQYXRoLAphcmdzOiBpbnB1dC5wcm9maWxlLnBs"
    "YXRmb3JtPT09ImxpbnV4Ij9bIi0tZW5mb3JjZV9rZXJuZWxfaXB2Nl9zdXBwb3J0PWZhbHNlIiwiLS11"
    "aWQ9Il06W10sCmN3ZDppbnB1dC5jd2QsCmVudjp7Ci4uLmFudGlncmF2aXR5RW52aXJvbm1lbnQoaW5w"
    "dXQucHJvZmlsZSxpbnB1dC5iYXNlRW52Pz9wcm9jZXNzLmVudiwgaW5wdXQuYXV0aD8/QU5USUdSQVZI"
    "VFlfUEVSU09OQUxfQVVUSCwgaW5wdXQucnVudGltZVRlbXBEaXJlY3RvcnkpLApBTlRJR1JBVklUWV9I"
    "QVJORVNTX1BBVEg6aW5wdXQuaW5zdGFsbGF0aW9uLmhhcm5lc3NQYXRoCn0sCmV4dGVuZEVudjpmYWxz"
    "ZQp9Owp9"
)

# 2. RemoteOpenTargets SSH Host patch (248 -> 248 bytes): checks process.env.T3_SSH_HOST
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

# 3. Provider Order patch (117 -> 117 bytes): ranks antigravity ahead of opencode in BUILT_IN_DRIVER_ORDER.
T3_DRIVER_ORDER_PATCH_TARGET = (
    "QlVJTFRfSU5fRFJJVkVSX09SREVSID0gWwoJCSJjb2RleCIsCgkJImNsYXVkZUFnZW50IiwKCQkiY3Vyc29y"
    "IiwKCQkiZ3JvayIsCgkJIm9wZW5jb2RlIiwKCQkiYW50aWdyYXZpdHkiLAoJCSJmeCIKCV07"
)
T3_DRIVER_ORDER_PATCH_REPLACEMENT = (
    "QlVJTFRfSU5fRFJJVkVSX09SREVSID0gWwoJCSJjb2RleCIsCgkJImNsYXVkZUFnZW50IiwKCQkiY3Vyc29y"
    "IiwKCQkiZ3JvayIsCgkJImFudGlncmF2aXR5IiwKCQkib3BlbmNvZGUiLAoJCSJmeCIKCV07"
)

# 4. Manifest currentModels patch (106 -> 106 bytes): keeps only gemini-3.8-flash-high.
T3_CURRENT_MODELS_PATCH_TARGET = (
    "CQkiYW50aWdyYXZpdHkiOiBbCgkJCSJnZW1pbmktMy44LWZsYXNoLWhpZ2giLAoJCQkiZ2VtaW5pLTMuOC1m"
    "bGFzaC1tZWRpdW0iLAoJCQkiZ2VtaW5pLTMuOC1mbGFzaC1sb3ciCgkJXQ=="
)
T3_CURRENT_MODELS_PATCH_REPLACEMENT = (
    "CQkiYW50aWdyYXZpdHkiOiBbCgkJCSJnZW1pbmktMy44LWZsYXNoLWhpZ2giLyoKCQkJImdlbWluaS0zLjgt"
    "Zmxhc2gtbWVkaXVtIiwKCQkJImdlbWluaS0zLjgtZmxhc2gtbG93IiovXQ=="
)

# 5. Manifest models array patch (1368 -> 1368 bytes): strips medium, low, and legacy models for antigravity.
T3_MODELS_MANIFEST_PATCH_TARGET = (
    "ImFudGlncmF2aXR5IjogewoJCQkiZGVmYXVsdHMiOiB7ICJjaGF0IjogImdlbWluaS0zLjgtZmxhc2gt"
    "aGlnaCIgfSwKCQkJInByb2ZpbGVzIjoge30sCgkJCSJtb2RlbHMiOiBbCgkJCQl7CgkJCQkJInNsdWci"
    "OiAiZ2VtaW5pLTMuOC1mbGFzaC1oaWdoIiwKCQkJCQkibmFtZSI6ICJHZW1pbmkgMy44IEZsYXNoIChI"
    "aWdoKSIsCgkJCQkJInN0YXR1cyI6ICJjdXJyZW50IgoJCQkJfSwKCQkJCXsKCQkJCQkic2x1ZyI6ICJn"
    "ZW1pbmktMy44LWZsYXNoLW1lZGl1bSIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuOCBGbGFzaCAoTWVk"
    "aXVtKSIsCgkJCQkJInN0YXR1cyI6ICJjdXJyZW50IgoJCQkJfSwKCQkJCXsKCQkJCQkic2x1ZyI6ICJn"
    "ZW1pbmktMy44LWZsYXNoLWxvdyIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuOCBGbGFzaCAoTG93KSIs"
    "CgkJCQkJInN0YXR1cyI6ICJjdXJyZW50IgoJCQkJfSwKCQkJCXsKCQkJCQkic2x1ZyI6ICJnZW1pbmkt"
    "My43LWZsYXNoLWhpZ2giLAoJCQkJCSJuYW1lIjogIkdlbWluaSAzLjcgRmxhc2ggKEhpZ2gpIiwKCQkJ"
    "CQkic3RhdHVzIjogImxlZ2FjeSIKCQkJCX0sCgkJCQl7CgkJCQkJInNsdWciOiAiZ2VtaW5pLTMuNy1m"
    "bGFzaC1tZWRpdW0iLAoJCQkJCSJuYW1lIjogIkdlbWluaSAzLjcgRmxhc2ggKE1lZGl1bSkiLAoJCQkJ"
    "CSJzdGF0dXMiOiAibGVnYWN5IgoJCQkJfSwKCQkJCXsKCQkJCQkic2x1ZyI6ICJnZW1pbmktMy43LWZs"
    "YXNoLWxvdyIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuNyBGbGFzaCAoTG93KSIsCgkJCQkJInN0YXR1"
    "cyI6ICJsZWdhY3kiCgkJCQl9LAoJCQkJewoJCQkJCSJzbHVnIjogImdlbWluaS0zLjYtZmxhc2gtaGln"
    "aCIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuNiBGbGFzaCAoSGlnaCkiLAoJCQkJCSJzdGF0dXMiOiAi"
    "bGVnYWN5IgoJCQkJfSwKCQkJCXsKCQkJCQkic2x1ZyI6ICJnZW1pbmktMy42LWZsYXNoLW1lZGl1bSIs"
    "CgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuNiBGbGFzaCAoTWVkaXVtKSIsCgkJCQkJInN0YXR1cyI6ICJs"
    "ZWdhY3kiCgkJCQl9LAoJCQkJewoJCQkJCSJzbHVnIjogImdlbWluaS0zLjYtZmxhc2gtbG93IiwKCQkJ"
    "CQkibmFtZSI6ICJHZW1pbmkgMy42IEZsYXNoIChMb3cpIiwKCQkJCQkic3RhdHVzIjogImxlZ2FjeSIK"
    "CQkJCX0sCgkJCQl7CgkJCQkJInNsdWciOiAiZ2VtaW5pLXByby1hZ2VudCIsCgkJCQkJIm5hbWUiOiAi"
    "R2VtaW5pIDMuMSBQcm8gKEhpZ2gpIiwKCQkJCQkic3RhdHVzIjogImxlZ2FjeSIKCQkJCX0sCgkJCQl7"
    "CgkJCQkJInNsdWciOiAiZ2VtaW5pLTMuMS1wcm8tbG93IiwKCQkJCQkibmFtZSI6ICJHZW1pbmkgMy4x"
    "IFBybyAoTG93KSIsCgkJCQkJInN0YXR1cyI6ICJsZWdhY3kiCgkJCQl9CgkJCV0="
)
T3_MODELS_MANIFEST_PATCH_REPLACEMENT = (
    "ImFudGlncmF2aXR5IjogewoJCQkiZGVmYXVsdHMiOiB7ICJjaGF0IjogImdlbWluaS0zLjgtZmxhc2gt"
    "aGlnaCIgfSwKCQkJInByb2ZpbGVzIjoge30sCgkJCSJtb2RlbHMiOiBbCgkJCQl7CgkJCQkJInNsdWci"
    "OiAiZ2VtaW5pLTMuOC1mbGFzaC1oaWdoIiwKCQkJCQkibmFtZSI6ICJHZW1pbmkgMy44IEZsYXNoIChI"
    "aWdoKSIsCgkJCQkJInN0YXR1cyI6ICJjdXJyZW50IgoJCQkJfS8qCQkJCXsKCQkJCQkic2x1ZyI6ICJn"
    "ZW1pbmktMy44LWZsYXNoLW1lZGl1bSIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuOCBGbGFzaCAoTWVk"
    "aXVtKSIsCgkJCQkJInN0YXR1cyI6ICJjdXJyZW50IgoJCQkJfSwKCQkJCXsKCQkJCQkic2x1ZyI6ICJn"
    "ZW1pbmktMy44LWZsYXNoLWxvdyIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuOCBGbGFzaCAoTG93KSIs"
    "CgkJCQkJInN0YXR1cyI6ICJjdXJyZW50IgoJCQkJfSwKCQkJCXsKCQkJCQkic2x1ZyI6ICJnZW1pbmkt"
    "My43LWZsYXNoLWhpZ2giLAoJCQkJCSJuYW1lIjogIkdlbWluaSAzLjcgRmxhc2ggKEhpZ2gpIiwKCQkJ"
    "CQkic3RhdHVzIjogImxlZ2FjeSIKCQkJCX0sCgkJCQl7CgkJCQkJInNsdWciOiAiZ2VtaW5pLTMuNy1m"
    "bGFzaC1tZWRpdW0iLAoJCQkJCSJuYW1lIjogIkdlbWluaSAzLjcgRmxhc2ggKE1lZGl1bSkiLAoJCQkJ"
    "CSJzdGF0dXMiOiAibGVnYWN5IgoJCQkJfSwKCQkJCXsKCQkJCQkic2x1ZyI6ICJnZW1pbmktMy43LWZs"
    "YXNoLWxvdyIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuNyBGbGFzaCAoTG93KSIsCgkJCQkJInN0YXR1"
    "cyI6ICJsZWdhY3kiCgkJCQl9LAoJCQkJewoJCQkJCSJzbHVnIjogImdlbWluaS0zLjYtZmxhc2gtaGln"
    "aCIsCgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuNiBGbGFzaCAoSGlnaCkiLAoJCQkJCSJzdGF0dXMiOiAi"
    "bGVnYWN5IgoJCQkJfSwKCQkJCXsKCQkJCQkic2x1ZyI6ICJnZW1pbmktMy42LWZsYXNoLW1lZGl1bSIs"
    "CgkJCQkJIm5hbWUiOiAiR2VtaW5pIDMuNiBGbGFzaCAoTWVkaXVtKSIsCgkJCQkJInN0YXR1cyI6ICJs"
    "ZWdhY3kiCgkJCQl9LAoJCQkJewoJCQkJCSJzbHVnIjogImdlbWluaS0zLjYtZmxhc2gtbG93IiwKCQkJ"
    "CQkibmFtZSI6ICJHZW1pbmkgMy42IEZsYXNoIChMb3cpIiwKCQkJCQkic3RhdHVzIjogImxlZ2FjeSIK"
    "CQkJCX0sCgkJCQl7CgkJCQkJInNsdWciOiAiZ2VtaW5pLXByby1hZ2VudCIsCgkJCQkJIm5hbWUiOiAi"
    "R2VtaW5pIDMuMSBQcm8gKEhpZ2gpIiwKCQkJCQkic3RhdHVzIjogImxlZ2FjeSIKCQkJCX0sCgkJCQl7"
    "CgkJCQkJInNsdWciOiAiZ2VtaW5pLTMuMS1wcm8tbG93IiwKCQkJCQkibmFtZSI6ICJHZW1pbmkgMy4x"
    "IFBybyAoTG93KSIsCgkJCQkJInN0YXR1cyI6ICJsZWdhY3kiCgkJCSovCgkJCV0="
)

T3_PATCH_SCRIPT = (
    "python3 -c '"
    'import base64; p = "/opt/t3/t3"; '
    f't1 = base64.b64decode("{T3_IPV6_PATCH_TARGET}"); '
    f'r1 = base64.b64decode("{T3_IPV6_PATCH_REPLACEMENT}"); '
    f't2 = base64.b64decode("{T3_SSH_PATCH_TARGET}"); '
    f'r2 = base64.b64decode("{T3_SSH_PATCH_REPLACEMENT}"); '
    f't3 = base64.b64decode("{T3_DRIVER_ORDER_PATCH_TARGET}"); '
    f'r3 = base64.b64decode("{T3_DRIVER_ORDER_PATCH_REPLACEMENT}"); '
    f't4 = base64.b64decode("{T3_CURRENT_MODELS_PATCH_TARGET}"); '
    f'r4 = base64.b64decode("{T3_CURRENT_MODELS_PATCH_REPLACEMENT}"); '
    f't5 = base64.b64decode("{T3_MODELS_MANIFEST_PATCH_TARGET}"); '
    f'r5 = base64.b64decode("{T3_MODELS_MANIFEST_PATCH_REPLACEMENT}"); '
    "assert len(t1) == len(r1) == 426; "
    "assert len(t2) == len(r2) == 248; "
    "assert len(t3) == len(r3) == 117; "
    "assert len(t4) == len(r4) == 106; "
    "assert len(t5) == len(r5) == 1367; "
    'c = open(p, "rb").read(); '
    'c = c.replace(t1, r1, 1) if t1 in c else c; '
    'c = c.replace(t2, r2, 1) if t2 in c else c; '
    'c = c.replace(t3, r3, 1) if t3 in c else c; '
    'c = c.replace(t4, r4, 1) if t4 in c else c; '
    'c = c.replace(t5, r5, 1) if t5 in c else c; '
    'open(p, "wb").write(c)\''
)
