# Unlock server

A small Flask app (`server/`) with a SQLite database:

- it signs users in with OpenID Connect;
- it checks the PBA's QR codes and shows the drive password to allowed users;
- it enrols machines for the rollout scripts;
- it keeps an audit log.

## Try it

```
cd server
docker compose up -d --build
```

This starts Keycloak with users `alice` / `alice` and `bob` / `bob`, and the
server at http://localhost:8000 with the enrolment token `demo-enroll-token`.
Enrol a machine with the Linux script and a fake drive, as the tests do,
or build an image by hand with `cakes-builder.py --sso-url http://localhost:8000`
and add it with `manage.py add <image>.machine.json --password <drive password> --owners alice@example.com`.

## Run it for real

The server needs HTTPS: the session cookie is only sent over HTTPS when
`PUBLIC_URL` starts with `https://`. Put it behind Caddy or nginx and run the
container:

```
docker build -t cakes-unlock server/
docker run -d --name cakes-unlock -p 127.0.0.1:8000:8000 -v cakes-unlock:/data \
    -e PUBLIC_URL=https://unlock.corp.com \
    -e SECRET_KEY=$(openssl rand -hex 32) \
    -e OIDC_ISSUER=... -e OIDC_CLIENT_ID=... -e OIDC_CLIENT_SECRET=... \
    -e ENROLL_TOKEN=$(openssl rand -hex 24) -e DEFAULT_OWNERS='*@corp.com' \
    cakes-unlock
```

The Docker image downloads a released PBA image and `cakes-builder.py` and
checks them by SHA-256. Change the four `ARG` lines in `server/Dockerfile` to
the release you roll out.

| Variable | Meaning |
|---|---|
| `PUBLIC_URL` | The server's address as phones reach it. It goes into the QR codes, so it can't change later without new images. |
| `SECRET_KEY` | Signs the session cookie. |
| `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` | The sign-in provider. The redirect URI to register is `<PUBLIC_URL>/auth/callback`. |
| `OIDC_METADATA_URL` | Only when the server reaches the provider at another address than browsers do. |
| `ENROLL_TOKEN` | What the rollout scripts send. Enrolment is off without it. |
| `DEFAULT_OWNERS` | Who may unlock newly enrolled machines: `user@corp.com`, `*@corp.com`, `*`, or a comma separated list. |
| `UNLOCK_DB` | The SQLite file, `/data/unlock.db` in the container. |

## Sign-in providers

The server needs a verified email address from the provider. It matches
that address against the machine's owners.

- **Microsoft Entra ID:**
  - Register an app as a web platform, with redirect URI `https://unlock.corp.com/auth/callback`.
  - Create a client secret.
  - Add `email` as an optional claim of the ID token.
  - Issuer: `https://login.microsoftonline.com/<tenant id>/v2.0`.
- **Okta:**
  - Create a web app integration with the same redirect URI.
  - Issuer: `https://<org>.okta.com` (or your authorization server).
- **Google Workspace:**
  - Create an OAuth client of type web application in Google Cloud.
  - Issuer: `https://accounts.google.com`.
  - Anyone with a Google account can sign in, so keep the owners rules on your domain (`*@corp.com`).
- **Keycloak, Authentik, Zitadel and others:** any OpenID Connect provider
  with discovery works.

## Managing machines

```
docker exec -it cakes-unlock python manage.py list
docker exec -it cakes-unlock python manage.py owners PC-0042 alice@corp.com,bob@corp.com
docker exec -it cakes-unlock python manage.py audit --limit 100
```

## What protects what

- **QR codes.** A code is signed with the machine key and accepted once. The
  key sits in the PBA image, so whoever has the drive can make codes for it.
  A code alone gives nothing: the password is only shown after a sign-in by
  an owner of that machine.
- **Wrong codes.** After 20 wrong codes in an hour the server stops
  answering for that machine.
- **Passwords.** The database holds the drive passwords in plain text, like
  a recovery key escrow. Treat the server and its backups as sensitive as
  the drives. Encrypting them at rest and one-time recovery codes are on the
  roadmap.
- **The enrolment token.** It can add or replace machines, so a stolen token
  could re-enrol a machine with a password of its choice, but it can't read
  passwords. Rotate it after a rollout.
