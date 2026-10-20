# Sources — the policy terms (plan step 2)

One stating line per term, quoted; never more of a page (W1). Fetched 2026-10-20 unless marked.
The documents are drafted from the **term table** at the end, never with these pages in context.

## The rule for choosing a source (fixed before any warranty page was fetched)

- **Returns:** the retailer `design.md` §2 names for the department, one retailer for both sides of a
  split: Best Buy (phones), Amazon (laptops), Target (electronics), IKEA (furniture).
- **Warranty:** the department's return retailer, **if it publishes its own warranty** for that
  department; otherwise **the maker that appears most often in the `Brand` field of the department's
  selected products** (`data/v1-draft/products/`; ties broken alphabetically; for a two-leaf
  department, per leaf, then W6). Paid protection plans are not warranties and are never used.
  - Best Buy, Amazon and Target publish no own warranty for phones, laptops, TVs or headphones →
    maker rule. **Not run yet: it needs Read on `data/v1-draft/products/`** (plan step 1).
  - IKEA publishes its own furniture warranty → IKEA.
  - **Amended by the author, 2026-10-21, before any maker page was fetched.** `make policy-sources`
    showed the Brand field empty on most selected products (phones 32 of 38, laptops 21, electronics
    26, furniture 21), so the rule would pick "no brand", and the few branded phones tie Amazon.com /
    Apple at 1. **The maker is now the Brand field, or else the first word of the title**
    (`check_policies.maker_of`), counted the same way: case-folded, ties alphabetical, per
    department and per leaf. Committed before it was run.
- **Second conditions are not used** (W7): member windows, carrier exceptions, state exceptions,
  prepaid exclusions, holiday windows.

## Returns

| Department | Term | URL | Stating line |
| :--- | :--- | :--- | :--- |
| phones | 14 days (both sides) | bestbuy.com, *Return & Exchange Policy* (`pcmcat260800050014`) | The returns table lists **14 days** for activatable devices, for standard and for My Best Buy Plus / Total members (a table row, not a sentence) |
| phones, opened | $45 | same | The returns-fee table lists "Activatable devices (excluding prepaid phones)" at **"$45."** |
| phones, unopened | no fee | same | "There is no restocking fee if the product is unopened." |
| laptops, new | 30 days | amazon.com help node `GKM69DUUYKQWKWX7` | **Read 2026-10-03** (`docs/work/2026-10-03-pqa-category-choice/spec.md:112`): 30 days. **Re-fetch failed 2026-10-20** (HTTP 503 on three Amazon help pages) |
| laptops, renewed | 90 days | amazon.com, *Amazon Renewed Guarantee* (`G4ZAA22U35N373NX`) | **Read 2026-10-03** (same line): Renewed 90. Re-fetch failed (503). A 2026-10-20 search summary agrees on 90 days for most Renewed items, **and reports a conflict**: some Renewed items get 30 days plus an 11-month limited warranty; Renewed Premium gets 365 |
| electronics | 30 days | target.com, *Returns* (`/help/articles/returns-exchanges/returns`) | "Electronics and entertainment items (excluding Apple® & Beats products) must be returned / exchanged within 30 days." |
| furniture, unopened | 365 days | ikea.com/us, *Return policy* | "IKEA offers a 365-day return policy for unopened products." |
| furniture, opened | 180 days | same | "You may also return open products within 180 days, with your proof of purchase, for a full refund." |

Not used, recorded for the data card: Target's phones line (14 days, "up to $35", no charge
unopened) — Best Buy is the phones source (question 4). Target's general window is 90 days, and
Best Buy's is 15; neither is a v1 department's source.

## Warranty

| Department | Term | URL | Stating line |
| :--- | :--- | :--- | :--- |
| furniture (chairs) | 10 years | ikea.com/us, *Find an office chair that suits your needs* | "All the chairs on this page have a 10-year limited warranty." |
| furniture (desks) | 10 years | ikea.com/us, BEKANT desk product page (`s19022808`) | "10-year Limited Warranty." |
| phones, domestic | 12 months | samsung.com/us, *Samsung Warranty* (`/us/support/warranty/`). Maker by the amended rule: **Samsung** (11 of 38 phones) | "The following models may have limited international warranty service support during the standard warranty 12-month period:" (the sentence goes on to a model list) |
| phones, international | not covered | same page | "Samsung limits service for smartphones, tablets, and wearable devices to the country where the product was first sold." For a phone bought from the store, service outside the US is therefore not covered. **Conflict, recorded:** the line above says some listed models get limited international support |
| laptops (one document) | 1 year | Maker by the amended rule: **HP** (9 of 38 laptops). The term is HP's 1-year limited hardware warranty, from a 2026-10-21 search summary of hp.com pages; **four direct fetches of support.hp.com and hp.com timed out**. The only verbatim HP line reached is in the 2004 *Worldwide Limited Warranty and Technical Support* PDF (`h10032.www1.hp.com/ctg/Manual/c00045119.pdf`, desktops): "1-Year Limited Hardware Warranty" | **Weak source; the author may want to confirm in a browser** |
| laptops, region | — (split dropped) | same PDF, and today's search summary of HP's current worldwide warranty | "THIS LIMITED WARRANTY IS APPLICABLE IN ALL COUNTRIES AND MAY BE ENFORCED IN ANY COUNTRY WHERE HP OR ITS AUTHORIZED SERVICE PROVIDERS OFFER WARRANTY SERVICE". Both sides get the same term, so by §2's fallback (review M3) **the laptops region split is dropped**: the family is one document, `policy-warranty-laptops` |
| electronics (TVs, headphones) | 1 year | Maker: **Sony**, by the author's rule of 2026-10-21 (skip title words that are not a maker name, so Sony 3 and TCL 3 tie, alphabetical). sony.com blocks this tool's crawler; Sony's own US warranty text was reached only as **old manuals on third-party sites** (manualowl, manualslib) through a search summary | TVs: labor and parts "one (1) year from the original date of purchase". **Conflict, recorded (W6):** an old Sony headphone manual (MDR-V300) gives "ninety (90) days". **The author picked 1 year** for the one electronics document. Weak source, flagged |

**Electronics, 2026-10-21.** The amended rule ran (`make policy-sources`, committed `a3cca5a`
first): phones → Samsung (11), laptops → HP (9). For electronics the top title word is "Bluetooth"
(4; headphone titles begin with it), then Sony (3) and TCL (3). Per leaf: TVs → TCL (3); headphones
→ "Bluetooth" (4), "Wireless" (3), "4" (2). None of the headphone words is a maker, so the rule
gives no source for that leaf. **The author (2026-10-21): skip title words that are not a maker name** — Sony (3) and TCL (3) tie at department level, alphabetical gives Sony, which makes both TVs and headphones.

Furniture: chairs and desks agree, so W6's one-term rule does not bite. (IKEA Canada lists 5 years
for BEKANT electric sit / stand frames; not a US source, not used.)

## Term table (what the drafts are written from)

| `doc_id` | `terms` |
| :--- | :--- |
| `policy-return-phones-unopened` | `["14 days"]` |
| `policy-return-phones-opened` | `["14 days", "$45"]` |
| `policy-return-laptops-new` | `["30 days"]` |
| `policy-return-laptops-renewed` | `["90 days"]` |
| `policy-return-electronics` | `["30 days"]` |
| `policy-return-furniture-unopened` | `["365 days"]` |
| `policy-return-furniture-opened` | `["180 days"]` |
| `policy-warranty-furniture` | `["10 years"]` |
| `policy-warranty-phones-domestic` | `["12 months"]` |
| `policy-warranty-phones-international` | `["not covered"]` |
| `policy-warranty-laptops` | `["1 year"]` |
| `policy-warranty-electronics` | `["1 year"]` |
