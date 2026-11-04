# Быстрый старт: разблокировка по QR-коду

Здесь по шагам описано, как пройти путь от пустого сервера до момента, когда
сотрудник открывает диск, отсканировав QR-код телефоном.

Понадобятся:

- сервер с Docker, доступный с телефонов сотрудников;
- компьютер с OPAL-диском;
- файлы из [релиза CakesCats PBA](https://github.com/cakescats/sedutil-pba/releases/latest):
  `cakes-pba-*-default.img.gz`, `cakes-builder.py`, `sedutil-cli`
  (`-linux-x86_64` или `-windows-x64.exe`).

## 1. Адрес сервера

Сначала решите, по какому адресу телефоны будут открывать сервер, например
`https://unlock.company.ru`. **Этот адрес попадает внутрь образа PBA.**
Если его поменять, придётся заново собрать и загрузить образы. Для пробы в
офисной сети подойдёт `http://192.168.1.10:8000`. Адрес `localhost` не
годится: телефон его не откроет.

## 2. Сервер разблокировки

```bash
git clone https://github.com/cakescats/sedutil-opal-enterprise
cd sedutil-opal-enterprise/server
```

**Проба с готовым Keycloak.** В `docker-compose.yml` и
`keycloak/realm-cakes.json` замените `localhost` на IP сервера:

- `KC_HOSTNAME`, `OIDC_ISSUER`, `PUBLIC_URL` в compose;
- `redirectUris`, `webOrigins` в realm.

Затем:

```bash
docker compose up -d --build
```

Тестовые пользователи: `alice` / `alice` и `bob` / `bob`. Токен регистрации:
`demo-enroll-token`.

**Рабочий вариант** со своим SSO (Entra ID, Okta, Google) и HTTPS описан в
[server.md](server.md). Главное:

- `PUBLIC_URL` — тот самый адрес из шага 1;
- у провайдера SSO зарегистрируйте redirect URI `<PUBLIC_URL>/auth/callback`.

## 3. Образ для компьютера

Есть два способа, выберите один.

**А. Вручную, для одной-двух машин:**

```bash
python3 cakes-builder.py build -i cakes-pba-1.20.0-cakes.2-default.img.gz -o pc-001.img \
    --sso-url https://unlock.company.ru --machine-id PC-001 \
    --set "title=Компания — вход в систему"
```

`--machine-id` — любое имя машины из латиницы, цифр и `. _ -`. Можно также
добавить свой логотип: `--logo logo.png`. Рядом с образом появится
`pc-001.img.machine.json` с ключом машины. Передайте его на сервер и никуда
не публикуйте:

```bash
docker compose cp pc-001.img.machine.json unlock:/tmp/
docker compose exec unlock python manage.py add /tmp/pc-001.img.machine.json \
    --password '<пароль диска>' --owners ivanov@company.ru
```

Пароль диска — тот, что вы зададите в шаге 4.

**Б. Через MDM или скрипт, для парка машин.** Скрипт сам придумает пароль,
зарегистрирует машину и получит её образ с сервера:

```bash
sudo ./enable-cakes-pba.sh --server https://unlock.company.ru --token <токен> \
    --owners ivanov@company.ru
```

Он же выполнит шаг 4. Для Windows и Intune — `Enable-CakesPBA.ps1`, см.
[mdm.md](mdm.md).

## 4. Загрузка на диск (для способа А)

Запишите PSID с наклейки диска. Затем:

```bash
sudo sedutil-cli --initialSetup '<пароль диска>' /dev/nvme0
sudo sedutil-cli --loadPBAimage '<пароль диска>' pc-001.img /dev/nvme0
sudo sedutil-cli --enableLockingRange 0 '<пароль диска>' /dev/nvme0
```

На Windows диск называется `\\.\PhysicalDrive0`, команды запускаются от
администратора. После этого **выключите компьютер полностью**.

## 5. Проверка

1. Включите компьютер. Появится экран PBA и строка «Forgot the password? F2…».
2. Нажмите **F2**: на экране QR-код, а под ним имя машины и код вида
   `ABCD-EFGH-IJKL-MNOP`.
3. Отсканируйте QR телефоном и войдите корпоративным аккаунтом. Страница
   покажет пароль.
4. Введите пароль в PBA. Диск откроется, загрузится система.

Если камеры нет, откройте адрес сервера в любом браузере и введите имя
машины и код вручную. Каждый код срабатывает один раз: для следующей
попытки снова нажмите F2.

## Управление

```bash
docker compose exec unlock python manage.py list                 # машины
docker compose exec unlock python manage.py owners PC-001 a@company.ru,b@company.ru
docker compose exec unlock python manage.py audit                # кто и когда открывал
```

Кто может открывать машину, задаётся так:

- `user@company.ru` — один сотрудник;
- `*@company.ru` — любой сотрудник домена;
- список через запятую.
