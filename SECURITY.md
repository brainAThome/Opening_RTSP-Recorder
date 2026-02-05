# Security Policy - RTSP Recorder v1.2.0 BETA

## Biometric Data Handling

### Current Implementation (v1.2.0)

This integration stores **face embeddings** (128-dimensional numerical vectors) for person recognition. These embeddings are:

- **Stored locally** in SQLite within the Home Assistant config directory
- **Not transmitted** to external services (all processing is local)
- **Binary format** (BLOB) - not human-readable

### Tables with Biometric Data

| Table | Purpose | Data |
|-------|---------|------|
| `face_embeddings` | Person recognition | 128-dim face vectors |
| `negative_embeddings` | Exclude matches | 128-dim face vectors |
| `ignored_embeddings` | Global ignore list | 128-dim face vectors |

### Security Model

1. **Physical Access Control**: Data resides on user's Home Assistant hardware
2. **File System Permissions**: SQLite file inherits HA config permissions
3. **Network Isolation**: No external API calls for biometric matching
4. **User Consent**: Users explicitly add faces for recognition

### Planned Improvements (v1.3+)

- [ ] **SEC-002**: Optional encryption for embedding BLOB fields using Fernet (AES-128)
- [ ] Key derivation from HA secret or user-provided passphrase
- [ ] Migration tool for existing unencrypted databases

### Responsible Disclosure

If you discover a security vulnerability:
1. **Do not** open a public issue
2. Contact the maintainer directly via GitHub
3. Allow 90 days for remediation before public disclosure

### GDPR Compliance Notes

Face embeddings are considered **biometric data** under GDPR Art. 9. Users processing data of EU residents should:
- Obtain explicit consent before adding faces
- Document the purpose (home security/automation)
- Enable deletion via the WebSocket API (`delete_person`)
- Be aware embeddings persist until explicitly deleted

---

*Last updated: 2026-02-03 | Version: 1.2.0 BETA*
