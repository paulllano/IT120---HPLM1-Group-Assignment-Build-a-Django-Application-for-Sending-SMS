"""
Automated tests for the SMS app. Run with:  python manage.py test

SMS Gateway is never called for real here: `requests.request` is replaced with
a mock, so the tests are free and work offline.
"""
from unittest import mock

import requests
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .forms import SMSForm, normalize_ph_mobile
from .models import SMSMessage
from .services import (
    ConfigurationError,
    NetworkError,
    ProviderError,
    SmsGateBackend,
    to_e164,
)

GATE_USER, GATE_PASS, GATE_DEVICE = 'GATEUSER', 'gate-secret-pass', 'device-abc'


def fake_response(status_code=200, json_data=None, json_error=False):
    response = mock.Mock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 400
    if json_error:
        response.json.side_effect = ValueError('not json')
    else:
        response.json.return_value = json_data
    return response


def gate_message(state='Pending', error=None, message_id='msg-123'):
    recipient = {'phoneNumber': '+639171234567', 'state': state}
    if error:
        recipient['error'] = error
    return {'id': message_id, 'state': state, 'isHashed': False, 'isEncrypted': False,
            'recipients': [recipient], 'states': {}}


# --------------------------------------------------------------------- forms

class PhoneNumberValidationTests(TestCase):
    def test_accepts_common_formats(self):
        for value in ['09171234567', '0917 123 4567', '0917-123-4567',
                      '+639171234567', '639171234567', '9171234567', '+63 917 123 4567']:
            with self.subTest(value=value):
                self.assertEqual(normalize_ph_mobile(value), '09171234567')

    def test_rejects_invalid_numbers(self):
        for value in ['12345', '0817123456', '091712345678', '08171234567', 'abcdefghijk', '+1 555 123 4567']:
            with self.subTest(value=value):
                form = SMSForm(data={'recipient': value, 'message': 'Hello'})
                self.assertFalse(form.is_valid())
                self.assertIn('recipient', form.errors)


class SMSFormTests(TestCase):
    def test_valid_form(self):
        form = SMSForm(data={'recipient': '09171234567', 'message': 'Hello'})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['recipient'], '09171234567')

    def test_empty_phone_number(self):
        form = SMSForm(data={'recipient': '', 'message': 'Hello'})
        self.assertFalse(form.is_valid())
        self.assertIn('Enter the recipient', form.errors['recipient'][0])

    def test_empty_message(self):
        form = SMSForm(data={'recipient': '09171234567', 'message': ''})
        self.assertFalse(form.is_valid())
        self.assertIn('Write a message', form.errors['message'][0])

    def test_whitespace_only_message(self):
        form = SMSForm(data={'recipient': '09171234567', 'message': '    \n  '})
        self.assertFalse(form.is_valid())
        self.assertIn('message', form.errors)

    def test_message_too_long(self):
        form = SMSForm(data={'recipient': '09171234567', 'message': 'a' * 460})
        self.assertFalse(form.is_valid())
        self.assertIn('message', form.errors)


# ---------------------------------------------------------- SMS Gateway for Android

@mock.patch('sms_app.services.requests.request')
class SmsGateBackendTests(TestCase):
    def backend(self, device_id=GATE_DEVICE):
        return SmsGateBackend(username=GATE_USER, password=GATE_PASS, device_id=device_id,
                              base_url='https://api.sms-gate.app/3rdparty/v1', timeout=5)

    def test_converts_numbers_to_international_format(self, mock_request):
        self.assertEqual(to_e164('09171234567'), '+639171234567')

    def test_successful_send(self, mock_request):
        mock_request.return_value = fake_response(202, gate_message('Pending'))
        result = self.backend().send('09171234567', 'Hello from IT 120')

        self.assertEqual(result.provider_message_id, 'msg-123')
        self.assertEqual(result.provider_status, 'Pending')
        self.assertEqual(result.status, SMSMessage.Status.SUBMITTED)

        method, url = mock_request.call_args.args
        self.assertEqual((method, url), ('post', 'https://api.sms-gate.app/3rdparty/v1/messages'))
        kwargs = mock_request.call_args.kwargs
        self.assertEqual(kwargs['auth'], (GATE_USER, GATE_PASS))
        self.assertEqual(kwargs['json'], {
            'textMessage': {'text': 'Hello from IT 120'},
            'phoneNumbers': ['+639171234567'],
            'withDeliveryReport': True,
            'deviceId': GATE_DEVICE,
        })

    def test_device_id_and_sim_are_optional(self, mock_request):
        mock_request.return_value = fake_response(202, gate_message())
        self.backend(device_id='').send('09171234567', 'Hi')
        self.assertNotIn('deviceId', mock_request.call_args.kwargs['json'])
        self.assertNotIn('simNumber', mock_request.call_args.kwargs['json'])

    def test_sim_number_is_sent_when_set(self, mock_request):
        mock_request.return_value = fake_response(202, gate_message())
        SmsGateBackend(username=GATE_USER, password=GATE_PASS, sim_number=2).send('09171234567', 'Hi')
        self.assertEqual(mock_request.call_args.kwargs['json']['simNumber'], 2)

    def test_missing_credentials(self, mock_request):
        with self.assertRaises(ConfigurationError) as ctx:
            SmsGateBackend(username='', password='')
        self.assertIn('SMSGATE_USERNAME', str(ctx.exception))
        mock_request.assert_not_called()

    def test_wrong_credentials(self, mock_request):
        mock_request.return_value = fake_response(401, {'message': 'Unauthorized'})
        with self.assertRaises(ConfigurationError) as ctx:
            self.backend().send('09171234567', 'Hi')
        self.assertIn('username or password', str(ctx.exception))
        self.assertNotIn(GATE_PASS, str(ctx.exception))

    def test_rejected_request(self, mock_request):
        mock_request.return_value = fake_response(400, {'message': 'invalid phone number'})
        with self.assertRaises(ProviderError) as ctx:
            self.backend().send('09171234567', 'Hi')
        self.assertIn('invalid phone number', str(ctx.exception))

    def test_error_never_echoes_password(self, mock_request):
        mock_request.return_value = fake_response(400, {'message': f'bad auth {GATE_PASS}'})
        with self.assertRaises(ProviderError) as ctx:
            self.backend().send('09171234567', 'Hi')
        self.assertNotIn(GATE_PASS, str(ctx.exception))

    def test_server_error_and_rate_limit(self, mock_request):
        for code in (500, 503, 429):
            with self.subTest(code=code):
                mock_request.return_value = fake_response(code, json_error=True)
                with self.assertRaises(ProviderError):
                    self.backend().send('09171234567', 'Hi')

    def test_ok_response_without_id_is_an_error(self, mock_request):
        mock_request.return_value = fake_response(200, {'message': 'something odd'})
        with self.assertRaises(ProviderError):
            self.backend().send('09171234567', 'Hi')

    def test_network_errors(self, mock_request):
        cases = ((requests.Timeout(), 'too long'),
                 (requests.ConnectionError(), 'Couldn’t reach SMS Gateway'))
        for exc, text in cases:
            with self.subTest(exc=type(exc).__name__):
                mock_request.side_effect = exc
                with self.assertRaises(NetworkError) as ctx:
                    self.backend().send('09171234567', 'Hi')
                self.assertIn(text, str(ctx.exception))

    def test_fetch_status_maps_all_states(self, mock_request):
        expected = {
            'Pending': SMSMessage.Status.SUBMITTED,
            'Processed': SMSMessage.Status.SUBMITTED,
            'Cancelling': SMSMessage.Status.SUBMITTED,
            'Sent': SMSMessage.Status.SENT,
            'Delivered': SMSMessage.Status.DELIVERED,
            'Failed': SMSMessage.Status.FAILED,
            'Cancelled': SMSMessage.Status.FAILED,
        }
        for state, status in expected.items():
            with self.subTest(state=state):
                mock_request.return_value = fake_response(200, gate_message(state))
                self.assertEqual(self.backend().fetch_status('msg-123').status, status)
        method, url = mock_request.call_args.args
        self.assertEqual((method, url), ('get', 'https://api.sms-gate.app/3rdparty/v1/messages/msg-123'))

    def test_failure_reason_is_reported(self, mock_request):
        mock_request.return_value = fake_response(200, gate_message('Failed', error='RESULT_ERROR_NO_SERVICE'))
        result = self.backend().fetch_status('msg-123')
        self.assertEqual(result.status, SMSMessage.Status.FAILED)
        self.assertEqual(result.error, 'RESULT_ERROR_NO_SERVICE')

    def test_unknown_message(self, mock_request):
        mock_request.return_value = fake_response(404, {'message': 'message not found'})
        with self.assertRaises(ProviderError):
            self.backend().fetch_status('nope')


# --------------------------------------------------------------------- views

@override_settings(SMS_PROVIDER='smsgate', SMSGATE_USERNAME=GATE_USER,
                   SMSGATE_PASSWORD=GATE_PASS, SMSGATE_DEVICE_ID=GATE_DEVICE)
class SendViewTests(TestCase):
    url = reverse('sms_app:send')

    def test_form_page_loads_with_csrf_token(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'csrfmiddlewaretoken')
        self.assertContains(response, 'Recipient phone number')
        self.assertContains(response, 'Send SMS')

    def test_empty_phone_number_is_rejected(self):
        response = self.client.post(self.url, {'recipient': '', 'message': 'Hello'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter the recipient')
        self.assertEqual(SMSMessage.objects.count(), 0)

    def test_empty_message_is_rejected(self):
        response = self.client.post(self.url, {'recipient': '09171234567', 'message': ''})
        self.assertContains(response, 'Write a message before sending.')
        self.assertEqual(SMSMessage.objects.count(), 0)

    def test_invalid_phone_number_is_rejected(self):
        response = self.client.post(self.url, {'recipient': '12345', 'message': 'Hello'})
        self.assertContains(response, 'Enter a valid Philippine mobile number')
        self.assertEqual(SMSMessage.objects.count(), 0)

    @mock.patch('sms_app.services.requests.request')
    def test_successful_send_confirms_submission_only(self, mock_request):
        mock_request.return_value = fake_response(202, gate_message('Pending'))
        response = self.client.post(self.url, {'recipient': '+63 917 123 4567', 'message': 'Hello'}, follow=True)

        self.assertRedirects(response, self.url)
        self.assertContains(response, 'Message submitted to SMS Gateway')
        self.assertContains(response, 'Delivery isn’t confirmed yet')
        self.assertNotContains(response, 'delivered')

        sms = SMSMessage.objects.get()
        self.assertEqual(sms.recipient, '09171234567')
        self.assertEqual(sms.provider, 'smsgate')
        self.assertEqual(sms.status, SMSMessage.Status.SUBMITTED)
        self.assertEqual(sms.provider_message_id, 'msg-123')

    @override_settings(SMSGATE_PASSWORD='')
    def test_missing_credentials(self):
        response = self.client.post(self.url, {'recipient': '09171234567', 'message': 'Hello there'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SMSGATE_USERNAME and SMSGATE_PASSWORD')
        self.assertContains(response, 'Hello there')  # the user's text is kept
        sms = SMSMessage.objects.get()
        self.assertEqual(sms.status, SMSMessage.Status.FAILED)

    @mock.patch('sms_app.services.requests.request')
    def test_incorrect_credentials_do_not_expose_password(self, mock_request):
        mock_request.return_value = fake_response(401, {'message': f'Invalid password {GATE_PASS}'})
        response = self.client.post(self.url, {'recipient': '09171234567', 'message': 'Hello'})
        self.assertContains(response, 'SMS Gateway rejected the username or password')
        self.assertNotContains(response, GATE_PASS)
        self.assertNotIn(GATE_PASS, SMSMessage.objects.get().error_message)

    @mock.patch('sms_app.services.requests.request')
    def test_network_error(self, mock_request):
        mock_request.side_effect = requests.ConnectionError()
        response = self.client.post(self.url, {'recipient': '09171234567', 'message': 'Hello'})
        self.assertContains(response, 'Couldn’t reach SMS Gateway')
        self.assertEqual(SMSMessage.objects.get().status, SMSMessage.Status.FAILED)

    @mock.patch('sms_app.services.requests.request')
    def test_provider_rejection(self, mock_request):
        mock_request.return_value = fake_response(400, {'message': 'The number format is invalid.'})
        response = self.client.post(self.url, {'recipient': '09171234567', 'message': 'Hello'})
        self.assertContains(response, 'SMS Gateway rejected the message')
        self.assertEqual(SMSMessage.objects.get().status, SMSMessage.Status.FAILED)

    @override_settings(SMS_PROVIDER='console')
    def test_test_mode_sends_nothing(self):
        with mock.patch('sms_app.services.requests.request') as mock_request:
            response = self.client.post(self.url, {'recipient': '09171234567', 'message': 'Hello'}, follow=True)
            mock_request.assert_not_called()
        self.assertContains(response, 'Test mode')
        self.assertEqual(SMSMessage.objects.get().provider, 'console')

    @override_settings(SMS_PROVIDER='nonsense')
    def test_unknown_provider(self):
        response = self.client.post(self.url, {'recipient': '09171234567', 'message': 'Hello'})
        self.assertContains(response, 'Unknown SMS_PROVIDER')

    def test_csrf_protection_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(self.url, {'recipient': '09171234567', 'message': 'Hello'})
        self.assertEqual(response.status_code, 403)


@override_settings(SMS_PROVIDER='smsgate', SMSGATE_USERNAME=GATE_USER,
                   SMSGATE_PASSWORD=GATE_PASS, SMSGATE_DEVICE_ID=GATE_DEVICE)
class HistoryViewTests(TestCase):
    def setUp(self):
        self.submitted = SMSMessage.objects.create(
            recipient='09171234567', body='Pending one', provider='smsgate',
            status=SMSMessage.Status.SUBMITTED, provider_message_id='msg-111', provider_status='Pending')
        self.failed = SMSMessage.objects.create(
            recipient='09181234567', body='Failed one', provider='smsgate',
            status=SMSMessage.Status.FAILED, error_message='Couldn’t reach SMS Gateway.')

    def test_history_groups_messages_by_number(self):
        response = self.client.get(reverse('sms_app:history'))
        conversations = response.context['conversations']
        # Newest conversation first, with its latest message and status.
        self.assertEqual([c['recipient'] for c in conversations], ['09181234567', '09171234567'])
        self.assertEqual(conversations[0]['last_body'], 'Failed one')
        self.assertEqual(conversations[0]['last_status'], SMSMessage.Status.FAILED)
        self.assertEqual(response.context['counts']['total'], 2)
        self.assertEqual(response.context['counts']['failed'], 1)
        # Both numbers appear in the list, formatted for reading.
        self.assertContains(response, '0918 123 4567')
        self.assertContains(response, '0917 123 4567')

    def test_newest_conversation_is_opened_by_default(self):
        response = self.client.get(reverse('sms_app:history'))
        self.assertEqual(response.context['selected'], '09181234567')
        self.assertEqual([m.body for m in response.context['thread']], ['Failed one'])
        self.assertContains(response, 'Couldn’t reach SMS Gateway.')  # failure reason shown

    def test_select_conversation(self):
        response = self.client.get(reverse('sms_app:history'), {'to': '09171234567'})
        self.assertEqual(response.context['selected'], '09171234567')
        self.assertEqual([m.body for m in response.context['thread']], ['Pending one'])
        self.assertContains(response, 'Check status')

    def test_thread_is_oldest_first(self):
        SMSMessage.objects.create(recipient='09171234567', body='Second one', provider='smsgate',
                                  status=SMSMessage.Status.SENT)
        response = self.client.get(reverse('sms_app:history'), {'to': '09171234567'})
        self.assertEqual([m.body for m in response.context['thread']], ['Pending one', 'Second one'])

    def test_unknown_number_falls_back_to_newest(self):
        response = self.client.get(reverse('sms_app:history'), {'to': '<script>'})
        self.assertEqual(response.context['selected'], '09181234567')

    def test_status_guide_is_shown(self):
        response = self.client.get(reverse('sms_app:history'))
        self.assertContains(response, 'Not yet confirmed on the phone.')
        self.assertContains(response, 'Sent to network')
        self.assertContains(response, 'Delivered')

    def test_new_message_link_prefills_send_form(self):
        response = self.client.get(reverse('sms_app:send'), {'to': '09171234567'})
        self.assertContains(response, 'value="09171234567"')

    def test_empty_history(self):
        SMSMessage.objects.all().delete()
        response = self.client.get(reverse('sms_app:history'))
        self.assertContains(response, 'No messages yet')

    @mock.patch('sms_app.services.requests.request')
    def test_check_status_updates_message(self, mock_request):
        mock_request.return_value = fake_response(200, gate_message('Sent', message_id='msg-111'))
        response = self.client.post(reverse('sms_app:refresh_status', args=[self.submitted.pk]), follow=True)
        self.assertContains(response, 'The mobile network accepted the message')
        self.submitted.refresh_from_db()
        self.assertEqual(self.submitted.status, SMSMessage.Status.SENT)
        self.assertEqual(self.submitted.provider_status, 'Sent')

    def test_sent_message_can_still_become_delivered(self):
        sms = SMSMessage.objects.create(recipient='09171234567', body='Hi', provider='smsgate',
                                        status=SMSMessage.Status.SENT, provider_message_id='msg-123')
        self.assertTrue(sms.can_refresh)
        sms.status = SMSMessage.Status.DELIVERED
        self.assertFalse(sms.can_refresh)

    @mock.patch('sms_app.services.requests.request')
    def test_check_status_delivered(self, mock_request):
        sms = SMSMessage.objects.create(recipient='09171234567', body='Hi', provider='smsgate',
                                        status=SMSMessage.Status.SENT, provider_message_id='msg-123')
        mock_request.return_value = fake_response(200, gate_message('Delivered'))
        response = self.client.post(reverse('sms_app:refresh_status', args=[sms.pk]), follow=True)
        self.assertContains(response, 'Delivered: 09171234567 received the message.')
        sms.refresh_from_db()
        self.assertEqual(sms.status, SMSMessage.Status.DELIVERED)

    @mock.patch('sms_app.services.requests.request')
    def test_check_status_failed_shows_reason(self, mock_request):
        sms = SMSMessage.objects.create(recipient='09171234567', body='Hi', provider='smsgate',
                                        status=SMSMessage.Status.SUBMITTED, provider_message_id='msg-123')
        mock_request.return_value = fake_response(
            200, gate_message('Failed', error='RESULT_ERROR_NO_SERVICE'))
        response = self.client.post(reverse('sms_app:refresh_status', args=[sms.pk]), follow=True)
        self.assertContains(response, 'RESULT_ERROR_NO_SERVICE')
        sms.refresh_from_db()
        self.assertEqual(sms.error_message, 'RESULT_ERROR_NO_SERVICE')

    def test_history_shows_delivered_in_status_guide(self):
        SMSMessage.objects.create(recipient='09171234567', body='Hi', provider='smsgate',
                                  status=SMSMessage.Status.DELIVERED, provider_message_id='msg-1')
        response = self.client.get(reverse('sms_app:history'))
        self.assertEqual(response.context['counts']['delivered'], 1)
        self.assertContains(response, 'pill-delivered')

    def test_check_status_requires_post(self):
        response = self.client.get(reverse('sms_app:refresh_status', args=[self.submitted.pk]))
        self.assertEqual(response.status_code, 405)

    def test_check_status_ignores_external_redirects(self):
        with mock.patch('sms_app.services.requests.request') as mock_request:
            mock_request.return_value = fake_response(200, gate_message('Pending', message_id='msg-111'))
            response = self.client.post(reverse('sms_app:refresh_status', args=[self.submitted.pk]),
                                        {'next': 'https://evil.example.com/'})
        self.assertRedirects(response, reverse('sms_app:history'))
