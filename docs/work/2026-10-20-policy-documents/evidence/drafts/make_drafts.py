"""Draft item 3.3's policy documents from the term table (evidence/sources.md) only.

A drafting aid kept as provenance (it shows how the minimal pairs of W5 were built). The record is
`data/policies-v1/`: the 12 files there were written by this script on 2026-10-21 and are what the
author read. After that, edit the files, not this script.

W2's outline, one per kind, six sections in order. Sibling pairs are built from ONE shared text with
the condition word placed once in every section (W5, minimal pairs); only the term sentences
differ. Writes {doc_id}.json into argv[1].
"""

import json
import sys
from pathlib import Path

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)


def para(*sentences):
    return " ".join(sentences)


def write(doc_id, title, category, kind, condition, terms, sections):
    record = {
        "doc_id": doc_id,
        "title": title,
        "category": category,
        "policy_kind": kind,
        "condition": condition,
        "terms": terms,
        "text": "\n\n".join(sections),
    }
    (OUT / f"{doc_id}.json").write_text(json.dumps(record, indent=2) + "\n")


# =================================================================================================
# Phones, returns: packaging = opened / unopened (Best Buy: 14 days; $45 opened; no fee unopened)
# =================================================================================================
PHONES_TERM = {
    "unopened": para(
        "Unopened phones can be sent back within 14 days of the day you received them. There is no",
        "restocking fee on an unopened phone, so the refund is the full amount you paid for it.",
    ),
    "opened": para(
        "Opened phones can be sent back within 14 days of the day you received them. A restocking",
        "fee of $45 is taken from the refund for each opened phone, because the device has to be",
        "inspected, cleaned and repackaged before it can be sold again.",
    ),
}
PHONES_REFUND = {
    "unopened": "Once we have checked the unopened phone, we send the full refund to the payment method you used.",
    "opened": "Once we have checked the opened phone, we send the refund, less the restocking fee, to the payment method you used.",
}


def phones_return(v):
    V = v.capitalize()
    return [
        para(
            f"This policy covers {v} phones bought from our store, whether you ordered online or",
            "bought in person.",
            PHONES_TERM[v],
            "The time limit is the same for every colour and storage size, and it counts from the day",
            "the phone reached you, not from the day you placed the order.",
        ),
        "What to send back",
        para(
            f"{V} phones must come back in their original box with every item that came with them,",
            "such as the charging cable, the power adapter, the SIM tool and the printed guides. Pack",
            "the box inside a sturdy shipping carton with enough padding to protect it on the way.",
            "Before you pack it, check that no account, tracking service or payment card is still",
            "linked to the device, and take out any SIM card or memory card you added. We cannot",
            "return cards, cases or accessories left inside the package, and we are not responsible",
            "for personal information left on a device that comes back to us. A phone that arrives",
            "with a cracked screen, liquid damage or missing parts is not accepted and will be shipped",
            "back to you at no cost.",
        ),
        "How to start a return",
        para(
            f"To start a return for {v} phones, sign in to your account, go to your order history and",
            "choose the phone you want to send back. We email you a prepaid shipping label and a",
            "return code to write on the carton, and you can drop the parcel at any shipping point",
            "listed on the label. If you prefer, bring the phone to the service desk in any of our",
            "stores, where a team member checks it with you and hands you a return slip. Keep the",
            "slip or the tracking number until your refund arrives, because it is your record that",
            "the phone was sent back in time.",
        ),
        "Your refund",
        para(
            PHONES_REFUND[v],
            "Refunds usually reach your account within a few business days, depending on your bank.",
            "Payments made with a gift card are refunded to a gift card, and a payment that was split",
            "across several methods is refunded in the same split. If the phone was a gift, the person",
            "who received it can ask for store credit instead. We email you as soon as the refund has",
            "been sent.",
        ),
        "Phones we cannot accept",
        para(
            f"{V} phones that were reported lost or stolen, or that are locked to an account we cannot",
            "remove, are not accepted. Prepaid airtime cards and SIM kits that have been activated",
            "cannot be sent back at all, because they are used up the moment they are activated.",
            "Screen protectors that have been applied, and phone cases that have been cut or marked,",
            "cannot be sent back either.",
        ),
        "Exchanges",
        para(
            f"If you would rather have a different colour or storage size, you can exchange {v} phones",
            "within the same time limit. An exchange follows the same steps as a return, and we ship",
            "the replacement as soon as the original phone has been checked. If the replacement costs",
            "more, you pay the difference; if it costs less, we refund the difference to you. Where the",
            "phone you want is not available, we tell you straight away and you can choose a refund",
            "instead.",
        ),
    ]


for v, terms in (("unopened", ["14 days"]), ("opened", ["14 days", "$45"])):
    write(
        f"policy-return-phones-{v}",
        f"Return Policy - Phones, {v.capitalize()}",
        "phones",
        "return",
        {"axis": "packaging", "value": v},
        terms,
        phones_return(v),
    )

# =================================================================================================
# Laptops, returns: grade = new / renewed (Amazon: 30 days; Renewed 90 days). No bare "new" in the
# shared text: the renewed document may not contain the word at all.
# =================================================================================================
LAPTOPS_TERM = {
    "new": para(
        "New laptops can be sent back within 30 days of the day you received them, for a full",
        "refund.",
    ),
    "renewed": para(
        "Renewed laptops are tested, cleaned and repaired where needed before they are sold, and",
        "they can be sent back within 90 days of the day you received them, for a full refund or a",
        "replacement unit of the same kind.",
    ),
}


def laptops_return(v):
    V = v.capitalize()
    return [
        para(
            f"This policy covers {v} laptops bought from our store, whether you ordered online or",
            "bought in person.",
            LAPTOPS_TERM[v],
            "The time limit counts from the day the laptop reached you, not from the day you placed",
            "the order, and it is the same for every screen size and colour.",
        ),
        "What to send back",
        para(
            f"{V} laptops must come back with the charger, the power cable and every accessory or",
            "guide that came in the box. Use the original packaging if you still have it, or a sturdy",
            "carton with enough padding to stop the laptop moving. Before you pack it, copy any files",
            "you want to keep, sign out of every account, turn off any device tracking and reset the",
            "laptop to its factory settings. We erase every laptop that comes back, but we cannot",
            "recover your files once the laptop has left your hands. A laptop with a cracked screen,",
            "liquid damage, missing keys or signs that it has been taken apart is not accepted and will",
            "be shipped back to you. Remove any stickers or covers you added to the lid.",
        ),
        "How to start a return",
        para(
            f"To start a return for {v} laptops, sign in to your account, go to your order history and",
            "choose the laptop you want to send back. We email you a prepaid shipping label and a",
            "return code to write on the carton, and you can drop the parcel at any shipping point",
            "listed on the label. You can also bring the laptop to the service desk in one of our",
            "stores, where a team member checks it with you before the return is accepted. Keep the",
            "tracking number or the desk slip until your refund arrives.",
        ),
        "Your refund",
        para(
            f"Once the {v} laptop has arrived and passed its check, we send the refund to the payment",
            "method you used. Refunds usually reach your account within a few business days, depending",
            "on your bank. Gift card payments are refunded to a gift card, and a payment split across",
            "several methods is refunded in the same split. We email you as soon as the refund has",
            "been sent, and the email lists every item it covers.",
        ),
        "Items we cannot take back",
        para(
            f"Software licences, digital downloads and subscriptions bought with {v} laptops cannot be",
            "sent back once they have been activated, because they cannot be taken back from the",
            "laptop. A laptop that is locked to an account we cannot remove, or that was reported lost",
            "or stolen, is not accepted. Laptops that have had parts swapped, such as memory or a",
            "storage drive, are accepted only with the original parts put back in place. Accessories",
            "bought in the same order, such as a mouse or a laptop bag, follow the same time limit as",
            "the laptop they were bought with.",
        ),
        "Exchanges",
        para(
            f"If you would rather have a different size or colour, you can exchange {v} laptops within",
            "the same time limit. The exchange follows the same steps as a return, and the replacement",
            "ships as soon as the original laptop has passed its check. If the replacement costs more,",
            "you pay the difference; if it costs less, we refund the difference to you. When the laptop",
            "you want is not available, we tell you straight away and you can choose a refund instead.",
        ),
    ]


for v, terms in (("new", ["30 days"]), ("renewed", ["90 days"])):
    write(
        f"policy-return-laptops-{v}",
        f"Return Policy - Laptops, {v.capitalize()}",
        "laptops",
        "return",
        {"axis": "grade", "value": v},
        terms,
        laptops_return(v),
    )

# =================================================================================================
# Electronics, returns: no condition (Target: 30 days). TVs and headphones.
# =================================================================================================
write(
    "policy-return-electronics",
    "Return Policy - Electronics",
    "electronics",
    "return",
    None,
    ["30 days"],
    [
        para(
            "This policy covers TVs and headphones bought from our store, whether you ordered online",
            "or bought in person. TVs and headphones can be sent back within 30 days of the day you",
            "received them, for a full refund or an exchange. The time limit counts from the day the",
            "item reached you, or from the day a TV was delivered to your home, not from the day you",
            "placed the order.",
        ),
        "What to send back",
        para(
            "A TV must come back with its stand or feet, the remote control, the power cable, the",
            "screws and any wall-mount parts that came with it. Headphones must come back with their",
            "charging case if they have one, the cable, the spare ear tips and the carry pouch. Please",
            "use the original carton for a TV if you still have it, because a screen is easily damaged",
            "in transit. For hygiene reasons, headphones that show signs of heavy use, such as worn or",
            "torn ear cushions or residue on the ear tips, are refused and sent back to you, so wipe",
            "them clean and pack them in their case before you send them. A TV with a cracked or",
            "scratched screen cannot be accepted.",
        ),
        "How to start a return",
        para(
            "To start a return, sign in to your account, go to your order history and choose the",
            "item. Headphones travel with the prepaid label we email you, and you can drop the parcel",
            "at any shipping point listed on the label. Large TVs are collected from your home: once",
            "you start the return, we contact you to arrange a pickup time, and the driver brings",
            "packing material if you no longer have the carton. You can also bring either item to the",
            "service desk in one of our stores, where a team member checks it with you. Unplug the TV",
            "and coil its cables before the driver arrives, so that the pickup is quick.",
        ),
        "Your refund",
        para(
            "When the item has reached us and passed its check, the refund goes back to the payment",
            "method you used. Most banks show it within a few business days. Gift card payments are",
            "refunded to a gift card, and a payment that was split across several methods is refunded",
            "in the same split. If a TV was delivered and set up by our team, the delivery and setup",
            "service is not refunded. We email you as soon as the refund has been sent.",
        ),
        "Items we cannot take back",
        para(
            "Mounting work done by an outside installer, cables that were cut to length, and apps or",
            "films bought through the TV cannot be sent back. A TV that was mounted on a wall and",
            "shows damage from the mounting is not accepted, and neither are headphones whose cable",
            "or headband has been cut or bent out of shape. Items damaged by a power surge or by being",
            "dropped are not accepted either. Headphones bought in the same order as a TV can still be",
            "sent back on their own.",
        ),
        "Exchanges",
        para(
            "You can exchange a TV for a different screen size, or headphones for another colour,",
            "within the same time limit. The exchange follows the same steps as a return. If the",
            "replacement costs more you pay the difference, and if it costs less we refund the",
            "difference to the payment method you used. For a large TV, the driver who collects the",
            "first set can bring the replacement on the same visit.",
        ),
    ],
)

# =================================================================================================
# Furniture, returns: packaging = opened / unopened (IKEA: 365 days unopened; 180 days opened;
# proof of purchase on both). Chairs and desks.
# =================================================================================================
FURNITURE_TERM = {
    "unopened": para(
        "Unopened furniture, still in its original packaging, can be sent back within 365 days of",
        "the day you received it, with your proof of purchase, for a full refund.",
    ),
    "opened": para(
        "Opened furniture, including pieces you have already put together, can be sent back within",
        "180 days of the day you received it, with your proof of purchase, for a full refund.",
    ),
}


def furniture_return(v):
    V = v.capitalize()
    return [
        para(
            f"This policy covers {v} chairs and desks bought from our store, whether you ordered",
            "online or bought in person.",
            FURNITURE_TERM[v],
            "The time limit counts from the day the furniture reached you, or from the day it was",
            "delivered to your home.",
        ),
        "What to send back",
        para(
            f"{V} furniture must come back with every part, screw, bracket and tool that came with it,",
            "and with the assembly guide if you still have it. Pieces that belong to a set must come",
            "back as a complete set, so a desk with a matching drawer unit, or a pair of chairs sold",
            "together, goes back together. Protect corners and legs with the original packing",
            "material or with blankets, so that nothing is scratched or dented on the way. Chairs and",
            "desks that have been damaged by use, stained, cut or painted cannot be accepted. Take a",
            "photo of each piece before it leaves your home, so that any damage on the way can be traced.",
        ),
        "How to start a return",
        para(
            f"To start a return for {v} furniture, sign in to your account, go to your order history",
            "and choose the pieces you want to send back, or bring your proof of purchase to the",
            "returns desk in one of our stores. Large pieces are collected from your home: once you",
            "start the return, we contact you to arrange a pickup time, and the driver checks each",
            "piece before taking it away. Smaller pieces, such as a single chair, can be brought to the",
            "returns desk, where a team member checks them with you. If a desk will not fit through the",
            "door in one piece, the driver can take it apart before carrying it out.",
        ),
        "Your refund",
        para(
            f"Once the {v} furniture has been checked, we send the refund to the payment method you",
            "used. It normally shows in your account within a few business days, depending on your",
            "bank. Gift card payments are refunded to a gift card, and a payment split across several",
            "methods is refunded in the same split. Delivery and assembly services are not refunded,",
            "because the work has already been done. If you paid in a store, you can also ask for the",
            "refund at the returns desk in the same way you paid.",
        ),
        "Pieces we cannot take back",
        para(
            "Floor samples and made-to-order pieces, such as a desk top cut to a custom length,",
            f"cannot be sent back, even when they are {v}. Furniture that was used outdoors, or stored",
            "in a damp room such as a basement or a bathroom, is not accepted either, because moisture",
            "can damage the wood and the fittings in ways that cannot be repaired.",
        ),
        "Exchanges",
        para(
            "You can exchange furniture for another colour or size within the same time limit.",
            "The exchange follows the same steps as a return, and the replacement is delivered or held",
            "for pickup once the original piece has been checked. If the replacement costs more you",
            "pay the difference, and if it costs less we refund the difference. Where the piece you",
            "want is not available, we tell you straight away and you can choose a refund instead. A",
            f"replacement for {v} furniture in another colour must come from the same range, so that",
            "matching pieces stay matched.",
        ),
    ]


for v, terms in (("unopened", ["365 days"]), ("opened", ["180 days"])):
    write(
        f"policy-return-furniture-{v}",
        f"Return Policy - Furniture, {v.capitalize()}",
        "furniture",
        "return",
        {"axis": "packaging", "value": v},
        terms,
        furniture_return(v),
    )

# =================================================================================================
# Furniture, warranty: no condition (IKEA: 10 years, chairs and desks agree).
# =================================================================================================
write(
    "policy-warranty-furniture",
    "Warranty - Furniture",
    "furniture",
    "warranty",
    None,
    ["10 years"],
    [
        para(
            "This warranty covers chairs and desks bought from our store, whether you ordered online",
            "or bought in person. Chairs and desks are covered for 10 years from the date of purchase",
            "against defects in materials and workmanship. The warranty is free, it comes with every",
            "chair and desk we sell, and you do not need to register it.",
        ),
        "What the warranty covers",
        para(
            "For chairs, the warranty covers the frame and the moving parts: the base, the casters,",
            "the gas cylinder, the tilt and height mechanisms, and the armrest and backrest",
            "adjustments. For desks, it covers the top, the frame, the legs, the drawers and the",
            "height-adjustment mechanism, together with the screws, bolts and fittings that hold the",
            "frame together. Coverage applies to normal use in a home or an office, by",
            "one person at a time, as described in the assembly and care guide that came with the",
            "piece.",
        ),
        "What the warranty does not cover",
        para(
            "The warranty does not cover normal wear and tear, cuts, scratches, stains, or damage from",
            "impacts and accidents. It does not cover fabric or leather covers, pieces used outdoors or",
            "in damp rooms such as bathrooms, pieces that were put together incorrectly or changed",
            "after purchase, or damage caused by moving them carelessly. It does not cover parts that",
            "wear out by design, such as the glides under chair legs, or pieces bought as floor",
            "samples. Damage caused by standing on a chair, or by putting a heavy load on a desk top, is",
            "not covered. It also does not cover costs or losses that follow from a defect, such as",
            "lost working time.",
        ),
        "How to make a claim",
        para(
            "To make a claim, contact our customer service team online or visit any of our stores",
            "with your proof of purchase. Describe the fault and, if you can, send photos of the defect",
            "and of the label under the seat or the desk top. Keep the piece until the claim is",
            "settled, because we may need to inspect it. Our team replies by email, usually within a",
            "few business days, and tells you whether the fault is covered and what happens next. If",
            "the fault makes the piece unsafe, stop using it straight away and say so in your claim, so",
            "that we can act quickly.",
        ),
        "Repair or replacement",
        para(
            "If the claim is accepted, we repair the faulty part or replace the piece with the same or",
            "a comparable one, and we choose which. Small parts are sent to you with instructions,",
            "while larger repairs are carried out by a technician who visits your home or office. If",
            "the piece is no longer sold, we offer a comparable piece instead. Any part that we replace",
            "is covered for the rest of the original warranty, not for a fresh period of its own. We pay",
            "for the parts and the labour of every covered repair.",
        ),
        "Proof of purchase and transfer",
        para(
            "Keep your proof of purchase for as long as the warranty runs, because it shows when the",
            "coverage started. If you bought online with your account, our team can find the sale",
            "there if the proof is lost. The warranty applies to the original buyer only, and it does",
            "not pass to another owner if the piece is sold or given away. If you move house, the",
            "warranty moves with you, as long as you still own the piece.",
        ),
    ],
)

# =================================================================================================
# Phones, warranty: region = domestic / international, framed as WHERE service is asked for, for a
# phone bought from the store (Samsung: 12 months; service limited to the country of first sale).
# =================================================================================================
PHONES_W_TERM = {
    "domestic": para(
        "When service is requested in the United States, where the phone was sold, phones are",
        "covered for 12 months from the date of purchase against defects in materials and",
        "workmanship.",
    ),
    "international": para(
        "When service is requested outside the United States, phones are not covered: the maker",
        "limits warranty service to the place where the phone was first sold. A fault that appears",
        "while you travel, or after you move, can be claimed only once the phone is back where it",
        "was bought.",
    ),
}


def phones_warranty(v):
    return [
        para(
            f"This warranty explains {v} service for phones bought from our store, whether you",
            "ordered online or bought in person.",
            PHONES_W_TERM[v],
        ),
        "What the warranty covers",
        para(
            "The warranty covers the phone itself, the battery inside it, and the charger and cable",
            "that came in the box, against faults in materials and workmanship that appear under",
            "normal use. Typical covered faults are a screen that stops responding to touch, buttons",
            "or ports that stop working, a battery that will no longer hold a charge, and a phone that",
            "will not turn on although it has not been dropped or wet. The charger and cable are covered",
            "only when they are the ones that came in the box, and faults that appear in the first",
            "days after purchase are handled in the same way as later ones. For {v} service, the opening",
            "section says whether and for how long such faults are covered.".replace("{v}", v),
        ),
        "What the warranty does not cover",
        para(
            "The warranty does not cover cracked screens, liquid damage, damage from drops or other",
            "accidents, or normal wear such as scratches and a worn finish. It does not cover faults",
            "caused by software or apps you installed, phones whose identification number has been",
            "removed or changed, or phones repaired by anyone other than an approved service center.",
            "Lost or stolen phones are not covered either, and accessories bought separately, such as",
            "cases and screen protectors, carry their own terms. These limits apply to",
            f"{v} service in the same way.",
        ),
        "How to make a claim",
        para(
            "To make a claim, contact our customer service team online or visit the service desk in",
            "any of our stores with your proof of purchase. Describe the fault and, if you can, send a",
            "short video or photo that shows it. A team member may ask you to restart the phone or run",
            "a simple check before the claim is logged in our system. For {v} service, the team then",
            "tells you where the phone must be sent and what happens next. Keep a note of the claim",
            "number we give you, and quote it whenever you contact us about the repair.".replace("{v}", v),
        ),
        "Repair, replacement or refund",
        para(
            "If the claim is accepted, the phone is repaired, or replaced with the same or a comparable",
            "phone when it cannot be repaired. A refund is offered only when neither is possible.",
            "Back up the phone and remove any SIM card before you send it, because some repairs reset",
            "the phone and we cannot keep cards or cases that come with it. A repaired or replaced phone",
            "is sent back to you by tracked delivery, or you can collect it from the service desk where",
            f"you handed it in. These options are the same for {v} service.",
        ),
        "Proof of purchase and transfer",
        para(
            "Keep your proof of purchase for as long as the phone is covered, because it shows where",
            "and when the phone was bought, and it is the first thing a technician asks for when you",
            f"request {v} service. The warranty stays with the phone if you give it away or sell it,",
            "as long as the next owner can show the original proof of purchase. If you bought online",
            "with your account, our team can find the sale there if the proof is lost.",
        ),
    ]


for v, terms in (("domestic", ["12 months"]), ("international", ["not covered"])):
    write(
        f"policy-warranty-phones-{v}",
        f"Warranty - Phones, {v.capitalize()} Service",
        "phones",
        "warranty",
        {"axis": "region", "value": v},
        terms,
        phones_warranty(v),
    )

# =================================================================================================
# Laptops, warranty: no condition (HP: 1 year; the region split is dropped, both sides one term).
# =================================================================================================
write(
    "policy-warranty-laptops",
    "Warranty - Laptops",
    "laptops",
    "warranty",
    None,
    ["1 year"],
    [
        para(
            "This warranty covers laptops bought from our store, whether you ordered online or",
            "bought in person. Laptops are covered for 1 year from the date of purchase against",
            "defects in materials and workmanship, and the cover begins on the day shown on your",
            "proof of purchase. The cover is the same whatever the screen size, processor or colour of",
            "the laptop.",
        ),
        "What the warranty covers",
        para(
            "The warranty covers the parts the laptop was sold with: the screen, the keyboard and",
            "touchpad, the battery, the ports, the main board, the memory and storage, the fans, and",
            "the charger that came in the box. Typical covered faults are keys that stop working, a",
            "screen with dead lines or a flickering backlight, ports that no longer connect, a fan",
            "that makes a grinding noise, and a laptop that will not start although it has not been",
            "dropped or wet. Pre-installed software that fails because of a hardware fault is restored as",
            "part of the repair. Coverage applies to normal use at home, at work or at school.",
        ),
        "What the warranty does not cover",
        para(
            "The warranty does not cover accidental damage such as drops, spills and cracked screens,",
            "or cosmetic wear such as scratches, dents and worn keys. It does not cover software",
            "problems, viruses or lost files, faults caused by parts or accessories that did not come",
            "with the laptop, or damage from repairs made by anyone other than an approved service",
            "center. A battery slowly holds less charge as it ages; that is normal, and it is covered",
            "only when the battery fails outright. Damage from heat, such as a laptop left in a hot car,",
            "is not covered.",
        ),
        "How to make a claim",
        para(
            "To make a claim, contact our customer service team online or visit the service desk in",
            "one of our stores with your proof of purchase. Describe the fault and, if the laptop",
            "still starts, run the built-in hardware check and note any error code it shows. The team",
            "may guide you through a few steps by phone or chat first, because many faults turn out to",
            "be settings or software that can be fixed without sending the laptop anywhere. Keep a note",
            "of the claim number we give you and quote it whenever you contact us.",
        ),
        "Repair, replacement or refund",
        para(
            "If the claim is accepted, the laptop is repaired, either at a service desk or through a",
            "prepaid mail-in service, and returned to you when the repair is done. If it cannot be",
            "repaired, it is replaced with the same or a comparable laptop, and a refund is offered",
            "only when neither is possible. Copy your files before you hand the laptop over, because a",
            "repair can erase the storage drive, and remove any discs or memory cards you added. A",
            "mail-in repair comes with a padded box and a prepaid label, so you do not need to find",
            "packing yourself.",
        ),
        "Proof of purchase and transfer",
        para(
            "Keep your proof of purchase for as long as the laptop is covered, because it shows when",
            "the cover started. If you bought online with your account, our team can find the sale",
            "there if the proof is lost. The warranty stays with the laptop if you give it away or sell",
            "it, and the next owner can make a claim with the original proof of purchase. If the laptop",
            "was a gift, the person who received it can claim with a gift receipt.",
        ),
    ],
)

# =================================================================================================
# Electronics, warranty: no condition (Sony: 1 year, the author's pick under W6). TVs and headphones.
# =================================================================================================
write(
    "policy-warranty-electronics",
    "Warranty - Electronics",
    "electronics",
    "warranty",
    None,
    ["1 year"],
    [
        para(
            "This warranty covers TVs and headphones bought from our store, whether you ordered",
            "online or bought in person. TVs and headphones are covered for 1 year from the date of",
            "purchase against defects in materials and workmanship, with parts and labor included. The",
            "cover is the same for every screen size and every kind of headphones.",
        ),
        "What the warranty covers",
        para(
            "For a TV, the warranty covers the panel, the power supply, the speakers, the ports, the",
            "stand and the remote control that came in the box. Typical covered faults are a picture",
            "with dead pixels in a cluster, a screen that stays dark although the TV has power, ports",
            "that stop passing a signal, and a remote that stops working with fresh batteries. For",
            "headphones, it covers the speakers, the microphone, the controls, the battery and the",
            "charging case, so sound that drops out in one ear, or a case that no longer charges, is",
            "covered. Pixels that fail one at a time, rather than in a cluster, are reviewed case by",
            "case. Coverage applies to normal use in a home.",
        ),
        "What the warranty does not cover",
        para(
            "The warranty does not cover cracked or scratched screens, damage from drops, liquid or",
            "power surges, or normal wear such as worn ear cushions, ear tips and headbands. It does",
            "not cover image retention caused by showing the same still picture for long periods,",
            "apps and streaming services, or damage from mounting a TV with brackets that were not",
            "made for it. Faults caused by repairs made by anyone other than an approved service",
            "center are not covered either, and neither are headphones that were bent, crushed or sat",
            "on.",
        ),
        "How to make a claim",
        para(
            "To make a claim, contact our customer service team online or visit the service desk in",
            "one of our stores with your proof of purchase. Describe the fault and, if you can, send a",
            "photo or a short video that shows it. For a large TV, a technician can visit your home to",
            "look at it, or we collect it; headphones are sent to us with a prepaid label. The team may",
            "first guide you through a reset, because many faults clear after one. Keep a note of the",
            "claim number we give you and quote it whenever you contact us.",
        ),
        "Repair, replacement or refund",
        para(
            "If the claim is accepted, we repair the faulty part or replace the item with the same or",
            "a comparable one, and we choose which. Large TVs are usually repaired in your home, while",
            "headphones are usually replaced. A refund is offered only when neither repair nor",
            "replacement is possible. If a TV has to be taken away for repair, the technician brings a",
            "protective cover for the screen and returns the set when the work is done. Any part we fit",
            "is covered for the rest of the original",
            "warranty, not for a fresh period of its own.",
        ),
        "Proof of purchase and transfer",
        para(
            "Keep your proof of purchase for as long as the item is covered, because it shows when the",
            "cover started. If you bought online with your account, our team can find the sale there",
            "if the proof is lost. The warranty stays with the item if you give it away or sell it, and",
            "the next owner can make a claim with the original proof of purchase. If the item was a gift,",
            "the person who received it can claim with a gift receipt.",
        ),
    ],
)
