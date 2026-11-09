# Demo corpus: Hilda & Luna Beadworks

**Everything in this folder is fictional sample content**, written to test and
show off this local RAG app. Hilda & Luna Beadworks is not a real company: its
policies, prices, people, addresses and e-mail addresses are invented and are
not guidance of any kind.

Each subfolder of `hilda-luna/` becomes a shelf (collection):

| Shelf | Contents |
|---|---|
| `hr` | Employee handbook, workshop safety training, holiday announcement, onboarding checklist |
| `operations` | Product catalog, supplier agreement, quality control manual, shipping and returns policy, wholesale price sheet |
| `customer-support` | Customer FAQ |
| `meetings` | Q3 2026 sales meeting notes |

Load it (Ollama must be running, for the embeddings):

```bash
cd backend && python -m app.cli seed-demo
```

Running it again changes nothing: files already stored are skipped as duplicates.
Then open the employee portal at http://localhost:8000/intranet and ask Luna,
for example "¿Cuántos días de vacaciones tengo en mi tercer año?".
