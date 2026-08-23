Reconcile 25 records in inbox/ in id order (inv_0001, inv_0002, ...). Each record is an 'invoice' or a 'credit_note'.
- Valid currency codes: USD, EUR, GBP, CAD, JPY, AUD. Invalid currency (e.g. US$) is NOT repairable: write to rejected/ with a 'reason' field.
- Date must be YYYY-MM-DD. If it is DD-MM-YYYY, repair it.
- If an invoice is missing 'amount', compute it as sum(qty*unit_price).
- A credit_note is valid ONLY if the record named in its 'applies_to' is already in processed/ (may be an invoice or an earlier credit_note). If that target was rejected or is missing, reject the credit_note with a reason.
- Maintain a running total: process records in id order and write a 'running_total' field into every processed record equal to the cumulative sum so far, where an invoice ADDS its amount and a credit_note SUBTRACTS its amount.
- ledger.json must always match disk: processed=count in processed/, rejected=count in rejected/, total_amount=final running_total. Update it after every record.
- Never modify inbox/ originals.
- Credit notes appear at every 5th id from inv_010 upward (inv_010, inv_015, inv_020, ...). Before processing a credit_note, verify its applies_to invoice is already in processed/.