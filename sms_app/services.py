"""
SMS provider integration.

Views only talk to `get_backend()`, so switching providers means changing
SMS_PROVIDER in .env, not the views. Two backends are available:

    smsgate    SMS Gateway for Android (https://sms-gate.app): sends from a
               group member's Android phone through the cloud API. Free.
    console    Test mode: nothing is sent.

Every error raised from here is an `SMSError` whose message is safe to show
on screen: it never contains passwords, API keys or raw provider output.
"""
import logging
import uuid
from dataclasses import dataclass

import requests
from django.conf import settings

from .models import SMSMessage

logger = logging.getLogger(__name__)

Status = SMSMessage.Status


# ---------------------------------------------------------------- errors

class SMSError(Exception):
    """Base class. `str(error)` is a user-friendly message."""


class ConfigurationError(SMSError):
    """Missing or rejected credentials, or an unknown provider name."""


class NetworkError(SMSError):
    """We couldn't reach the provider (offline, DNS, timeout)."""


class ProviderError(SMSError):
    """The provider answered but refused or failed the request."""


# ---------------------------------------------------------------- results

@dataclass
class SendResult:
    provider_message_id: str
    provider_status: str      # the provider's own word, e.g. "Pending" or "Delivered"
    status: str               # our SMSMessage.Status value
    network: str = ''
    error: str = ''           # failure reason reported by the provider, if any


def to_e164(number):
    """09171234567 -> +639171234567"""
    return '+63' + number[1:] if number.startswith('0') else number


def http_request(service, method, url, timeout, **kwargs):
    """Make an HTTP call and turn connection problems into friendly NetworkErrors."""
    try:
        return requests.request(method, url, timeout=timeout, **kwargs)
    except requests.Timeout:
        logger.warning('%s request timed out', service)
        raise NetworkError(f'{service} took too long to respond. Check your connection and try again.')
    except requests.ConnectionError:
        # Don't log the exception text: it can contain the URL with credentials.
        logger.warning('Could not connect to %s', service)
        raise NetworkError(f'Couldn’t reach {service}. Check your internet connection and try again.')
    except requests.RequestException as exc:
        logger.warning('%s request failed: %s', service, type(exc).__name__)
        raise NetworkError(f'Something went wrong while contacting {service}. Please try again.')


def read_json(response):
    try:
        return response.json()
    except ValueError:
        return None


def flatten_messages(data):
    """Collect every text message from a nested error response."""
    if isinstance(data, str):
        return [data]
    if isinstance(data, dict):
        return [text for value in data.values() for text in flatten_messages(value)]
    if isinstance(data, list):
        return [text for value in data for text in flatten_messages(value)]
    return []


def summarize(data, secrets=()):
    texts = flatten_messages(data)
    if not texts:
        return 'the response was not understood.'
    summary = ' '.join(texts)
    for secret in secrets:
        if secret:
            summary = summary.replace(secret, '***')
    return summary[:200]


# ---------------------------------------------------------------- SMS Gateway for Android

# SMS Gateway state -> our status. "Delivered" is a real delivery report from the recipient's phone.
SMSGATE_STATUS_MAP = {
    'pending': Status.SUBMITTED,      # queued on the server, waiting for the phone
    'processed': Status.SUBMITTED,    # the phone handed it to Android's SMS system
    'cancelling': Status.SUBMITTED,
    'sent': Status.SENT,              # the mobile network accepted it
    'delivered': Status.DELIVERED,    # the recipient's phone confirmed receipt
    'failed': Status.FAILED,
    'cancelled': Status.FAILED,
}


class SmsGateBackend:
    """
    Sends SMS from an Android phone running the SMS Gateway app, through the
    cloud server at api.sms-gate.app (Basic Auth with the app's username/password).
    """

    name = 'smsgate'
    display_name = 'SMS Gateway'
    refreshable = {Status.SUBMITTED, Status.SENT}  # Sent can still become Delivered

    def __init__(self, username, password, device_id='', sim_number=None, base_url=None, timeout=15):
        if not username or not password:
            raise ConfigurationError(
                'SMS sending isn’t set up yet. Add SMSGATE_USERNAME and SMSGATE_PASSWORD to the .env file '
                'and restart the server.'
            )
        self.auth = (username, password)
        self.device_id = device_id
        self.sim_number = sim_number
        self.base_url = (base_url or settings.SMSGATE_API_URL).rstrip('/')
        self.timeout = timeout

    def send(self, number, message):
        payload = {
            'textMessage': {'text': message},
            'phoneNumbers': [to_e164(number)],
            'withDeliveryReport': True,
        }
        if self.device_id:
            payload['deviceId'] = self.device_id
        if self.sim_number:
            payload['simNumber'] = self.sim_number
        response = http_request(self.display_name, 'post', f'{self.base_url}/messages',
                                self.timeout, json=payload, auth=self.auth)
        return self._parse(response)

    def fetch_status(self, message_id):
        response = http_request(self.display_name, 'get', f'{self.base_url}/messages/{message_id}',
                                self.timeout, auth=self.auth)
        return self._parse(response)

    def _parse(self, response):
        data = read_json(response)

        if response.status_code in (401, 403):
            raise ConfigurationError(
                'SMS Gateway rejected the username or password. '
                'Check SMSGATE_USERNAME and SMSGATE_PASSWORD in your .env file.'
            )
        if response.status_code == 404:
            raise ProviderError('SMS Gateway couldn’t find this message.')
        if response.status_code == 429:
            raise ProviderError('Too many messages in a short time. Wait a minute and try again.')
        if response.status_code >= 500:
            raise ProviderError('SMS Gateway is having problems right now. Try again in a few minutes.')

        if response.ok and isinstance(data, dict) and data.get('id'):
            state = str(data.get('state') or 'Pending')
            recipients = data.get('recipients') or []
            first = recipients[0] if recipients and isinstance(recipients[0], dict) else {}
            # The per-recipient state is the most precise one for a single number.
            state = str(first.get('state') or state)
            return SendResult(
                provider_message_id=str(data['id']),
                provider_status=state,
                status=SMSGATE_STATUS_MAP.get(state.lower(), Status.SUBMITTED),
                error=str(first.get('error') or '')[:200],
            )

        reason = summarize(data, secrets=self.auth)
        logger.warning('SMS Gateway rejected request (HTTP %s): %s', response.status_code, reason)
        raise ProviderError(f'SMS Gateway rejected the message: {reason}')


# ---------------------------------------------------------------- test mode

class ConsoleBackend:
    """
    Test mode. Nothing is sent: the message is printed to the terminal
    running `runserver`. Useful for development and for demonstrating
    validation without a phone.
    """

    name = 'console'
    display_name = 'test mode'
    refreshable = {Status.SUBMITTED}

    def send(self, number, message):
        logger.info('[TEST MODE] SMS to %s: %s', number, message)
        return SendResult(
            provider_message_id=f'test-{uuid.uuid4().hex[:12]}',
            provider_status='Pending',
            status=Status.SUBMITTED,
            network='Test mode',
        )

    def fetch_status(self, message_id):
        # Simulate the network accepting the message.
        return SendResult(provider_message_id=message_id, provider_status='Sent',
                          status=Status.SENT, network='Test mode')


# ---------------------------------------------------------------- factory

BACKENDS = {
    'smsgate': SmsGateBackend,
    'console': ConsoleBackend,
}


def get_backend(name=None):
    name = (name or settings.SMS_PROVIDER).lower()
    if name == 'smsgate':
        return SmsGateBackend(
            username=settings.SMSGATE_USERNAME,
            password=settings.SMSGATE_PASSWORD,
            device_id=settings.SMSGATE_DEVICE_ID,
            sim_number=settings.SMSGATE_SIM_NUMBER,
            base_url=settings.SMSGATE_API_URL,
            timeout=settings.SMS_REQUEST_TIMEOUT,
        )
    if name == 'console':
        return ConsoleBackend()
    raise ConfigurationError(
        f'Unknown SMS_PROVIDER “{name}”. Use “smsgate” or “console” in your .env file.'
    )


def is_refreshable(sms):
    """Whether this message's status can still change, so "Check status" makes sense."""
    backend_class = BACKENDS.get(sms.provider)
    return bool(sms.provider_message_id) and backend_class is not None and sms.status in backend_class.refreshable
