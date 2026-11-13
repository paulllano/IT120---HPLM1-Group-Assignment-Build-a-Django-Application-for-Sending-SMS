from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Max, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import MAX_MESSAGE_LENGTH, SMSForm
from .models import SMSMessage
from .services import SMSError, get_backend


def _sender_label():
    """Who the recipient sees as the sender, shown in the message preview."""
    if settings.SMS_PROVIDER == 'smsgate':
        return 'Our group’s phone'
    return 'Test mode'


def _page_context():
    """Values every page needs."""
    return {
        'test_mode': settings.SMS_PROVIDER == 'console',
        'sender_name': _sender_label(),
    }


def send_sms(request):
    """Show the SMS form (GET) and send the message (POST)."""
    if request.method == 'POST':
        form = SMSForm(request.POST)
        if form.is_valid():
            recipient = form.cleaned_data['recipient']
            body = form.cleaned_data['message']
            provider_name = settings.SMS_PROVIDER

            try:
                backend = get_backend()
                provider_name = backend.name
                result = backend.send(recipient, body)
            except SMSError as exc:
                # Keep a record of the failed attempt, then show the form again
                # with the user's text so they don't have to retype it.
                SMSMessage.objects.create(
                    recipient=recipient,
                    body=body,
                    provider=provider_name,
                    status=SMSMessage.Status.FAILED,
                    error_message=str(exc)[:255],
                )
                messages.error(request, str(exc))
                return render(request, 'sms_app/send.html', {
                    'form': form, 'max_length': MAX_MESSAGE_LENGTH, **_page_context(),
                })

            sms = SMSMessage.objects.create(
                recipient=recipient,
                body=body,
                provider=provider_name,
                status=result.status,
                provider_message_id=result.provider_message_id,
                provider_status=result.provider_status,
                network=result.network,
                error_message=result.error,
            )

            if sms.status == SMSMessage.Status.FAILED:
                reason = f' ({result.error})' if result.error else ''
                messages.error(
                    request, f'{backend.display_name} reported that the message to {recipient} failed{reason}.'
                )
            elif provider_name == 'console':
                messages.success(
                    request,
                    f'Test mode: the message to {recipient} was saved but not sent.',
                )
            else:
                messages.success(
                    request,
                    f'Message submitted to {backend.display_name} for {recipient}. '
                    'Delivery isn’t confirmed yet. Use “Check status” on the History page for updates.',
                )
            # Redirect after a successful POST so refreshing the page doesn't send the SMS twice.
            return redirect('sms_app:send')
    else:
        # "New message" on the History page links here with ?to=<number> to pre-fill the form.
        form = SMSForm(initial={'recipient': request.GET.get('to', '')[:20]})

    return render(request, 'sms_app/send.html', {
        'form': form, 'max_length': MAX_MESSAGE_LENGTH, **_page_context(),
    })


THREAD_LIMIT = 50  # newest messages shown in one conversation


def history(request):
    """Chat-style inbox: one conversation per phone number."""
    counts = SMSMessage.objects.aggregate(
        total=Count('id'),
        submitted=Count('id', filter=Q(status=SMSMessage.Status.SUBMITTED)),
        sent=Count('id', filter=Q(status=SMSMessage.Status.SENT)),
        delivered=Count('id', filter=Q(status=SMSMessage.Status.DELIVERED)),
        failed=Count('id', filter=Q(status=SMSMessage.Status.FAILED)),
    )

    statuses = [
        (SMSMessage.Status.SUBMITTED, 'Submitted', counts['submitted'],
         'The SMS service accepted it and is sending it now.'),
        (SMSMessage.Status.SENT, 'Sent to network', counts['sent'],
         'The carrier (Globe, Smart, DITO) accepted it. Not yet confirmed on the phone.'),
        (SMSMessage.Status.DELIVERED, 'Delivered', counts['delivered'],
         'The recipient’s phone confirmed it received the message.'),
        (SMSMessage.Status.FAILED, 'Failed', counts['failed'],
         'Not sent. The reason is shown under the message.'),
    ]

    # One row per phone number, with its latest message, newest conversation first.
    latest = SMSMessage.objects.filter(recipient=OuterRef('recipient')).order_by('-created_at')
    conversations = list(
        SMSMessage.objects.values('recipient')
        .annotate(
            total=Count('id'),
            last_sent=Max('created_at'),
            last_body=Subquery(latest.values('body')[:1]),
            last_status=Subquery(latest.values('status')[:1]),
        )
        .order_by('-last_sent')
    )

    recipients = [convo['recipient'] for convo in conversations]
    selected = request.GET.get('to', '')
    if selected not in recipients:
        selected = recipients[0] if recipients else ''

    # Oldest at the top, newest at the bottom, like a messaging app.
    thread = []
    if selected:
        newest_first = SMSMessage.objects.filter(recipient=selected).order_by('-created_at')[:THREAD_LIMIT]
        thread = list(reversed(newest_first))

    return render(request, 'sms_app/history.html', {
        'counts': counts,
        'statuses': statuses,
        'conversations': conversations,
        'selected': selected,
        'thread': thread,
        **_page_context(),
    })


@require_POST
def refresh_status(request, pk):
    """Ask the provider for the latest status of one message."""
    sms = get_object_or_404(SMSMessage, pk=pk)

    next_url = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse('sms_app:history')

    if not sms.can_refresh:
        messages.info(request, 'This message already has a final status.')
        return redirect(next_url)

    try:
        backend = get_backend(sms.provider)
        result = backend.fetch_status(sms.provider_message_id)
    except SMSError as exc:
        messages.error(request, f'Couldn’t check the status: {exc}')
        return redirect(next_url)

    sms.status = result.status
    sms.provider_status = result.provider_status
    if result.network:
        sms.network = result.network
    if result.error:
        sms.error_message = result.error
    sms.save(update_fields=['status', 'provider_status', 'network', 'error_message', 'updated_at'])

    Status = SMSMessage.Status
    if sms.status == Status.SUBMITTED:
        messages.info(request, f'Still waiting: {backend.display_name} reports “{result.provider_status}”.')
    elif sms.status == Status.SENT:
        messages.success(request, f'The mobile network accepted the message to {sms.recipient}. '
                                  'Delivery to the phone isn’t confirmed yet.')
    elif sms.status == Status.DELIVERED:
        messages.success(request, f'Delivered: {sms.recipient} received the message.')
    else:
        messages.error(request, f'The message to {sms.recipient} failed '
                                f'({result.error or result.provider_status}).')
    return redirect(next_url)
