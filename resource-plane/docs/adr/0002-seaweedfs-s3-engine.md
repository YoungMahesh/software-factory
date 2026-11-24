# SeaweedFS as S3-Compatible Storage Engine

We selected SeaweedFS (`chrislusf/seaweedfs`) as the underlying engine for object storage. Compared to heavyweight AWS emulators or MinIO, SeaweedFS provides full S3 API support with negligible memory consumption, fast cold starts, and native Docker support, making it well-suited for lightweight local and edge environments.
