"""
UTM parameters parser for Telegram deep links.

This module provides utilities to parse UTM parameters from Telegram bot /start commands.

Deep link format: https://t.me/bot_username?start=PARAMETER
The PARAMETER can encode UTM data in various formats.

Supported formats:
1. Short format (recommended for Yandex.Direct - 64 char limit):
   Format: source_medium_campaign_content_term
   Example: yd_cpc_sellers_banner1
   Link: https://t.me/bot?start=yd_cpc_sellers_banner1

2. Full UTM format (for other ad platforms):
   Format: utm_source-SOURCE_utm_medium-MEDIUM_utm_campaign-CAMPAIGN...
   Example: utm_source-yandex_utm_medium-cpc_utm_campaign-sellers
   Link: https://t.me/bot?start=utm_source-yandex_utm_medium-cpc_utm_campaign-sellers
"""

import logging
from typing import Dict, Optional
import urllib.parse


logger = logging.getLogger(__name__)


# Mapping of short codes to full values for compactness
UTM_SHORTCUTS = {
    # Sources
    'yd': 'yandex_direct',
    'rsya': 'yandex_rsya',
    'vk': 'vk_ads',
    'tg': 'telegram_ads',
    'fb': 'facebook',
    'ig': 'instagram',
    'gg': 'google',

    # Mediums
    'cpc': 'cpc',
    'cpm': 'cpm',
    'cpa': 'cpa',
    'retarget': 'retargeting',
    'organic': 'organic',
    'referral': 'referral',
    'social': 'social',
    'banner': 'banner',
}


def parse_utm_from_start_param(param: Optional[str]) -> Dict[str, Optional[str]]:
    """
    Parse UTM parameters from /start command parameter.

    Args:
        param: Parameter from /start command (e.g., "yd_cpc_sellers_banner1")

    Returns:
        Dict with UTM parameters: {
            'utm_source': str or None,
            'utm_medium': str or None,
            'utm_campaign': str or None,
            'utm_content': str or None,
            'utm_term': str or None
        }

    Examples:
        >>> parse_utm_from_start_param("yd_cpc_sellers_banner1")
        {'utm_source': 'yandex_direct', 'utm_medium': 'cpc',
         'utm_campaign': 'sellers', 'utm_content': 'banner1', 'utm_term': None}

        >>> parse_utm_from_start_param("utm_source-yandex_utm_campaign-test")
        {'utm_source': 'yandex', 'utm_medium': None,
         'utm_campaign': 'test', 'utm_content': None, 'utm_term': None}

        >>> parse_utm_from_start_param(None)
        {'utm_source': None, 'utm_medium': None,
         'utm_campaign': None, 'utm_content': None, 'utm_term': None}
    """
    result = {
        'utm_source': None,
        'utm_medium': None,
        'utm_campaign': None,
        'utm_content': None,
        'utm_term': None
    }

    if not param:
        return result

    try:
        # Try full UTM format first (utm_source-value_utm_medium-value)
        if 'utm_' in param:
            result.update(_parse_full_utm_format(param))
        else:
            # Use short format (source_medium_campaign_content_term)
            result.update(_parse_short_utm_format(param))

        logger.info(f"Parsed UTM from param '{param}': {result}")

    except Exception as e:
        logger.error(f"Error parsing UTM from param '{param}': {e}", exc_info=True)

    return result


def _parse_short_utm_format(param: str) -> Dict[str, Optional[str]]:
    """
    Parse short UTM format: source_medium_campaign_content_term

    Args:
        param: Short format parameter (e.g., "yd_cpc_sellers_banner1_keyword")

    Returns:
        Dict with parsed UTM parameters
    """
    result = {
        'utm_source': None,
        'utm_medium': None,
        'utm_campaign': None,
        'utm_content': None,
        'utm_term': None
    }

    parts = param.split('_')

    if len(parts) >= 1:
        # Source
        source = parts[0]
        result['utm_source'] = UTM_SHORTCUTS.get(source, source)

    if len(parts) >= 2:
        # Medium
        medium = parts[1]
        result['utm_medium'] = UTM_SHORTCUTS.get(medium, medium)

    if len(parts) >= 3:
        # Campaign
        result['utm_campaign'] = parts[2]

    if len(parts) >= 4:
        # Content
        result['utm_content'] = parts[3]

    if len(parts) >= 5:
        # Term (join remaining parts with underscore)
        result['utm_term'] = '_'.join(parts[4:])

    return result


def _parse_full_utm_format(param: str) -> Dict[str, Optional[str]]:
    """
    Parse full UTM format: utm_source-value_utm_medium-value_...

    Args:
        param: Full format parameter (e.g., "utm_source-yandex_utm_medium-cpc")

    Returns:
        Dict with parsed UTM parameters
    """
    result = {
        'utm_source': None,
        'utm_medium': None,
        'utm_campaign': None,
        'utm_content': None,
        'utm_term': None
    }

    # Split by underscore to get utm_key-value pairs
    pairs = param.split('_')

    for pair in pairs:
        if '-' not in pair:
            continue

        key, value = pair.split('-', 1)

        # URL decode value
        value = urllib.parse.unquote(value)

        if key == 'utm_source':
            result['utm_source'] = value
        elif key == 'utm_medium':
            result['utm_medium'] = value
        elif key == 'utm_campaign':
            result['utm_campaign'] = value
        elif key == 'utm_content':
            result['utm_content'] = value
        elif key == 'utm_term':
            result['utm_term'] = value

    return result


def generate_utm_link(
    bot_username: str,
    utm_source: str,
    utm_medium: Optional[str] = None,
    utm_campaign: Optional[str] = None,
    utm_content: Optional[str] = None,
    utm_term: Optional[str] = None,
    use_short_format: bool = True
) -> str:
    """
    Generate a Telegram deep link with UTM parameters.

    Args:
        bot_username: Bot username (without @)
        utm_source: UTM source
        utm_medium: UTM medium
        utm_campaign: UTM campaign
        utm_content: UTM content
        utm_term: UTM term
        use_short_format: Use short format (recommended for character limits)

    Returns:
        Telegram deep link URL

    Examples:
        >>> generate_utm_link("mybot", "yandex_direct", "cpc", "sellers", use_short_format=True)
        'https://t.me/mybot?start=yd_cpc_sellers'

        >>> generate_utm_link("mybot", "yandex", "cpc", use_short_format=False)
        'https://t.me/mybot?start=utm_source-yandex_utm_medium-cpc'
    """
    if use_short_format:
        param = _generate_short_utm_param(
            utm_source, utm_medium, utm_campaign, utm_content, utm_term
        )
    else:
        param = _generate_full_utm_param(
            utm_source, utm_medium, utm_campaign, utm_content, utm_term
        )

    return f"https://t.me/{bot_username}?start={param}"


def _generate_short_utm_param(
    source: str,
    medium: Optional[str] = None,
    campaign: Optional[str] = None,
    content: Optional[str] = None,
    term: Optional[str] = None
) -> str:
    """Generate short format UTM parameter."""
    # Reverse lookup for shortcuts
    reverse_shortcuts = {v: k for k, v in UTM_SHORTCUTS.items()}

    parts = []

    # Add source (use shortcut if available)
    parts.append(reverse_shortcuts.get(source, source))

    # Add medium
    if medium:
        parts.append(reverse_shortcuts.get(medium, medium))

        # Add campaign only if medium exists
        if campaign:
            parts.append(campaign)

            # Add content only if campaign exists
            if content:
                parts.append(content)

                # Add term only if content exists
                if term:
                    parts.append(term)

    return '_'.join(parts)


def _generate_full_utm_param(
    source: str,
    medium: Optional[str] = None,
    campaign: Optional[str] = None,
    content: Optional[str] = None,
    term: Optional[str] = None
) -> str:
    """Generate full format UTM parameter."""
    pairs = []

    if source:
        pairs.append(f"utm_source-{urllib.parse.quote(source)}")
    if medium:
        pairs.append(f"utm_medium-{urllib.parse.quote(medium)}")
    if campaign:
        pairs.append(f"utm_campaign-{urllib.parse.quote(campaign)}")
    if content:
        pairs.append(f"utm_content-{urllib.parse.quote(content)}")
    if term:
        pairs.append(f"utm_term-{urllib.parse.quote(term)}")

    return '_'.join(pairs)
