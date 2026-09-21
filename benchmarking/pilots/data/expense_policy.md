# Northwind Travel and Expense Policy

Every expense line gets one decision: `approve`, `needs_approval`, or `reject`.
If a line breaks more than one rule, a `reject` rule wins over a `needs_approval` rule.
If no rule applies, the decision is `approve` and the rule is `none`.

| Rule | Text | Decision |
|---|---|---|
| R01 | Any expense over USD 25.00 must have a receipt attached. | reject |
| R02 | Meals are limited to USD 75.00 per person. A meal above that limit needs manager approval. | needs_approval |
| R03 | Alcohol is never reimbursed. | reject |
| R04 | Flights shorter than 6 hours must be economy class. Business class is allowed on flights of 6 hours or longer. | reject |
| R05 | Flights booked fewer than 14 days before departure need VP approval. | needs_approval |
| R06 | Hotel rates above USD 250.00 per night need manager approval. | needs_approval |
| R07 | Expenses must be submitted within 60 days of the expense date. | reject |
| R08 | Any software or subscription purchase over USD 100.00 needs IT approval. | needs_approval |
| R09 | Client gifts are limited to USD 50.00 per recipient. | reject |
| R10 | Premium ride-hailing tiers (for example Uber Black, Lyft Lux) are not reimbursed. | reject |
| R11 | Personal hotel extras (minibar, in-room movies, spa) are not reimbursed. | reject |
| R12 | Personal car mileage above 300 miles per trip needs manager approval. | needs_approval |
