"""Starter service menus loaded when a business is created. Owners edit them later."""

STARTER_SERVICES = {
    "spa": [
        ("Swedish massage", 60, 4500),
        ("Deep tissue massage", 90, 6500),
        ("Hot stone massage", 75, 6000),
        ("Signature facial", 60, 5000),
        ("Coffee body scrub", 60, 5500),
        ("Steam and sauna", 45, 2000),
    ],
    "barbershop": [
        ("Haircut", 30, 800),
        ("Haircut and beard trim", 45, 1200),
        ("Kids cut", 30, 500),
        ("Hot towel shave", 30, 700),
        ("Dreadlock retwist", 90, 2500),
    ],
    "nail_bar": [
        ("Gel manicure", 60, 1800),
        ("Spa pedicure", 60, 2000),
        ("Acrylic full set", 90, 3500),
        ("Nail art, per set", 30, 1000),
    ],
    "hair_salon": [
        ("Wash and blow-dry", 45, 1500),
        ("Knotless braids, medium", 180, 4500),
        ("Relaxer", 90, 2500),
        ("Deep treatment", 45, 2000),
    ],
    "wellness": [
        ("Physio assessment", 45, 3000),
        ("Physio session", 45, 3500),
        ("Sports massage", 60, 4000),
        ("Cupping therapy", 30, 2500),
    ],
}

DEFAULT_TAGLINES = {
    "spa": "Slow down. Book a treatment in under a minute.",
    "barbershop": "Sharp cuts, no queue. Book your chair.",
    "nail_bar": "Nails done your way. Pick a slot and pay the deposit by M-Pesa.",
    "hair_salon": "Book your stylist and skip the wait.",
    "wellness": "Physio and recovery sessions, booked online.",
}
