# Software Factory

Cloud development environments, persistent application resources, and the application starter shared across the factory.
Resource-specific terms are defined in the [Resource Plane glossary](https://github.com/YoungMahesh/software-factory/blob/main/resource-plane/GLOSSARY.md).

## Language

### Factory and interfaces

**Execution Plane**:
The factory subsystem for provisioning and managing Development Sandboxes and their development tooling.

**Resource Plane**:
The factory subsystem for persistent application databases, object storage, and their management interfaces.
_Avoid_: Database host, db-host

**Resource Plane Console**:
The browser interface for managing Resource Plane Projects, application databases, object storage, and their access credentials.
_Avoid_: App Workspace, unqualified control plane

**Resource Plane Management API**:
The programmatic interface for managing Resource Plane Projects, application databases, object storage, and their access credentials.
_Avoid_: Unqualified control plane API

**Hosted Sandbox Control Plane**:
The backend responsible for managing Development Sandboxes, Builder Workspaces, Launch Requests, and Filesystem Snapshots.

**Sandbox Web Dashboard**:
The factory's browser interface for Builder Workspaces, Development Sandboxes, Filesystem Snapshots, and Scratchpad notes.
_Avoid_: Modal Sandbox Runner, runner dashboard

**Builder**:
The area of the Sandbox Web Dashboard for creating and opening Builder Workspaces.

**Modal Sandbox CLI**:
The factory's command-line interface for provisioning and managing Development Sandboxes.

**Dashboard Deployer**:
The separate deployment interface for updating the Sandbox Web Dashboard.
_Avoid_: Staging dashboard, self-deploy UI

**Documentation Web App**:
The factory's public documentation site, hosted independently of the Hosted Sandbox Control Plane.

**Control Plane Provenance**:
The identity of the factory source revision used to deploy the Hosted Sandbox Control Plane, including whether that source contained local modifications.

### Applications and workspaces

**App Template**:
The factory's canonical starter blueprint for new web applications with optional mobile support.

**App Scaffolder**:
The factory tool for creating an application workspace from the App Template.
_Avoid_: Create-base-app, bootstrap script

**Target Repository**:
The source repository selected for sandbox work.

**Builder Workspace**:
A development workspace created through the Builder, with its own coding conversation and sandbox association; existing UI and API terminology calls this a Factory App. Its identity is separate from its Target Repository and any Hosted App, and its tracking ends when its sandbox terminates.
_Avoid_: Factory App (except existing UI/API names), Builder project, prompt project

**Resource Plane Project**:
A named grouping of application databases and object storage managed by the Resource Plane.
_Avoid_: Unqualified project

**T3 Project**:
A repository checkout or workspace registered with T3 Code to group coding conversations. Multiple Builder Workspaces for the same Target Repository can share one T3 Project.
_Avoid_: Unqualified project

**Hosted App**:
An application deployed to the factory's persistent host and exposed through the Host Ingress Proxy. Its deployment identity and lifetime are independent of Builder Workspaces and Development Sandboxes.

**Launch Request**:
A tracked provisioning attempt to create or relaunch a Builder Workspace. Reconnecting to an already running Builder Workspace does not create a Launch Request.

### Development sandboxes

**Development Sandbox**:
An isolated cloud execution environment for working on source code and running development tools.

**Standard Sandbox**:
A Development Sandbox with a lightweight container runtime for workloads that do not require a virtual machine.

**VM Sandbox**:
A Development Sandbox with a virtual machine runtime that supports Docker and workloads requiring virtual machine capabilities.

**Standalone Sandbox**:
A Development Sandbox launched without a selected Target Repository. It can use either runtime and can acquire application workspaces later, including when used as a Prime Sandbox.
_Avoid_: Empty sandbox, blank runner

**Prime Sandbox**:
A Development Sandbox shared by multiple Builder Workspaces with compatible runtime and tooling requirements. It can use either runtime, and its Builder Workspaces share its resources and lifetime.
_Avoid_: Persistent container

**XFCE Desktop Sandbox**:
A VM Sandbox with an XFCE graphical desktop available through noVNC Web Ingress.

**Shared Base Image**:
The factory-maintained starting filesystem shared by Standard Sandboxes and VM Sandboxes.

### Snapshots and persistence

**Filesystem Snapshot**:
A retained capture of a Development Sandbox's root filesystem that can seed a new sandbox, including all workspaces in that filesystem. Running processes, separately stored Builder Workspace tracking records, and persistent volumes are outside its scope.
_Avoid_: Container backup, sandbox image

**Snapshot Registry**:
The catalog of Filesystem Snapshots and their associated sandbox metadata. Removing a catalog entry does not delete the retained image.

**T3 Code Persistent Storage Volume**:
Persistent storage for T3 Code conversation history and usage records, retained independently of a Development Sandbox's lifetime.

### Agents, access, and profiles

**T3 Code Server**:
The sandbox service for coding-agent conversations, source workspaces, and browser or desktop access to those conversations.

**Codex Provider**:
The OpenAI coding agent available through T3 Code in a Development Sandbox.

**Antigravity Provider**:
The Google Gemini coding-agent integration available through T3 Code in a Development Sandbox.

**OpenCode Provider**:
The OpenCode coding-agent integration available through T3 Code in a Development Sandbox.

**Pairing URL**:
An access link authorizing a browser or desktop app to connect to a sandbox's T3 Code Server.

**Modal Profile**:
A named credential configuration used to select Modal access for factory operations.
_Avoid_: Unqualified profile, multi-profile configuration

**Codex Credential Profile**:
One reusable ChatGPT sign-in session for the Codex Provider. Multiple profiles can belong to the same ChatGPT account, and each profile can serve one running sandbox at a time.
_Avoid_: Unqualified profile

**Shared Agent Configuration**:
Factory-maintained editor and agent settings supplied to Development Sandboxes.

**Shared Agent Skills**:
Factory-maintained agent skills available across workspaces in a fresh Development Sandbox. A sandbox resumed from a Filesystem Snapshot retains the skills captured in that snapshot.

### Configuration and secrets

**Factory Environment Configuration**:
The factory settings and credentials used to configure control plane deployment and sandbox launches.

**Central Config Store**:
The factory's shared repository for encrypted repository environments, Host Ingress Proxy configuration, Idea Notes, and Raw Notes.
_Avoid_: Central secrets repo, env-store, caddy-store

**Environment Mapping Manifest**:
A repository-specific mapping from stored environment files to their destination paths in an application workspace.

**Repository Environment Cache**:
A local, decrypted copy of a Target Repository's environment files and their destination mappings, shared by its Git worktrees. It is separate from the encrypted source files in the Central Config Store.
_Avoid_: Repository Vault Cache

**In-Repo Secrets Directory**:
A repository-local directory for private credential files kept outside version control.

**Centralized Organization Credentials**:
The GitHub access credentials and organization selection used by factory operations.

**Modal Sandbox SSH Key**:
The dedicated client key pair for authenticating SSH access to Development Sandboxes.

### Application ingress

**App Base Domain**:
The shared DNS base for the Sandbox Web Dashboard, Dashboard Deployer, and Hosted App hostnames.

**Host Ingress Proxy**:
The shared public web entry point for Hosted Apps and other services on the factory's persistent host.

**Cloudflare Tunnel**:
The application ingress connecting a sandbox web service to a configured public hostname.

**Cloudflare Tunnel Domain**:
The public hostname associated with a sandbox's Cloudflare Tunnel.

**Metro Tunnel**:
The public access path to a mobile application's development bundler inside a Development Sandbox.

**noVNC Web Ingress**:
The browser access path to an XFCE Desktop Sandbox's graphical desktop.

### Notes and catalogs

**Scratchpad**:
The note-capture area of the Sandbox Web Dashboard, containing Idea Notes and Raw Notes.

**Idea Note**:
A Scratchpad note refined with AI and saved after operator review.

**Raw Note**:
A Scratchpad note saved verbatim without AI refinement.

**Repository Catalog**:
The factory's saved list of accessible GitHub repositories available for selection in the Builder.
_Avoid_: Repository Catalog Cache

**Scratchpad Catalog**:
The factory's saved index of Idea Notes and Raw Notes available for browsing in the Scratchpad.
_Avoid_: Scratchpad Catalog Cache
