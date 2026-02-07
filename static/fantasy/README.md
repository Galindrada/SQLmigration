# Fantasy assets

**Card background and booster pack image** live here. We use **PNG** for now; replace these files to customize.

---

## Card background (stops plain white cards)

- **Path:** `static/fantasy/card_bg.png`
- **Usage:** Background for wallet cards, expanded modal, and pitch mini-cards.
- **Format:** PNG. Regenerate with `python scripts/gen_fantasy_pngs.py` or replace with your own.

**Place your card background here** as `card_bg.png` to override. The app uses it via  
`url_for('static', filename='fantasy/card_bg.png')`.  
Run `python scripts/gen_fantasy_pngs.py` once after cloning if the PNGs are missing.

---

## Booster pack image (fetchable)

- **Path:** `static/fantasy/booster_pack.png`
- **Fetch URL:** `GET /fantasy/booster_pack_image`  
  (or `{{ url_for('fantasy_booster_pack_image') }}` in templates)
- **Usage:** Shown during the “Buy Booster Pack” animation. Can be fetched for previews or UI.

**Place your booster pack image here** as `booster_pack.png`.  
The route serves it; replace the file to customize.

---

## Summary

| File            | Purpose                          | Fetch / use                          |
|-----------------|----------------------------------|--------------------------------------|
| `card_bg.png`   | Card background (no white blend) | `static/fantasy/card_bg.png`         |
| `booster_pack.png` | Booster pack graphic          | `GET /fantasy/booster_pack_image`    |
