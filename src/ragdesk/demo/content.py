"""Sample help-centre documents for the demo assistants (a fictional outdoor-gear shop), in English
and Spanish."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class DemoAssistant:
    name: str
    language: str
    welcome: str
    fallback: str
    suggested_questions: list[str]
    documents: dict[str, str] = field(default_factory=dict)


ENGLISH_DOCUMENTS: dict[str, str] = {
    "products.md": """# What you can order

## Catalogue

Northwind Outdoor sells tents, sleeping bags, backpacks, waterproof jackets and repair kits. You
can order any of them on our website and choose standard or express delivery at checkout.

## Out of stock items

When an item is out of stock you can ask to be told by email as soon as it is available again.
""",
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

SPANISH_DOCUMENTS: dict[str, str] = {
    "productos.md": """# Qué puedo pedir

## Catálogo

Esto es lo que puedo pedir en Northwind Outdoor: carpas, sacos de dormir, mochilas, chaquetas
impermeables y kits de reparación. Puedes pedir cualquiera de ellos en nuestra web y elegir entrega
estándar o exprés al pagar.

## Productos agotados

Cuando un producto está agotado puedes pedir que te avisemos por correo en cuanto vuelva a estar
disponible.
""",
    "devoluciones-y-reembolsos.md": """# Devoluciones y reembolsos

## Plazo de devolución

Puedes devolver cualquier producto sin usar dentro de los 30 días posteriores a la entrega. Debe
estar en su empaque original. Las carpas que se han montado se consideran usadas.

## Cómo funcionan los reembolsos

El reembolso vuelve al medio de pago original en un plazo de 5 días hábiles después de que
recibamos el paquete. Los gastos de envío solo se reembolsan si el producto llegó dañado o
enviamos uno equivocado.

## Cambios

Inicia un cambio desde la página de Pedidos. Enviamos el reemplazo en cuanto el transportista
escanea la devolución, así que no tienes que esperar al reembolso.
""",
    "envios.md": """# Envíos

## Tiempos de entrega

Los pedidos hechos antes de las 2 p. m. salen el mismo día hábil. La entrega estándar tarda de 3 a
5 días hábiles. La entrega exprés tarda de 1 a 2 días hábiles y es gratis en pedidos superiores a
150 euros.

## Pedidos internacionales

Enviamos a la Unión Europea, el Reino Unido y Suiza. Los gastos de aduana fuera de la Unión
Europea los paga el comprador en la entrega.

## Seguimiento

Recibes un enlace de seguimiento por correo cuando el paquete sale de nuestro almacén. El
seguimiento puede tardar hasta 24 horas en actualizarse.
""",
    "reparaciones-y-garantia.md": """# Reparaciones y garantía

## Garantía

Todos los productos tienen dos años de garantía contra defectos de fabricación. El desgaste normal,
como las cremalleras gastadas tras años de uso, no está cubierto.

## Servicio de reparación gratuito

Envíanos tu chaqueta, mochila o saco de dormir y reparamos costuras, cremalleras y hebillas sin
costo durante el periodo de garantía. Después, las reparaciones cuestan entre 10 y 35 euros según
el trabajo.

## Instrucciones de cuidado

Lava las chaquetas impermeables a 30 grados con un detergente técnico y vuelve a
impermeabilizarlas con un spray una vez al año. Nunca uses suavizante, obstruye la membrana
impermeable.
""",
}

DEMO_ASSISTANTS: tuple[DemoAssistant, ...] = (
    DemoAssistant(
        name="Northwind Outdoor help",
        language="en",
        welcome="Hi! I'm the Northwind Outdoor assistant. Ask me about orders, returns or repairs.",
        fallback=(
            "I could not find that in our help articles. Write to help@northwind.example "
            "and the team will answer you."
        ),
        suggested_questions=[
            "What can I order?",
            "How long does standard delivery take?",
            "How do refunds work?",
            "What does the warranty cover?",
        ],
        documents=ENGLISH_DOCUMENTS,
    ),
    DemoAssistant(
        name="Northwind Outdoor ayuda",
        language="es",
        welcome=(
            "¡Hola! Soy el asistente de Northwind Outdoor. "
            "Pregúntame por pedidos, devoluciones o reparaciones."
        ),
        fallback=(
            "No encontré eso en nuestros artículos de ayuda. Escribe a ayuda@northwind.example "
            "y el equipo te responderá."
        ),
        suggested_questions=[
            "¿Qué puedo pedir?",
            "¿Cuánto tarda la entrega estándar?",
            "¿Cómo funcionan los reembolsos?",
            "¿Qué cubre la garantía?",
        ],
        documents=SPANISH_DOCUMENTS,
    ),
)
