"""
M-Pesa deposit requests. This is a stub with the real interface.

Production: call Safaricom Daraja's STK push with the *business's own*
shortcode and credentials (from a secrets store keyed by tenant id), then mark
the booking confirmed in the callback view. The platform never holds the money.
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class StkRequest:
    accepted: bool
    message: str
    checkout_request_id: str = ""


def request_deposit(booking):
    tenant = booking.tenant
    if not tenant.mpesa_shortcode:
        logger.info("Tenant %s has no M-Pesa shortcode yet; booking %s held for manual payment", tenant.slug, booking.ref)
        return StkRequest(False, "This business has not connected M-Pesa yet. Pay the deposit at the front desk.")

    logger.info(
        "STK push (stub): KES %s to %s %s for booking %s, phone %s",
        booking.deposit_kes, tenant.get_mpesa_type_display(), tenant.mpesa_shortcode, booking.ref, booking.customer.phone,
    )
    return StkRequest(True, "Check your phone and enter your M-Pesa PIN to pay the deposit.", f"stub-{booking.ref}")
