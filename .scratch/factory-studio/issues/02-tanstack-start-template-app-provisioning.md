# 02: TanStack Start Template Repository Provisioning

**What to build:** An application discovery and provisioning interface that lists available repositories under the canonical test organization and allows instantiating new project repositories from a canonical TanStack Start template repository using organization credentials, making new frontend project creation instantaneous and reliable.

**Blocked by:** 01: Dedicated Port 3010 and HTTP Basic Auth Security

**Status:** ready-for-agent

- [ ] API endpoint returns the list of member repositories under the test organization with indicator for TanStack Start template compatibility.
- [ ] API endpoint accepts a requested project name and creates a new repository in the test organization initialized from the canonical TanStack Start template repository.
- [ ] Repository creation uses decrypted organization credentials in memory without persisting secrets to disk.
- [ ] Validation prevents creating duplicate repository names or invalid GitHub repository slugs.
- [ ] Automated tests verify repository listing and successful instantiation from the template using mocked GitHub API interactions.
