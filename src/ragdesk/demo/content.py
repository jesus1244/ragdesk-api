"""Sample help-centre documents for the demo assistant (a fictional outdoor-gear shop)."""

DEMO_BOT_NAME = "Northwind Outdoor help"
DEMO_WELCOME = "Hi! I'm the Northwind Outdoor assistant. Ask me about orders, returns or repairs."

DEMO_DOCUMENTS: dict[str, str] = {
    "returns-and-refunds.md": """# Returns and refunds

## Return window

You can return any unused item within 30 days of delivery. Items must be in their original
packaging. Tents that have been pitched are considered used.

## How refunds work

Refunds go back to the original payment method within 5 business days after we receive the parcel.
Shipping costs are refunded only when the item arrived damaged or we sent the wrong product.

## Exchanges

Start an exchange from the Orders page. We ship the replacement as soon as the return is scanned
by the carrier, so you do not have to wait for the refund.
""",
    "shipping.md": """# Shipping

## Delivery times

Orders placed before 2 pm ship the same business day. Standard delivery takes 3 to 5 business days.
Express delivery takes 1 to 2 business days and is free for orders above 150 euros.

## International orders

We ship to the European Union, the United Kingdom and Switzerland. Customs fees outside the
European Union are paid by the buyer on delivery.

## Tracking

You receive a tracking link by email when the parcel leaves our warehouse. Tracking updates can
take up to 24 hours to appear.
""",
    "repairs-and-warranty.md": """# Repairs and warranty

## Warranty

Every product has a two-year warranty against manufacturing defects. Normal wear, such as worn
zippers after years of use, is not covered.

## Free repair service

Send us your jacket, backpack or sleeping bag and we repair seams, zippers and buckles for free
during the warranty period. After that, repairs cost between 10 and 35 euros depending on the work.

## Care instructions

Wash waterproof jackets at 30 degrees with a technical detergent and re-proof them with a spray
once a year. Never use fabric softener, it clogs the waterproof membrane.
""",
}
