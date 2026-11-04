# sedutil OPAL Enterprise: SSO and MDM integration for self-encrypting drives

Corporate add-on to [CakesCats PBA](https://github.com/cakescats/sedutil-pba),
the maintained **sedutil** pre-boot authorization image for **TCG OPAL 2.0**
self-encrypting drives. The drives encrypt in hardware, so there is no
performance cost and nothing to license. This repository adds what a company
needs around them:

- **SSO integration.** The company sign-in decides who may open which machine.
  - F2 on the PBA screen hands the request over to SSO through a QR code.
  - The employee scans it with a phone and signs in with Entra ID, Okta,
    Google Workspace, Keycloak or any OpenID Connect provider.
  - The unlock server shows the password to type in.
  - No helpdesk call, no network in the PBA, every unlock in the audit log.
- **MDM integration:** rollout and configuration with Microsoft Intune, Ansible or
  any tool that runs scripts as SYSTEM or root. The script enrols the machine, gets its PBA
  image from the server and turns on locking. It is safe to run again.
- **Unlock server:**
  - a small Flask app with SQLite;
  - per-machine owners and one-time QR codes;
  - rate limiting and an audit log;
  - Docker and a Keycloak demo that starts with one command.

[Русский](README.ru.md)

## How it fits together

```
 PBA (drive's shadow MBR)            phone                      unlock server
 ───────────────────────            ─────                      ─────────────
 F2 → QR: /m/PC-0042?c=<code>  ──►  scan, sign in (SSO)  ──►  check code (HMAC, once)
                                                               check owner, audit
 type the password             ◄──  password shown       ◄──  machine password

 MDM script: enrol PC-0042 ─────────────────────────────────►  store password, build image
             initialSetup, loadPBAimage, enableLockingRange ◄─  PC-0042's PBA image
```

## Start

- [docs/quickstart.ru.md](docs/quickstart.ru.md): step by step from server to QR unlock (Russian).
- [docs/server.md](docs/server.md): run the unlock server, connect the sign-in provider.
- [docs/mdm.md](docs/mdm.md): roll out with Intune, Ansible or another tool.
- [CakesCats PBA docs](https://github.com/cakescats/sedutil-pba/tree/main/docs):
  the PBA itself, the image builder and how the QR code works (`sso.md`).

Demo in two minutes:

```
cd server && docker compose up -d --build
```

## Status

| Part | State |
|---|---|
| SSO integration (OpenID Connect) | works; tested end to end with Keycloak in CI |
| Enrolment and image per machine | works |
| Windows rollout (Intune, PowerShell) | works; tested with a dry run in CI |
| Linux rollout (shell, Ansible) | works; tested against the server in CI with a stand-in drive |
| Google Workspace | needs an MSI package (next) |
| Passwords encrypted at rest, one-time recovery codes | planned |
| TPM-bound machine key, smart cards, NFC, mobile app | planned |

## License

GPL-3.0-or-later, like sedutil and CakesCats PBA.
