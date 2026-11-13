from django import template

register = template.Library()


@register.filter
def phone(value):
    """Format 09171234567 as 0917 123 4567 for easier reading."""
    digits = str(value or '')
    if len(digits) == 11 and digits.isdigit():
        return f'{digits[:4]} {digits[4:7]} {digits[7:]}'
    return digits
