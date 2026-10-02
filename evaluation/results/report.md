# Retrieval evaluation

40 manually labeled queries; 10 documents; 77 chunks; RRF k=60.

Labels were authored from document contents before this run, independently of retriever outputs.
Recall@N is relevant documents in the first N unique results divided by all labeled relevant documents. MRR is mean reciprocal rank of the first relevant document (zero if absent). Aggregates are macro averages across queries.

All available candidates are evaluated. Semantic document order uses the best-ranked chunk, with consecutive ranks after deduplication. RRF ties use document name. No parameter tuning was performed.

Limitations: this is a small, manually judged development set, not an independently judged held-out benchmark. The source documents contain repeated paragraphs. With only ten documents and full candidate depth, Recall@10 is largely a coverage check. Results do not establish performance on larger corpora or shallow candidate pools.

## Aggregate metrics

| System | Recall@5 | Recall@10 | MRR |
|---|---:|---:|---:|
| bm25 | 0.9542 | 0.9750 | 0.8058 |
| semantic | 0.9875 | 1.0000 | 0.9313 |
| rrf | 1.0000 | 1.0000 | 0.8771 |

## Metrics by query category

| Category | System | Recall@5 | Recall@10 | MRR |
|---|---|---:|---:|---:|
| broad | bm25 | 0.7708 | 0.8750 | 0.7750 |
| broad | semantic | 0.9375 | 1.0000 | 0.8438 |
| broad | rrf | 1.0000 | 1.0000 | 0.8229 |
| conceptual | bm25 | 1.0000 | 1.0000 | 0.9375 |
| conceptual | semantic | 1.0000 | 1.0000 | 1.0000 |
| conceptual | rrf | 1.0000 | 1.0000 | 0.9375 |
| exact_technical | bm25 | 1.0000 | 1.0000 | 1.0000 |
| exact_technical | semantic | 1.0000 | 1.0000 | 1.0000 |
| exact_technical | rrf | 1.0000 | 1.0000 | 1.0000 |
| natural_language | bm25 | 1.0000 | 1.0000 | 0.6562 |
| natural_language | semantic | 1.0000 | 1.0000 | 0.9375 |
| natural_language | rrf | 1.0000 | 1.0000 | 0.8750 |
| paraphrased | bm25 | 1.0000 | 1.0000 | 0.6604 |
| paraphrased | semantic | 1.0000 | 1.0000 | 0.8750 |
| paraphrased | rrf | 1.0000 | 1.0000 | 0.7500 |

## Per-query results

Each cell is Recall@5 / Recall@10 / reciprocal rank. Full rankings and chunk metadata are in results.json; tabular results are in per_query.csv.

| ID | Query | Relevant documents | BM25 | Semantic | RRF |
|---|---|---|---|---|---|
| q01 | BSON types and ObjectId identifiers | 01_introduction.txt, 02_collections_documents.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q02 | updateOne $set $inc $push | 03_crud_operations.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q03 | compound index leading fields explain plans | 04_indexing.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q04 | $match $group $unwind aggregation stages | 05_aggregation.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q05 | JSON Schema validation embedding referencing | 06_data_modeling.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q06 | replica set majority write concern | 07_replication.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q07 | mongos hashed shard key range queries | 08_sharding.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q08 | SCRAM X.509 role-based access control | 09_security.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q09 | Why can documents in a collection have different fields? | 01_introduction.txt, 02_collections_documents.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q10 | How is replacing a document different from updating selected fields? | 03_crud_operations.txt | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 0.5000 |
| q11 | Why can adding more indexes reduce write performance? | 04_indexing.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q12 | Why should filtering happen early in an aggregation pipeline? | 05_aggregation.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q13 | When should related data be embedded rather than referenced? | 02_collections_documents.txt, 06_data_modeling.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q14 | How does replication differ from having a backup? | 07_replication.txt, 10_backup_monitoring.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q15 | Why can a badly chosen shard key create hotspots? | 08_sharding.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q16 | What is the difference between authentication and authorization? | 09_security.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q17 | Store records whose attributes evolve without forcing identical columns | 01_introduction.txt, 02_collections_documents.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q18 | Change a counter and append an item without overwriting the whole record | 03_crud_operations.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q19 | Avoid reading every record just to find a few matching values | 04_indexing.txt | 1.0000 / 1.0000 / 0.3333 | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 0.5000 |
| q20 | Turn many orders into totals and averages for each customer | 05_aggregation.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q21 | Keep a shipping address with its order but share product records separately | 06_data_modeling.txt, 02_collections_documents.txt | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 0.5000 |
| q22 | Keep serving the application when the current writer machine goes down | 07_replication.txt | 1.0000 / 1.0000 / 0.2500 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 0.5000 |
| q23 | Spread growing storage and incoming writes across machines evenly | 08_sharding.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 |
| q24 | Limit each application's database account to only the actions it needs | 09_security.txt | 1.0000 / 1.0000 / 0.2000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 0.5000 |
| q25 | MongoDB document database basics | 01_introduction.txt, 02_collections_documents.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q26 | Designing flexible data structures and validation rules | 01_introduction.txt, 02_collections_documents.txt, 06_data_modeling.txt | 0.6667 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q27 | Improving query and analytics performance | 04_indexing.txt, 05_aggregation.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q28 | Planning capacity and horizontal database growth | 08_sharding.txt, 10_backup_monitoring.txt | 1.0000 / 1.0000 / 1.0000 | 0.5000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 |
| q29 | Production availability and disaster recovery | 07_replication.txt, 10_backup_monitoring.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q30 | Protecting database access and sensitive stored data | 09_security.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q31 | Working with records and producing analytical reports | 03_crud_operations.txt, 05_aggregation.txt | 0.0000 / 0.0000 / 0.0000 | 1.0000 / 1.0000 / 0.2500 | 1.0000 / 1.0000 / 0.2500 |
| q32 | Choosing data layout and indexes for application access patterns | 06_data_modeling.txt, 04_indexing.txt | 0.5000 / 1.0000 / 0.2000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 0.3333 |
| q33 | I forgot to give my new document an ID. What happens and can I change it later? | 02_collections_documents.txt | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q34 | I only need two fields from matching records. How can I avoid returning everything? | 03_crud_operations.txt | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 |
| q35 | Our writes slowed down after we added lots of indexes. What should we check? | 04_indexing.txt | 1.0000 / 1.0000 / 0.2500 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 0.5000 |
| q36 | I need to combine related records from another collection in a report. Which stage helps? | 05_aggregation.txt | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q37 | My user document keeps growing as I add every event. Is this a good design? | 06_data_modeling.txt | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 0.5000 |
| q38 | Can I read from a secondary if slightly old data is acceptable? | 07_replication.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q39 | We use timestamps as our shard key and one machine gets most new writes. Why? | 08_sharding.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| q40 | How do I decide acceptable data loss and prove we can restore service in time? | 10_backup_monitoring.txt | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
