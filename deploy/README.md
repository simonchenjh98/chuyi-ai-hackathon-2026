# Isolated Chuyi cloud deployment

This is the GOTC deployment workflow adapted to a separate Chuyi service. Existing
GOTC and September event paths, accounts, scores and databases are not copied.

`deploy.py` only builds a local release package unless `--execute` is supplied:

```powershell
python deploy/deploy.py
python -B -m unittest discover -s deploy -p 'test_install.py'
python deploy/deploy.py --execute
```

The deployment uses these independent resources:

| Resource | Chuyi value |
| --- | --- |
| Application/data root | `/opt/chuyi-hackathon` |
| Ownership marker | `/opt/chuyi-hackathon/.chuyi-owned` |
| System user and service | `chuyi-hackathon` |
| Loopback port | `127.0.0.1:5275` |
| Public URL | `https://8.141.114.201/chuyi/` |
| Nginx managed block | `CHUYI HACKATHON MANAGED LOCATION` |

The service sets `CHUYI_HOST`, `CHUYI_PORT`, `CHUYI_DATA_DIR`,
`CHUYI_BASE_PATH` and `CHUYI_PUBLIC_ORIGIN`. It runs Python 3.12 as an unprivileged
system user. The release is read-only; only its private data directory is writable.
Nginx preserves `/chuyi` when proxying, so session cookie paths remain isolated.

Commit this project's source before publishing. The script records its Git commit
SHA, content digest, release archive SHA-256, URL and health result in
`.runtime/deployment.json`. If this folder has no project-owned Git repository,
the source content SHA-256 identifies the release instead.

The release includes only allowlisted public HTML/CSS/JS, approved assets and
downloads, and backend Python source. It excludes data, SQLite databases, private
access files, tests, deployment scripts and internal documents.

The deploy tool uses local Paramiko with the existing verified SSH identity at
`~/.ssh/realtalk_ecs` and strict host-key checking using `~/.ssh/known_hosts`.
The key is never copied to the release or included in logs, shell arguments or
source files. No remote changes occur without `--execute`.

Before activation the installer checks that the existing `gotc-hackathon`,
`etown-hackathon`, `nginx`, `realtalk-api` and `dapm` services are active. It rejects
an occupied port on first deployment, foreign application roots, ambiguous Nginx
server blocks, unmanaged `/chuyi` routes and concurrent Nginx edits.

The installer backs up Nginx, this service's prior unit and any Chuyi SQLite
database. It switches only this service, checks its local board API, validates and
reloads Nginx, checks the public board API, and confirms the original services are
still active. Failure restores this service's prior release/unit and the Nginx
edit. Existing application data is preserved. If Nginx changed concurrently, the
installer leaves that newer edit untouched and reports the saved backup for review.

The initial admin access file is transferred through SFTP into the ignored local
`.runtime/admin-access.txt`; the code is never printed. Keep `.runtime/` out of Git,
public downloads and source delivery packages. Generate separate judge invitations
through the Chuyi administrator interface.
