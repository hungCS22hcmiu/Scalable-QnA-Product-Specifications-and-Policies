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
| phones, domestic / international | — | **pending: maker rule** | — |
| laptops, domestic / international | — | **pending: maker rule** | — |
| electronics (TVs, headphones) | — | **pending: maker rule** | — |

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
| warranty, phones / laptops / electronics | pending |
