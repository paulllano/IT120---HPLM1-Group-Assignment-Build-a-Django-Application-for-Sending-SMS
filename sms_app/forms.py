import re

from django import forms
from django.core.exceptions import ValidationError

# Longest message we allow: 3 SMS parts of 153 characters each.
MAX_MESSAGE_LENGTH = 459


def normalize_ph_mobile(value):
    """
    Accept common ways of writing a Philippine mobile number and return
    the 11-digit local format (09XXXXXXXXX).

    Accepted: 09171234567, 0917 123 4567, 0917-123-4567,
              +639171234567, 639171234567, 9171234567
    """
    cleaned = re.sub(r'[\s\-().]', '', value or '')

    if cleaned.startswith('+63'):
        cleaned = '0' + cleaned[3:]
    elif cleaned.startswith('63') and len(cleaned) == 12:
        cleaned = '0' + cleaned[2:]
    elif cleaned.startswith('9') and len(cleaned) == 10:
        cleaned = '0' + cleaned

    if not re.fullmatch(r'09\d{9}', cleaned):
        raise ValidationError(
            'Enter a valid Philippine mobile number, like 09171234567 or +639171234567.',
            code='invalid_phone',
        )
    return cleaned


class SMSForm(forms.Form):
    recipient = forms.CharField(
        label='Recipient phone number',
        max_length=20,
        error_messages={'required': 'Enter the recipient’s phone number.'},
        widget=forms.TextInput(attrs={
            'placeholder': '09171234567',
            'inputmode': 'tel',
            'autocomplete': 'tel',
        }),
    )
    message = forms.CharField(
        label='Message',
        max_length=MAX_MESSAGE_LENGTH,
        error_messages={
            'required': 'Write a message before sending.',
            'max_length': f'Keep the message under {MAX_MESSAGE_LENGTH} characters (3 SMS parts).',
        },
        widget=forms.Textarea(attrs={
            'rows': 5,
            'placeholder': 'Type your message…',
            'maxlength': MAX_MESSAGE_LENGTH,
        }),
    )

    def clean_recipient(self):
        return normalize_ph_mobile(self.cleaned_data['recipient'])
