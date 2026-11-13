# SMS Sender: Django Application for Sending SMS

A Django web application for sending SMS messages to Philippine mobile numbers. The user enters a recipient number and a message. The app validates both, sends the message through an SMS service's API and reports the result. It keeps a chat-style history of every attempt and can check whether each message was sent and delivered.

The app sends real SMS messages through **[SMS Gateway for Android](https://sms-gate.app)** (which dispatches messages from an Android phone through a cloud REST API) and also includes a built-in **test mode** (`console`) for offline development and validation testing.

**Course:** IT 120 – Integrative Programming and Technologies, 1st Semester SY 2026–2027
**Activity:** Group Assignment – Build a Django Application for Sending SMS

---

## 1. Application objectives

- **Purpose:** Send an SMS from a web browser, and see clearly whether the message was submitted, accepted by the mobile network, delivered to the phone or rejected.
- **Users:** Anyone who needs to send a quick text to a Philippine mobile number, such as a teacher sending reminders, a small business sending notices or a student organisation sending announcements.
- **SMS functionality:** The app connects to an SMS service's REST API to submit messages. It saves each attempt and can ask the service for the latest status later.

### Choosing an SMS service

The activity names Twilio as an example provider. We didn't use Twilio because messages from its international numbers are often filtered by Philippine carriers, and a Twilio trial only sends to verified numbers.

Instead, we use **SMS Gateway for Android**. Its Android app turns a phone into an SMS gateway, and our Django app calls its cloud API at `api.sms-gate.app`. Messages go out from the phone's own SIM, so Philippine carriers (Globe, Smart, DITO) deliver them like any normal text. The only cost is the phone's regular load. It also sends **delivery reports**, so the app can show when a message has actually reached the recipient's phone.

Switching between live sending (`smsgate`) and test mode (`console`) means changing one line in `.env` (`SMS_PROVIDER`). The rest of the app stays the same.

---

## 2. Group members and responsibilities

| Member | Role | Responsibilities |
|---|---|---|
| **Marriane B. Barbin** | Group Leader | Django project setup, views, URL routing and application logic |
| **Jurls Earl Miguel B. Velasco** | Member | User interface, templates and CSS, forms, input validation and user feedback |
| **Paul Matthew F. Llano** | Member | SMS Gateway service integration, automated and manual testing, documentation and demonstration video |

All members reviewed the complete application and can explain its workflow.

---

## 3. Main features

**Core**
- SMS form with recipient number, message and **Send SMS** button.
- Server-side validation of the phone number and message, with a clear error under each field.
- Sending through the SMS Gateway API, with a success or failure message after every attempt.
- Error handling for: missing number, empty message, invalid number format, missing or incorrect credentials, network problems and timeouts, rejection by the service, rate limiting, and service errors.
- The app says **"Submitted"** when the service accepts the request. It only says **"Delivered"** when the recipient's phone has confirmed it.

**Additional features**
- **Chat-style message history:** every attempt, including failures, grouped by phone number like a phone's messaging app. Each message shows its time and a coloured status, and failed messages show the reason. **New message** opens the Send form with that number filled in.
- **Status guide:** a strip at the top of History that explains each status and shows how many messages have it.
- **Delivery tracking:** a *Check status* button asks the service for the latest status. A message can move from Submitted to Sent to network to **Delivered**.
- **Character and SMS-part counter:** shows characters used and how many SMS parts the message will use. It detects emoji and other special characters, which lower the limit from 160 to 70 characters per SMS.
- **Live message preview:** shows the message as the recipient will see it.
- **Test mode:** `SMS_PROVIDER=console` saves messages without sending them, for development and for demonstrating validation.
- **Double-send protection:** the Send button is disabled while a message is sending, and the page redirects after a successful send so refreshing it doesn't send the message again.
- **Keeps your place:** after choosing a conversation, checking a status or sending, the page stays where you were instead of jumping to the top.

### Status meanings

| Status in the app | SMS Gateway state | Meaning |
|---|---|---|
| Submitted | Pending, Processed | The service accepted the message and is sending it. |
| Sent to network | Sent | The mobile network accepted it. Not yet confirmed on the phone. |
| Delivered | Delivered | The recipient's phone confirmed it received the message. |
| Failed | Failed, Cancelled | The message was not sent. The reason is shown under it. |

---

## 4. SMS workflow

1. The user opens the app (the **Send SMS** page).
2. The user enters a recipient phone number, for example `09171234567` or `+63 917 123 4567`.
3. The user writes a message. The counter and preview update while typing.
4. The user selects **Send SMS**. Django checks the CSRF token and validates the form:
   - Phone number: required, must be a valid PH mobile number, and is stored as `09XXXXXXXXX`.
   - Message: required, not just spaces, and at most 459 characters (3 SMS parts).
   - If anything is invalid, the form is shown again with an error under the field. Nothing is sent.
5. The app sends the message to the configured service:
   - SMS Gateway: `POST https://api.sms-gate.app/3rdparty/v1/messages` with Basic Auth, the number in international format (`+639…`), the text, and a request for a delivery report.
6. The app saves the attempt and shows the result:
   - Accepted: "Message submitted to SMS Gateway… Delivery isn't confirmed yet."
   - Error: an explanation of what went wrong. The form keeps the typed message so the user can try again.
7. On **History**, the user picks a phone number to open its conversation and selects **Check status** on a message. The app calls `GET /messages/{id}` and updates the status, for example to **Delivered**.

```
Browser ──POST form──▶ Django view ──validate──▶ SMSForm
                           │                       │ invalid → show errors
                           ▼ valid
                    services.get_backend()   ← chosen by SMS_PROVIDER in .env
                           │
               ┌───────────┴───────────┐
               ▼                       ▼
         SmsGateBackend          ConsoleBackend
        (Android phone,          (test mode,
         cloud API)               nothing sent)
               │
               ▼
 SMSMessage saved to database ──▶ success / error message ──▶ History page
```

---

## 5. Technologies and dependencies

| Technology | Purpose |
|---|---|
| Python 3.12+ (developed on 3.14) | Programming language |
| Django 6.1 | Web framework: views, forms, templates, ORM, CSRF protection, admin |
| SQLite | Database for message history (Django's default) |
| requests | HTTP client for calling the SMS Gateway API |
| python-dotenv | Loads secrets from the `.env` file into environment variables |
| HTML, CSS, vanilla JavaScript | User interface, character counter, preview |
| SMS Gateway for Android (cloud API v1) | Sends SMS from an Android phone's SIM |

The full list of pinned versions is in [`requirements.txt`](requirements.txt).

---

## 6. Project structure

```
sms_project/                  ← repository root
├── manage.py
├── requirements.txt
├── .env.example              ← safe template; copy to .env
├── .gitignore
├── README.md
├── sms_project/              ← Django project configuration
│   ├── settings.py           ← reads secrets from environment variables
│   └── urls.py
└── sms_app/                  ← the SMS application
    ├── models.py             ← SMSMessage (history and status)
    ├── forms.py              ← SMSForm and phone number validation
    ├── services.py           ← SMS Gateway and test-mode backends
    ├── views.py              ← send, history, check status
    ├── urls.py
    ├── admin.py
    ├── tests.py              ← automated test suite
    ├── templatetags/         ← phone-number display filter
    ├── templates/sms_app/    ← base.html, send.html, history.html
    └── static/sms_app/       ← css/style.css, js/compose.js, js/history.js, js/keep-scroll.js
```

---

## 7. Installation and setup

**Requirements:** Python 3.12 or newer, Git.

```bash
# 1. Clone the repository
git clone <repository-url>
cd sms_project

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows (PowerShell):
#   If you see "running scripts is disabled on this system", run this once:
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
.venv\Scripts\Activate.ps1
# Windows (Command Prompt):
.venv\Scripts\activate.bat
# macOS / Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env file from the template
# Windows:
copy .env.example .env
# macOS / Linux:
cp .env.example .env

# 5. Create the database tables
python manage.py migrate
```

Generate a secret key and paste it into `DJANGO_SECRET_KEY` in `.env`:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## 8. Configuring the SMS service

### Option A: SMS Gateway for Android (live SMS sending)

1. On an Android phone (Android 5.0 or newer) with load or an unlimited-text promo, install **SMS Gateway for Android** from <https://sms-gate.app>.
2. Open the app, allow it to send SMS, and turn on **Cloud server**.
3. The app shows a **Username**, **Password** and **Device ID**. Copy them into `.env`:

```env
SMS_PROVIDER=smsgate
SMSGATE_USERNAME=paste-username
SMSGATE_PASSWORD=paste-password
SMSGATE_DEVICE_ID=paste-device-id     # optional with only one phone
```

4. Keep the phone switched on, connected to the internet, and with the app running while you send.
5. Restart the Django server after changing `.env`.

### Option B: Test mode

Set `SMS_PROVIDER=console` in `.env`. A banner shows that test mode is on, and messages are printed in the terminal instead of being sent.

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | Yes | Django's cryptographic signing key |
| `DJANGO_DEBUG` | No | `True` for development (default), `False` in production |
| `DJANGO_ALLOWED_HOSTS` | No | Comma-separated host names (default `127.0.0.1,localhost`) |
| `SMS_PROVIDER` | No | `smsgate` (default) or `console` |
| `SMSGATE_USERNAME` | When provider is `smsgate` | Username shown in the SMS Gateway app |
| `SMSGATE_PASSWORD` | When provider is `smsgate` | Password shown in the SMS Gateway app |
| `SMSGATE_DEVICE_ID` | No | Which phone sends, if several are connected |
| `SMSGATE_SIM_NUMBER` | No | Which SIM sends on a dual-SIM phone (`1` or `2`); blank uses the phone's default SIM |

---

## 9. Running the application

```bash
python manage.py runserver
```

Open <http://127.0.0.1:8000/>.

| Page | URL |
|---|---|
| Send SMS | `/` |
| History | `/history/` |
| Django admin (optional) | `/admin/` (create a user first with `python manage.py createsuperuser`) |

---

## 10. Security

- **Credentials live only in `.env`.** It is listed in `.gitignore` and is never committed. The repository contains only `.env.example`, which has placeholder values.
- `settings.py` reads every secret with `os.environ`. Nothing secret is written in the source code.
- Error messages never contain passwords, API keys or raw service responses. Service text is filtered to replace secrets with `***` before display or logging. Network errors are logged without the request URL, because a URL can contain credentials.
- All forms use Django's **CSRF protection** (`{% csrf_token %}`, `CsrfViewMiddleware`). The automated tests confirm that a POST without a token is rejected (HTTP 403).
- **Check status** accepts POST only, and its redirect target is checked so it can't send users to an outside site.
- Django templates escape all user input automatically, which prevents HTML and script injection.
- Only authorized test recipients (group members' own numbers) were used for testing.
- No credentials, `.env` contents or dashboard pages are shown in the demonstration video.

---

## 11. Testing

### Automated tests

The test suite replaces the SMS service with mocks, so it sends nothing, costs nothing and runs offline:

```bash
python manage.py test sms_app
```

| Area | What is tested |
|---|---|
| Phone validation | Accepts `09…`, `+63…`, `63…`, `9…` with spaces or dashes. Rejects short, long and non-PH numbers. |
| Message validation | Empty, whitespace-only, and over 459 characters. |
| SMS Gateway backend | Correct endpoint, Basic Auth and JSON body; `+63` conversion; optional device ID and SIM number; missing and wrong credentials; rejected request; password never appears in errors; 429 and 5xx; response without an ID; timeout and no connection; mapping of all 7 states including Delivered; failure reason; unknown message. |
| Views | Form and CSRF token render; empty, invalid and missing-credential cases; success says "submitted", not "delivered"; network and service errors; test mode; unknown provider; CSRF enforced. |
| History | Grouping by number, newest conversation first, selecting a conversation, oldest-first thread, status guide and counts, New message pre-fill, empty state, Check status updates (including Delivered and failure reasons), POST-only, safe redirect. |

### Manual test cases (from the activity guide)

| # | Test case | Input | Expected result | Actual result |
|---|---|---|---|---|
| 1 | Valid number and message | `09XXXXXXXXX` (member's phone), "Hello from IT 120" | "Message submitted to SMS Gateway… Delivery isn't confirmed yet."; SMS arrives on the phone | ✅ Pass |
| 2 | Empty phone number | blank, "Hello" | Rejected: "Enter the recipient's phone number." | ✅ Pass |
| 3 | Empty message | `09171234567`, blank | Rejected: "Write a message before sending." | ✅ Pass |
| 4 | Invalid phone number | `12345` | Rejected: "Enter a valid Philippine mobile number…" | ✅ Pass |
| 5 | Missing credentials | `SMSGATE_PASSWORD=` blank | "SMS sending isn't set up yet. Add SMSGATE_USERNAME and SMSGATE_PASSWORD…"; nothing secret shown | ✅ Pass |
| 6 | Incorrect credentials | wrong password in `.env` | "SMS Gateway rejected the username or password…" | ✅ Pass |
| 7 | Network error | Wi-Fi turned off on the computer | "Couldn't reach SMS Gateway. Check your internet connection…" | ✅ Pass |
| 8 | Successful provider response | same as #1, then **Check status** | Status goes Submitted → Sent to network → **Delivered** only after the phone confirms | ✅ Pass |

---

## 12. Known limitations

- **The phone must be online:** SMS Gateway sends through a real Android phone, so the phone must be on, connected to the internet, and running the app. If it's offline, messages stay *Submitted* until it reconnects.
- **Sender is a personal number:** recipients see the group phone's number, not a brand name. Carrier fair-use limits on personal SIMs also apply.
- **Status updates are manual:** the user selects *Check status*. Automatic updates through webhooks would need a public URL, which a local development server doesn't have.
- **Philippine numbers only:** validation accepts PH mobile numbers (`09XXXXXXXXX`) only.
- **One recipient per message:** the service supports several recipients per call, but the form sends to one number to keep the app simple.
- **Message length:** limited to 459 characters (3 SMS parts).
- **No user accounts:** anyone with access to the running app can send messages. This is fine for a local class project, but a public deployment would need login and rate limiting.
- **Development server only:** the app runs with `runserver` and SQLite and isn't configured for production hosting.
