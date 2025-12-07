from typing import Optional
import re


def validate_email(email: str) -> bool:
    """
    Validate email address

    Args:
        email: Email address to validate

    Returns:
        True if valid
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_phone(phone: str) -> bool:
    """
    Validate phone number (Russian format)

    Args:
        phone: Phone number to validate

    Returns:
        True if valid
    """
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone)

    # Check if it's a valid Russian phone number
    # Should be 11 digits starting with 7 or 8
    if len(digits) == 11 and digits[0] in ['7', '8']:
        return True

    # Or 10 digits (without country code)
    if len(digits) == 10:
        return True

    return False


def validate_telegram_id(telegram_id: int) -> bool:
    """
    Validate Telegram ID

    Args:
        telegram_id: Telegram user ID

    Returns:
        True if valid
    """
    # Telegram IDs are positive integers
    return isinstance(telegram_id, int) and telegram_id > 0


def validate_amount(amount: float, min_amount: float = 0.01, max_amount: float = 1000000.0) -> bool:
    """
    Validate payment amount

    Args:
        amount: Amount to validate
        min_amount: Minimum allowed amount
        max_amount: Maximum allowed amount

    Returns:
        True if valid
    """
    try:
        amount_float = float(amount)
        return min_amount <= amount_float <= max_amount
    except (ValueError, TypeError):
        return False


def validate_invoice_id(invoice_id: str) -> bool:
    """
    Validate invoice ID format

    Args:
        invoice_id: Invoice ID to validate

    Returns:
        True if valid
    """
    # Invoice ID should be alphanumeric and not empty
    return bool(invoice_id) and invoice_id.replace('-', '').replace('_', '').isalnum()


def validate_image_file(file_size: int, max_size: int = 20 * 1024 * 1024) -> tuple[bool, Optional[str]]:
    """
    Validate image file

    Args:
        file_size: File size in bytes
        max_size: Maximum allowed file size (default 20MB)

    Returns:
        Tuple of (is_valid, error_message)
    """
    if file_size <= 0:
        return False, "Файл пустой"

    if file_size > max_size:
        max_mb = max_size / (1024 * 1024)
        return False, f"Файл слишком большой. Максимальный размер: {max_mb:.0f}MB"

    return True, None


def sanitize_text(text: str, max_length: int = 1000) -> str:
    """
    Sanitize user input text

    Args:
        text: Text to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized text
    """
    if not text:
        return ""

    # Remove leading/trailing whitespace
    text = text.strip()

    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length]

    # Remove potential HTML/script tags (basic sanitization)
    text = re.sub(r'<[^>]+>', '', text)

    return text


def validate_package_id(package_id: int, available_packages: list) -> bool:
    """
    Validate package ID against available packages

    Args:
        package_id: Package ID to validate
        available_packages: List of available package IDs

    Returns:
        True if valid
    """
    return package_id in available_packages


def normalize_phone_number(phone: str) -> str:
    """
    Normalize phone number to international format for YooKassa

    Args:
        phone: Phone number in any format

    Returns:
        Normalized phone number starting with +7 (or original if invalid)
    """
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone)

    # Convert 8 to 7 for Russian numbers
    if digits.startswith('8') and len(digits) == 11:
        digits = '7' + digits[1:]

    # Add +7 prefix if missing
    if len(digits) == 10:
        digits = '7' + digits

    # Add + prefix
    if digits.startswith('7') and len(digits) == 11:
        return '+' + digits

    # Return original if can't normalize
    return phone
