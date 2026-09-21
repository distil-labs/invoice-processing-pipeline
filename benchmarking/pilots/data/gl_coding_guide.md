# Northwind GL coding guide

Assign every invoice or expense line to exactly one account.

## Chart of accounts

| Code | Account |
|---|---|
| 1510 | Capitalised equipment |
| 5010 | Hosting and infrastructure (cost of goods sold) |
| 5020 | Payment processing fees (cost of goods sold) |
| 5030 | Customer support tools (cost of goods sold) |
| 6110 | Software subscriptions |
| 6120 | Hardware and equipment (expensed) |
| 6210 | Travel: airfare |
| 6220 | Travel: lodging |
| 6230 | Travel: ground transport |
| 6240 | Travel: meals |
| 6310 | Client entertainment |
| 6320 | Staff welfare |
| 6330 | Conferences and events |
| 6410 | Professional fees: legal |
| 6420 | Professional fees: accounting and tax |
| 6430 | Contractors and freelancers |
| 6510 | Marketing: advertising |
| 6520 | Marketing: content and design |
| 6610 | Office rent and utilities |
| 6620 | Office supplies and furniture |
| 6710 | Recruiting |
| 6720 | Training and education |
| 6810 | Bank charges and interest |
| 6910 | Insurance |

## Conventions

When two conventions could apply, the one listed first wins.

1. **Recruiting wins over everything.** Any cost incurred for a job candidate or for hiring goes to 6710: candidate flights, hotels and meals, job postings, recruiting agency fees. Job postings are not advertising.
2. **Production systems are cost of goods sold.** Anything the customer-facing production system depends on goes to 5010: cloud hosting, CDN, production monitoring and alerting, even when billed as a subscription. Tools used only for development, testing, or internal work stay in 6110.
3. **Customer support tooling** (helpdesk, support chat, telephony for the support team) goes to 5030. The same tool bought for another team goes to 6110.
4. **Capitalisation is judged per unit.** A single hardware or furniture item with a unit price of USD 2,500 or more goes to 1510. Below that, hardware goes to 6120 and furniture to 6620. The invoice total does not matter.
5. **Meals.** If at least one client or prospect is present, 6310, wherever the meal takes place. Otherwise, a meal while travelling away from the home city goes to 6240, and a team meal in the home city goes to 6320.
6. **Conferences.** Tickets, booths and conference sponsorship go to 6330. Travel to a conference is coded to the travel accounts, and meals at a conference follow convention 5. A workshop or course that ends in a certificate is training, 6720, even when held at a conference.
7. **Training.** Courses, certifications, books and learning platforms go to 6720, even when billed as a subscription.
8. **People who bill for their time.** Individuals and agencies billing for time go to 6430, except: law firms 6410; accounting, tax and audit firms 6420; design or content work that produces marketing assets 6520.
9. **Advertising.** Ad platform spend and sponsorship of newsletters or podcasts go to 6510.
10. **Gifts.** To employees 6320, to clients 6310.
11. **Money movement.** Fees charged by a payment processor for collecting customer payments go to 5020. Wire fees, currency conversion fees, card membership fees and interest go to 6810, whoever charges them.
12. **Office.** Rent, coworking memberships, electricity, internet and cleaning go to 6610. Consumables go to 6620.
