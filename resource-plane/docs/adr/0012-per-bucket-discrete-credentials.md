# Per-Bucket Discrete Access Credentials in SeaweedFS

Each S3 object storage resource provisioned in the control plane receives its own cryptographically generated Access Key ID and Secret Access Key. The control plane updates the SeaweedFS S3 IAM configuration to restrict each credential pair exclusively to read, write, and list operations within its assigned bucket, preventing external apps from accessing other projects' data.
