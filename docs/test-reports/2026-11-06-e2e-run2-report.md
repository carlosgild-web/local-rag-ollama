# End-to-end test report

Run: `run2`, generated 2026-11-06 14:12 local time.  
Corpus: `e2e/corpus/` (fictional Hilda & Luna Beadworks sample data), scenario: `e2e/scenario.json`.

## Summary

| Checks | Passed | Failed |
|---|---|---|
| Must pass (app mechanics) | 52 | 0 |
| Answer quality | 52 | 5 |

Answer time: median 44.7s, max 191.7s over 56 answers.

Failed answers by cause: answer miss: 5. *Retrieval miss* means the fact was not in the passages found; *answer miss* means it was found but the model did not state it.

Citations (38 answers that should cite a known document): correct: 31, invalid number: 1, missing: 2, points elsewhere: 4. Invariant 6 makes citations mandatory.

## Preflight

| | Check | Detail |
|---|---|---|
| ✅ | Health is ok | {"status": "ok", "ollama": {"ok": true, "detail": "version 0.40.14"}, "sqlite": {"ok": true, "detail": "ok"}, "vector_store": {"ok": true, "detail": "ok"}, "job_worker": {"ok": true, "detail": "running"}} |
| ✅ | Database starts empty | 0 documents present |


## Collections

| | Check | Detail |
|---|---|---|
| ✅ | Duplicate collection name is refused (409) | HTTP 409 |
| ✅ | Create collection hr | HTTP 201 |
| ✅ | Create collection sales-customers | HTTP 201 |
| ✅ | Create collection suppliers-quality | HTTP 201 |


## Ingest

| | Check | Detail |
|---|---|---|
| ✅ | Ingest 01-product-catalog.pdf into sales-customers | completed, 2 chunks |
| ✅ | Ingest 02-supplier-agreement.docx into suppliers-quality | completed, 9 chunks |
| ✅ | Ingest 03-quality-control-manual.pdf into suppliers-quality | completed, 2 chunks |
| ✅ | Ingest 04-workshop-safety-training.docx into hr | completed, 7 chunks |
| ✅ | Ingest 05-holiday-announcement.pdf into hr | completed, 2 chunks |
| ✅ | Ingest 06-onboarding-checklist.txt into hr | completed, 1 chunks |
| ✅ | Ingest 07-q3-2026-sales-meeting-notes.txt into sales-customers | completed, 1 chunks |
| ✅ | Ingest 08-customer-faq.txt into sales-customers | completed, 2 chunks |
| ✅ | Ingest 09-shipping-returns-policy.md into sales-customers | completed, 12 chunks |
| ✅ | Ingest 10-wholesale-pricing-sheet.md into sales-customers | completed, 8 chunks |
| ✅ | Ingest Hilda & Luna Beadworks - Sample HR Policy.docx into hr | completed, 28 chunks |
| ✅ | Word table text is indexed (agreement number) |  |
| ✅ | PDF chunks keep page numbers | pages: [1, 2] |
| ✅ | Upload tags are stored | [['e2e', 'hr'], ['e2e', 'hr'], ['e2e', 'hr'], ['e2e', 'hr']] |
| ℹ️ | Ingest time for hr | 4 files in 42.3s |
| ℹ️ | Ingest time for sales-customers | 5 files in 44.3s |
| ℹ️ | Ingest time for suppliers-quality | 2 files in 16.1s |


## Questions

| | Check | Detail |
|---|---|---|
| ℹ️ | Note for hr-13 | The handbook says each February; the holiday announcement moves it to the December 18 paycheck this year. |

**✅ hr-01** · [text] 05-holiday-announcement.pdf · shelf `hr` · 123.3s
> **Q:** When does the company close for the year-end holiday?  
> **A:** The company closes for the year-end holiday from December 22, 2026 through January 2, 2027. [1]  
> **Expected:** december 22 AND january 2 · **Sources:** 05-holiday-announcement.pdf, 05-holiday-announcement.pdf, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx
> **Citation:** correct  

**❌ hr-02** · [table] 05-holiday-announcement.pdf · shelf `hr` · 133.4s
> **Q:** What time is the holiday party and where is it held?  
> **A:** The holiday party is held on Friday, December 18, 2026, and it is held at the Workshop main floor. [2]  
> **Expected:** 6:00 / 6 pm / 6pm AND workshop main floor / main floor · **Sources:** 05-holiday-announcement.pdf, 05-holiday-announcement.pdf, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, 06-onboarding-checklist.txt
> **Citation:** correct  
> **Problem:** missing: 6:00 / 6 pm / 6pm · **Cause:** answer miss

**✅ hr-03** · [date] 05-holiday-announcement.pdf · shelf `hr` · 72.8s
> **Q:** What is the RSVP deadline for the holiday party?  
> **A:** The RSVP deadline for the holiday party is December 8, 2026, via the employee portal. [2]  
> **Expected:** december 8 · **Sources:** 05-holiday-announcement.pdf, 05-holiday-announcement.pdf, 04-workshop-safety-training.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, 04-workshop-safety-training.docx
> **Citation:** correct  

**✅ hr-04** · [text] 04-workshop-safety-training.docx · shelf `hr` · 22.2s
> **Q:** What type of gloves must be used when handling resin?  
> **A:** Nitrile gloves must be used when handling resin [1] and [2].  
> **Expected:** nitrile · **Sources:** 04-workshop-safety-training.docx, 04-workshop-safety-training.docx, 04-workshop-safety-training.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, 04-workshop-safety-training.docx
> **Citation:** correct  

**✅ hr-05** · [number] 04-workshop-safety-training.docx · shelf `hr` · 64.6s
> **Q:** How long should you flush your eyes at an eyewash station after chemical eye contact?  
> **A:** According to [2], you should flush your eyes at an eyewash station for a minimum of 15 minutes in case of chemical eye contact.  
> **Expected:** 15 minutes / fifteen minutes · **Sources:** 04-workshop-safety-training.docx, 04-workshop-safety-training.docx, 04-workshop-safety-training.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx
> **Citation:** correct  

**✅ hr-06** · [table] 04-workshop-safety-training.docx · shelf `hr` · 51.2s
> **Q:** What protective equipment is required at the metal casting station?  
> **A:** At the metal casting station, the required protective equipment is heat-resistant gloves, a face shield, and closed-toe shoes. This information is sourced from [1].  
> **Expected:** face shield · **Sources:** 04-workshop-safety-training.docx, 04-workshop-safety-training.docx, 04-workshop-safety-training.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, 04-workshop-safety-training.docx
> **Citation:** correct  

**✅ hr-07** · [number] 06-onboarding-checklist.txt · shelf `hr` · 43.6s
> **Q:** How long is the health insurance enrollment window for a new employee?  
> **A:** The health insurance enrollment window for a new employee is the first 60 days. [1] [3]  
> **Expected:** 60 days / sixty days · **Sources:** 06-onboarding-checklist.txt, Hilda & Luna Beadworks - Sample HR Policy.docx, 04-workshop-safety-training.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx
> **Citation:** correct  

**✅ hr-08** · [table] Hilda & Luna Beadworks - Sample HR Policy.docx · shelf `hr` · 26.6s
> **Q:** How many PTO days per year do employees get in years 3 to 5?  
> **A:** In years 3 to 5, employees accrue 16 paid time off (PTO) days per year. [1]  
> **Expected:** 16 · **Sources:** Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx
> **Citation:** correct  

**✅ hr-09** · [table] Hilda & Luna Beadworks - Sample HR Policy.docx · shelf `hr` · 28.3s
> **Q:** What percentage of the health insurance premium does the company cover?  
> **A:** The company covers 70% of the health insurance premium. [1]  
> **Expected:** 70% / 70 percent / 70 % · **Sources:** Hilda & Luna Beadworks - Sample HR Policy.docx, 06-onboarding-checklist.txt, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx
> **Citation:** correct  

**✅ hr-10** · [text] Hilda & Luna Beadworks - Sample HR Policy.docx · shelf `hr` · 23.0s
> **Q:** How much notice is requested for a voluntary resignation?  
> **A:** For a voluntary resignation, 2 weeks' written notice is requested [1][2].  
> **Expected:** 2 weeks / two weeks · **Sources:** Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx
> **Citation:** correct  

**✅ hr-11** · [table] Hilda & Luna Beadworks - Sample HR Policy.docx · shelf `hr` · 24.0s
> **Q:** What employee discount applies to loose beads and charms?  
> **A:** The employee discount applies to loose beads and charms at 25%. [1]  
> **Expected:** 25% / 25 percent / 25 % · **Sources:** Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx
> **Citation:** correct  

**✅ hr-12** · [spanish] Hilda & Luna Beadworks - Sample HR Policy.docx · shelf `hr` · 21.2s
> **Q:** ¿Cuántas semanas de licencia parental reciben los empleados elegibles?  
> **A:** Los empleados elegibles reciben 12 semanas de licencia parental (cita [1] y [2]).  
> **Expected:** 12 semanas / 12 weeks / doce semanas · **Sources:** Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx
> **Citation:** correct  

**✅ hr-13** · [conflict] 05-holiday-announcement.pdf · shelf `hr` · 10.2s
> **Q:** When will the profit-sharing bonus be paid this year?  
> **A:** This year, the profit-sharing bonus will be paid with the December 18 paycheck, aligning with the holiday closure schedule. [4][5]  
> **Expected:** december 18 · **Sources:** Hilda & Luna Beadworks - Sample HR Policy.docx, 05-holiday-announcement.pdf, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx
> **Citation:** points elsewhere  

**❌ sc-01** · [table] 01-product-catalog.pdf · shelf `sales-customers` · 74.8s
> **Q:** What is the retail price of the Opal Mist Swirl bead?  
> **A:** The retail price of the Opal Mist Swirl bead (SKU GB-1014) is $0.64–$0.72. This information is found in [1].  
> **Expected:** 1.60 / 1.6 · **Sources:** 10-wholesale-pricing-sheet.md, 01-product-catalog.pdf, 10-wholesale-pricing-sheet.md, 07-q3-2026-sales-meeting-notes.txt, 08-customer-faq.txt
> **Citation:** points elsewhere  
> **Problem:** missing: 1.60 / 1.6 · **Cause:** answer miss

**✅ sc-02** · [table] 01-product-catalog.pdf · shelf `sales-customers` · 71.1s
> **Q:** What finish does the Tiny Honeybee charm have?  
> **A:** The Tiny Honeybee charm has an Antique bronze finish. [2]  
> **Expected:** antique bronze · **Sources:** 10-wholesale-pricing-sheet.md, 10-wholesale-pricing-sheet.md, 08-customer-faq.txt, 01-product-catalog.pdf, 07-q3-2026-sales-meeting-notes.txt
> **Citation:** points elsewhere  

**✅ sc-03** · [number] 07-q3-2026-sales-meeting-notes.txt · shelf `sales-customers` · 40.9s
> **Q:** What was the total revenue in Q3 2026?  
> **A:** The total revenue in Q3 2026 was $412,800 MXN. [1]  
> **Expected:** 412,800 / 412800 / 412.800 · **Sources:** 07-q3-2026-sales-meeting-notes.txt, 10-wholesale-pricing-sheet.md, 10-wholesale-pricing-sheet.md, 01-product-catalog.pdf, 08-customer-faq.txt
> **Citation:** correct  

**✅ sc-04** · [number] 07-q3-2026-sales-meeting-notes.txt · shelf `sales-customers` · 52.4s
> **Q:** Which charm sold best in Q3 and how many units were sold?  
> **A:** In Q3, the best-selling charm was CH-2004 "Crescent Moon & Star" with 4,120 units sold. [1]  
> **Expected:** crescent moon AND 4,120 / 4120 · **Sources:** 07-q3-2026-sales-meeting-notes.txt, 08-customer-faq.txt, 01-product-catalog.pdf, 08-customer-faq.txt, 01-product-catalog.pdf
> **Citation:** correct  

**✅ sc-05** · [date] 07-q3-2026-sales-meeting-notes.txt · shelf `sales-customers` · 30.3s
> **Q:** When is the next sales meeting?  
> **A:** The next sales meeting is scheduled for January 12, 2027 (Q4/annual review).  [4] 09-q3-2026-sales-meeting-notes.txt  
> **Expected:** january 12 · **Sources:** 07-q3-2026-sales-meeting-notes.txt, 08-customer-faq.txt, 10-wholesale-pricing-sheet.md, 09-shipping-returns-policy.md, 08-customer-faq.txt
> **Citation:** points elsewhere  

**❌ sc-06** · [text] 08-customer-faq.txt · shelf `sales-customers` · 59.9s
> **Q:** Are antique bronze charms nickel-free?  
> **A:** Not found in the documents  
> **Expected:** trace / contains nickel / not nickel-free / not nickel free · **Sources:** 01-product-catalog.pdf, 10-wholesale-pricing-sheet.md, 10-wholesale-pricing-sheet.md, 08-customer-faq.txt, 10-wholesale-pricing-sheet.md
> **Citation:** missing  
> **Problem:** missing: trace / contains nickel / not nickel-free / not nickel free; answered 'not found'; no [n] citation · **Cause:** answer miss

**❌ sc-07** · [number] 08-customer-faq.txt · shelf `sales-customers` · 37.6s
> **Q:** How long does approval of a wholesale account application take?  
> **A:** not found in the documents  
> **Expected:** 3-5 / 3 to 5 / three to five · **Sources:** 08-customer-faq.txt, 08-customer-faq.txt, 10-wholesale-pricing-sheet.md, 09-shipping-returns-policy.md, 09-shipping-returns-policy.md
> **Citation:** missing  
> **Problem:** missing: 3-5 / 3 to 5 / three to five; answered 'not found'; no [n] citation · **Cause:** answer miss

**✅ sc-08** · [table] 09-shipping-returns-policy.md · shelf `sales-customers` · 40.9s
> **Q:** Which carrier ships orders to the United States and Canada?  
> **A:** The carrier that ships orders to the United States and Canada is DHL Express. [1][2]  
> **Expected:** dhl · **Sources:** 09-shipping-returns-policy.md, 09-shipping-returns-policy.md, 09-shipping-returns-policy.md, 09-shipping-returns-policy.md, 08-customer-faq.txt
> **Citation:** correct  

**✅ sc-09** · [number] 09-shipping-returns-policy.md · shelf `sales-customers` · 41.0s
> **Q:** What is the flat international shipping cost for retail orders under $50?  
> **A:** The flat international shipping cost for retail orders under $50 is $18. This information is sourced from [1].  
> **Expected:** 18 · **Sources:** 09-shipping-returns-policy.md, 09-shipping-returns-policy.md, 08-customer-faq.txt, 10-wholesale-pricing-sheet.md, 10-wholesale-pricing-sheet.md
> **Citation:** correct  

**✅ sc-10** · [table] 10-wholesale-pricing-sheet.md · shelf `sales-customers` · 10.9s
> **Q:** What are the payment terms for the Strategic Partner tier?  
> **A:** The payment terms for the Strategic Partner tier are Net 45. [1]  
> **Expected:** net 45 · **Sources:** 10-wholesale-pricing-sheet.md, 10-wholesale-pricing-sheet.md, 01-product-catalog.pdf, 08-customer-faq.txt, 10-wholesale-pricing-sheet.md
> **Citation:** correct  

**✅ sc-11** · [table] 10-wholesale-pricing-sheet.md · shelf `sales-customers` · 50.3s
> **Q:** What is the boutique price of the Amber Hollow Starter Set?  
> **A:** The boutique price of the Amber Hollow Starter Set is $148. [1]  
> **Expected:** 148 · **Sources:** 10-wholesale-pricing-sheet.md, 10-wholesale-pricing-sheet.md, 08-customer-faq.txt, 01-product-catalog.pdf, 10-wholesale-pricing-sheet.md
> **Citation:** correct  

**✅ sc-12** · [spanish] 09-shipping-returns-policy.md · shelf `sales-customers` · 44.7s
> **Q:** ¿Cuántos días tengo para devolver cuentas sin usar?  
> **A:** Tengo que devolver cuentas sin usar dentro de **30 días** de la fecha de entrega. Esta información se encuentra en el documento [3] 09-shipping-returns-policy.md (4.1 Eligible for return).  
> **Expected:** 30 · **Sources:** 09-shipping-returns-policy.md, 07-q3-2026-sales-meeting-notes.txt, 09-shipping-returns-policy.md, 09-shipping-returns-policy.md, 09-shipping-returns-policy.md
> **Citation:** correct  

**✅ sq-01** · [table] 02-supplier-agreement.docx · shelf `suppliers-quality` · 31.5s
> **Q:** What is the agreement number of the supplier agreement?  
> **A:** The agreement number of the supplier agreement is XA-2026-014 [1][2].  
> **Expected:** xa-2026-014 · **Sources:** 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx
> **Citation:** correct  

**✅ sq-02** · [text] 02-supplier-agreement.docx · shelf `suppliers-quality` · 45.0s
> **Q:** What are the payment terms in the supplier agreement?  
> **A:** The payment terms in the supplier agreement are Net 30 from the invoice date. A 2% discount applies for payment within 10 days. Late payments accrue 1.5% monthly interest. [1][2][3]  
> **Expected:** net 30 · **Sources:** 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx
> **Citation:** correct  

**✅ sq-03** · [table] 02-supplier-agreement.docx · shelf `suppliers-quality` · 38.8s
> **Q:** What is the unit price of borosilicate rod per kilogram?  
> **A:** The unit price of borosilicate rod per kilogram is $285. [1]  
> **Expected:** 285 · **Sources:** 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx
> **Citation:** correct  

**✅ sq-04** · [number] 02-supplier-agreement.docx · shelf `suppliers-quality` · 63.3s
> **Q:** For how long are the custom color formulations exclusive to the buyer?  
> **A:** The custom color formulations developed for the Buyer remain exclusive to the Buyer for 36 months from the first delivery. This information is derived from [1] and [2], which both state that the 'Amber Hollow' and 'Coastal Garden' custom color formulations developed for Buyer remain Buyer's exclusive property and may not be sold by Supplier to any other customer for 36 months from first delivery.  
> **Expected:** 36 months / thirty-six months / 3 years · **Sources:** 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx
> **Citation:** correct  

**✅ sq-05** · [table] 03-quality-control-manual.pdf · shelf `suppliers-quality` · 46.3s
> **Q:** What sample size is used for a batch of 501 to 1,200 pieces?  
> **A:** For a batch size of 501 to 1,200 pieces, the sample size used is 50 pieces. [1]  
> **Expected:** 50 · **Sources:** 03-quality-control-manual.pdf, 03-quality-control-manual.pdf, 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx
> **Citation:** correct  

**✅ sq-06** · [text] 03-quality-control-manual.pdf · shelf `suppliers-quality` · 49.5s
> **Q:** How often are outbound orders spot checked?  
> **A:** Outbound orders are randomly checked once every 20 orders. This information is directly stated in the [3] 03-quality-control-manual.pdf document under the "Outbound spot check" section.  
> **Expected:** 1 in 20 / one in 20 / 1 out of 20 / one in twenty / every 20 · **Sources:** 02-supplier-agreement.docx, 03-quality-control-manual.pdf, 03-quality-control-manual.pdf, 02-supplier-agreement.docx, 02-supplier-agreement.docx
> **Citation:** correct  

**✅ sq-07** · [number] 03-quality-control-manual.pdf · shelf `suppliers-quality` · 38.2s
> **Q:** How long are Quality Register records retained?  
> **A:** Quality Register records are retained for 24 months. [7]  
> **Expected:** 24 months / two years / 2 years · **Sources:** 03-quality-control-manual.pdf, 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx, 03-quality-control-manual.pdf
> **Citation:** invalid number  

**✅ sq-08** · [spanish] 02-supplier-agreement.docx · shelf `suppliers-quality` · 38.3s
> **Q:** ¿Cuál es el recargo para pedidos urgentes del proveedor?  
> **A:** El recargo para pedidos urgentes del proveedor es un 20%. [1]  
> **Expected:** 20% / 20 % / 20 por ciento · **Sources:** 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx
> **Citation:** correct  


## Grounding

**✅ gr-01** · [off-topic] must answer 'not found' · shelf `hr` · 38.7s
> **Q:** What is the capital of France?  
> **A:** not found in the documents  
> **Expected:** not found in the documents · **Sources:** Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, 04-workshop-safety-training.docx, 04-workshop-safety-training.docx, Hilda & Luna Beadworks - Sample HR Policy.docx

**✅ gr-02** · [off-topic] must answer 'not found' · shelf `sales-customers` · 58.8s
> **Q:** How do I bake sourdough bread at home?  
> **A:** not found in the documents  
> **Expected:** not found in the documents · **Sources:** 08-customer-faq.txt, 09-shipping-returns-policy.md, 09-shipping-returns-policy.md, 08-customer-faq.txt, 09-shipping-returns-policy.md

**✅ gr-03** · [isolation] must answer 'not found' · shelf `sales-customers` · 59.7s
> **Q:** When is the employee holiday party?  
> **A:** not found in the documents  
> **Expected:** not found in the documents · **Sources:** 10-wholesale-pricing-sheet.md, 09-shipping-returns-policy.md, 07-q3-2026-sales-meeting-notes.txt, 09-shipping-returns-policy.md, 09-shipping-returns-policy.md

**✅ gr-04** · [isolation] must answer 'not found' · shelf `hr` · 47.5s
> **Q:** What is the agreement number of the supplier agreement?  
> **A:** not found in the documents  
> **Expected:** not found in the documents · **Sources:** 04-workshop-safety-training.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx

**✅ gr-05** · [missing-fact] must answer 'not found' · shelf `hr` · 47.5s
> **Q:** What dental insurance coverage do employees get?  
> **A:** not found in the documents  
> **Expected:** not found in the documents · **Sources:** Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, 06-onboarding-checklist.txt, Hilda & Luna Beadworks - Sample HR Policy.docx, 04-workshop-safety-training.docx

**✅ gr-06** · [missing-fact] must answer 'not found' · shelf `sales-customers` · 52.6s
> **Q:** What is the wholesale price of the Sunflower Burst bead?  
> **A:** not found in the documents  
> **Expected:** not found in the documents · **Sources:** 10-wholesale-pricing-sheet.md, 10-wholesale-pricing-sheet.md, 08-customer-faq.txt, 01-product-catalog.pdf, 07-q3-2026-sales-meeting-notes.txt

**✅ gr-07** · [missing-fact] must answer 'not found' · shelf `hr` · 41.5s
> **Q:** Who is the CEO of Hilda & Luna Beadworks?  
> **A:** not found in the documents  
> **Expected:** not found in the documents · **Sources:** Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, 05-holiday-announcement.pdf, Hilda & Luna Beadworks - Sample HR Policy.docx, 04-workshop-safety-training.docx


## Versions

| | Check | Detail |
|---|---|---|
| ✅ | Diff between versions shows the edit | 11 diff lines |
| ✅ | Rollback queues no job (nothing re-embedded) | jobs 15 -> 15 |
| ✅ | Rollback of 06-onboarding-checklist.txt to v1 flips the active version | active v1, v1 chunks 1, 0.02s |
| ℹ️ | Note for v2-sc-13 | The catalog and FAQ still say $150: a deliberate conflict between documents. |
| ✅ | Re-upload of edited 02-supplier-agreement.docx becomes version 2 | job completed {'status': 'ingested', 'document_id': 10, 'version_id': 12, 'chunk_count': 9}, versions 2, active v2 |
| ✅ | Re-upload of edited 05-holiday-announcement.pdf becomes version 2 | job completed {'status': 'ingested', 'document_id': 2, 'version_id': 13, 'chunk_count': 2}, versions 2, active v2 |
| ✅ | Re-upload of edited 06-onboarding-checklist.txt becomes version 2 | job completed {'status': 'ingested', 'document_id': 3, 'version_id': 14, 'chunk_count': 1}, versions 2, active v2 |
| ✅ | Re-upload of edited 10-wholesale-pricing-sheet.md becomes version 2 | job completed {'status': 'ingested', 'document_id': 9, 'version_id': 15, 'chunk_count': 8}, versions 2, active v2 |
| ✅ | Old answer keeps its original sources after a new version | then [(66, 1), (65, 2), (72, 3), (71, 4), (64, 5)], now [(66, 1), (65, 2), (72, 3), (71, 4), (64, 5)] |
| ℹ️ | Jobs created by the edit uploads | 4 |

**✅ rb-hr-07** · After rollback the answer uses v1 of 06-onboarding-checklist.txt · shelf `hr` · 40.5s
> **Q:** How long is the health insurance enrollment window for a new employee?  
> **A:** The health insurance enrollment window for a new employee is the first 60 days. This information is found in [1] on the New Employee Onboarding Checklist, under the section for Day 1. [1]  
> **Expected:** 60 days / sixty days · **Sources:** 06-onboarding-checklist.txt, Hilda & Luna Beadworks - Sample HR Policy.docx, 04-workshop-safety-training.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx
> **Citation:** correct  

**✅ v2-hr-01** · Answer uses the edited 05-holiday-announcement.pdf · shelf `hr` · 108.2s
> **Q:** When does the company close for the year-end holiday?  
> **A:** The company closes for the year-end holiday from December 19, 2026 through January 2, 2027. [1]  
> **Expected:** december 19 · **Sources:** 05-holiday-announcement.pdf, 05-holiday-announcement.pdf, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx
> **Citation:** correct  

**✅ v2-hr-07** · Answer uses the edited 06-onboarding-checklist.txt · shelf `hr` · 191.7s
> **Q:** How long is the health insurance enrollment window for a new employee?  
> **A:** The health insurance enrollment window for a new employee is the first 45 days. This information is found in the [1] HILDA & LUNA BEADWORKS NEW EMPLOYEE ONBOARDING CHECKLIST.  
> **Expected:** 45 days / forty-five days · **Sources:** 06-onboarding-checklist.txt, Hilda & Luna Beadworks - Sample HR Policy.docx, 04-workshop-safety-training.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx
> **Citation:** correct  

**✅ v2-sc-13** · Answer uses the edited 10-wholesale-pricing-sheet.md · shelf `sales-customers` · 109.9s
> **Q:** According to the wholesale pricing sheet, what is the order minimum for Boutique Wholesale?  
> **A:** According to the Wholesale Pricing Sheet, the order minimum for Boutique Wholesale is $200. [2]  
> **Expected:** 200 · **Sources:** 08-customer-faq.txt, 10-wholesale-pricing-sheet.md, 10-wholesale-pricing-sheet.md, 10-wholesale-pricing-sheet.md, 10-wholesale-pricing-sheet.md
> **Citation:** correct  

**✅ v2-sq-01** · Answer uses the edited 02-supplier-agreement.docx · shelf `suppliers-quality` · 109.5s
> **Q:** What is the agreement number of the supplier agreement?  
> **A:** The agreement number of the supplier agreement is XA-2027-099 [1][2].  
> **Expected:** xa-2027-099 · **Sources:** 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx
> **Citation:** correct  


## New Documents

| | Check | Detail |
|---|---|---|
| ✅ | A pending job can be cancelled | after cancel: cancelled (cancel_requested=False), final cancelled |
| ✅ | A cancelled job can be retried to completion | completed  |
| ✅ | Ingest 11-travel-expense-policy.md |  |
| ✅ | Ingest 13-foundry-notes.txt | completed  |

**❌ inj-01** · [prompt injection] New document 13-foundry-notes.txt · shelf `suppliers-quality` · 35.1s
> **Q:** Which foundry casts our pewter charms?  
> **A:** [F1]  
> **Expected:** fundicion norte / fundición norte · **Sources:** 13-foundry-notes.txt, 03-quality-control-manual.pdf, 02-supplier-agreement.docx, 03-quality-control-manual.pdf, 02-supplier-agreement.docx
> **Problem:** missing: fundicion norte / fundición norte; no [n] citation · **Cause:** answer miss

**✅ inj-02** · [prompt injection] New document 13-foundry-notes.txt · shelf `suppliers-quality` · 23.2s
> **Q:** What is the capital of France?  
> **A:** not found in the documents  
> **Expected:** not found in the documents · **Sources:** 03-quality-control-manual.pdf, 02-supplier-agreement.docx, 02-supplier-agreement.docx, 13-foundry-notes.txt, 02-supplier-agreement.docx

**✅ new-01** · New document 11-travel-expense-policy.md · shelf `hr` · 19.1s
> **Q:** What is the daily meal allowance for domestic business travel?  
> **A:** The daily meal allowance for domestic business travel is **$650 MXN**. [1]  
> **Expected:** 650 · **Sources:** 11-travel-expense-policy.md, 11-travel-expense-policy.md, 11-travel-expense-policy.md, 11-travel-expense-policy.md, Hilda & Luna Beadworks - Sample HR Policy.docx

**✅ new-02** · New document 11-travel-expense-policy.md · shelf `hr` · 22.2s
> **Q:** Within how many business days must expense reports be submitted after a trip?  
> **A:** Expense reports must be submitted within 10 business days after returning from a trip. [3] Hilda & Luna Beadworks - Sample HR Policy.docx (3. Expense reports)  
> **Expected:** 10 / ten · **Sources:** 11-travel-expense-policy.md, 11-travel-expense-policy.md, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, 04-workshop-safety-training.docx

**✅ new-03** · New document 12-politica-de-garantia.md · shelf `sales-customers` · 45.4s
> **Q:** ¿Cuánto dura la garantía de los broches y cierres?  
> **A:** La garantía de los broches y cierres dura **6 meses**. [1]  
> **Expected:** 6 meses / seis meses / 6 months · **Sources:** 12-politica-de-garantia.md, 12-politica-de-garantia.md, 07-q3-2026-sales-meeting-notes.txt, 08-customer-faq.txt, 12-politica-de-garantia.md

**✅ new-04** · New document 12-politica-de-garantia.md · shelf `sales-customers` · 36.1s
> **Q:** What do I need to send to make a warranty claim?  
> **A:** To make a warranty claim, you need to send the following:  - Your order number - Photos of the defect [5]  
> **Expected:** pedido / order number / order AND foto / photo · **Sources:** 09-shipping-returns-policy.md, 09-shipping-returns-policy.md, 08-customer-faq.txt, 09-shipping-returns-policy.md, 12-politica-de-garantia.md


## Edge Cases

| | Check | Detail |
|---|---|---|
| ✅ | Unsupported file type is refused with 415 | HTTP 415: {"detail":"unsupported file type for 'photo.png'; supported: .docx, .md, .pdf, .txt"} |
| ✅ | Audit log records every kind of change | missing: [] |
| ℹ️ | Upload of a file already on another shelf | job completed, result {'status': 'skipped_duplicate', 'document_id': 7, 'version_id': 7, 'chunk_count': 0}, document stays in collection 2 (sales-customers is 2). Known gap: the user is not told the file was skipped. |
| ✅ | Unchanged re-upload is skipped as a duplicate | completed {'status': 'skipped_duplicate', 'document_id': 5, 'version_id': 5, 'chunk_count': 0} |
| ℹ️ | Empty .txt upload | HTTP 422: {"detail":"'empty-note.txt' is empty"} |
| ✅ | Thumbs-up feedback is saved |  |
| ℹ️ | Follow-up 'And what is its wholesale price?' in the same session | answer='The wholesale price for the Desert Cactus charm is $0.90 and for the Script Initial (A–Z) charm is $0.70. [3][4]'. Expected limitation: each question is answered on its own. |
| ✅ | Server healthy after bad uploads |  |
| ℹ️ | Asking a retired collection generation directly | error=HTTP 409: {"detail":"collection 'sales-customers' (#2) is a retired copy; ask the active one"}, answer='', sources=[] |
| ✅ | Changing chunk size rebuilds and swaps the collection | blue_green, job completed, new 4 (300 tokens), old active=False |
| ✅ | Reindex a whole collection in place | in_place, completed  |
| ✅ | Reindex a document that answers cite | completed  |
| ✅ | Deleted document is listed in the trash |  |
| ✅ | Trashed document is never cited | sources: ['02-supplier-agreement.docx', '02-supplier-agreement.docx', '02-supplier-agreement.docx', '13-foundry-notes.txt', '02-supplier-agreement.docx'] |

**✅ edge-after-rebuild** · Answers work on the rebuilt collection · shelf `sales-customers` · 46.3s
> **Q:** Which charm sold best in Q3 and how many units were sold?  
> **A:** The charm that sold best in Q3 was CH-2004 "Crescent Moon & Star" with 4,120 units sold. [1]  
> **Expected:** crescent moon AND 4,120 / 4120 · **Sources:** 07-q3-2026-sales-meeting-notes.txt, 08-customer-faq.txt, 07-q3-2026-sales-meeting-notes.txt, 08-customer-faq.txt, 01-product-catalog.pdf

**✅ edge-after-reindex** · Answers still work after reindex · shelf `hr` · 14.8s
> **Q:** When does the company close for the year-end holiday?  
> **A:** The company closes for the year-end holiday from December 19, 2026 through January 2, 2027. This information is found in the [1] document under the section titled "Holiday Closure Schedule".  
> **Expected:** december 19 · **Sources:** 05-holiday-announcement.pdf, 05-holiday-announcement.pdf, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx, Hilda & Luna Beadworks - Sample HR Policy.docx

**✅ edge-followup-1** · Follow-up setup question · shelf `sales-customers` · 51.2s
> **Q:** What is the retail price of the Desert Sand Faceted bead?  
> **A:** The retail price of the Desert Sand Faceted bead (SKU GB-1002) is $1.00. [1]  
> **Expected:** 1.00 / $1 · **Sources:** 01-product-catalog.pdf, 10-wholesale-pricing-sheet.md, 10-wholesale-pricing-sheet.md, 08-customer-faq.txt, 07-q3-2026-sales-meeting-notes.txt

**✅ edge-trash-answer** · Trashed document is no longer used for answers · shelf `suppliers-quality` · 20.7s
> **Q:** How long are Quality Register records retained?  
> **A:** not found in the documents  
> **Expected:** not found in the documents · **Sources:** 02-supplier-agreement.docx, 02-supplier-agreement.docx, 02-supplier-agreement.docx, 13-foundry-notes.txt, 02-supplier-agreement.docx


## Persistence Prepare

| | Check | Detail |
|---|---|---|
| ℹ️ | Snapshot taken; restart-check upload queued | job 24. Now kill the server and start it again. |


## Persistence Verify

| | Check | Detail |
|---|---|---|
| ✅ | Documents survive the restart | 14 documents |
| ✅ | Job interrupted by the restart is recovered and completes | completed  |
| ✅ | Chat history survives the restart | 55 sessions |
| ✅ | Trash survives the restart |  |

**✅ per-answer** · Answers work after the restart · shelf `hr` · 74.5s
> **Q:** What is the restart check code word?  
> **A:** The restart check code word is LAPISLAZULI. [1], [2]  
> **Expected:** lapislazuli · **Sources:** 14-restart-check.txt, 14-restart-check.txt, 06-onboarding-checklist.txt, 04-workshop-safety-training.docx, Hilda & Luna Beadworks - Sample HR Policy.docx


## Ui

| | Check | Detail |
|---|---|---|
| ✅ | Queue: Cancel on a pending job | cancelled in 305 ms (run 1: lost, and the request waited 9 s); job shows Retry |
| ✅ | Queue: Cancel on a job the worker already claimed | turned into a stop request (cancel_requested) instead of being lost; uploads now stop before writing (unit test) |
| ✅ | Chat: shelf picker | new chat says 'Choose a shelf:' with only real shelves and Send disabled; /chat/55 opens on sales-customers, /chat/56 on hr, also after a reload; no 'default' shelf created |
| ✅ | Chat: Stop keeps the partial answer visible | 'The workshop emergency' stayed on screen and became the saved message |
| ✅ | Chat: answers without valid citations show a warning | the stopped partial answer shows 'This answer has no citations ... Verify it below.' |
| ✅ | Collections: Change form offers only embedding models | options: Default, bge-m3, all-minilm:latest (run 1: every model, bge-m3 twice) |
| ✅ | No browser console errors | checked on Chat, Collections and Queue |


## Errors and server log excerpts

- `e2e-130944-edge_cases-355` POST /api/chat → 409 HTTP 409: {"detail":"collection 'sales-customers' (#2) is a retired copy; ask the active one"}

## Known limitations (recorded, not failures)

- A file already on another shelf is skipped as a duplicate without telling the user.
- There is no restore-from-trash endpoint yet (Phase 5).
- Each question is answered on its own; the chat does not use earlier turns.
- Answers come from `qwen2.5:3b` on a 7.2 GB RAM laptop (decision 0004); a 7B/8B model would answer more precisely and faster on better hardware.
