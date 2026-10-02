# Cross-encoder evaluation

Model: `cross-encoder/ms-marco-MiniLM-L6-v2`; candidate_k=10; top_k=10; maximum input length=512 tokens.

Frozen BM25, semantic and RRF outputs from the existing evaluation are reused. Corpus and manual relevance labels are checked against their original hashes. Metrics use only those labels, never model scores. No tuning was performed on the labels.

Each candidate uses its best semantic chunk; missing chunk text falls back to full document text. Long pairs may be truncated by the cross-encoder. Score ties preserve RRF order.

This development set contains 40 queries and only 10 documents, with repeated source paragraphs. Recall@10 has a ceiling effect. Changes in irrelevant-document order need not improve measured relevance. If top_k or candidate_k is below 10, Recall@10 measures only that truncated result set.

## Aggregate metrics

| Stage | Recall@5 | Recall@10 | MRR |
|---|---:|---:|---:|
| bm25 | 0.9542 | 0.9750 | 0.8058 |
| semantic | 0.9875 | 1.0000 | 0.9313 |
| rrf | 1.0000 | 1.0000 | 0.8771 |
| rrf_reranker | 0.9667 | 1.0000 | 0.8958 |

## Per-query metrics

Cells show Recall@5 / Recall@10 / reciprocal rank. Full rankings, candidate metadata and reranker scores are in results.json.

| ID | Query | BM25 | Semantic | RRF | RRF + reranker | Change |
|---|---|---|---|---|---|---|
| q01 | BSON types and ObjectId identifiers | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q02 | updateOne $set $inc $push | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q03 | compound index leading fields explain plans | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q04 | $match $group $unwind aggregation stages | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q05 | JSON Schema validation embedding referencing | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q06 | replica set majority write concern | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q07 | mongos hashed shard key range queries | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q08 | SCRAM X.509 role-based access control | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q09 | Why can documents in a collection have different fields? | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q10 | How is replacing a document different from updating selected fields? | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 | improved |
| q11 | Why can adding more indexes reduce write performance? | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q12 | Why should filtering happen early in an aggregation pipeline? | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q13 | When should related data be embedded rather than referenced? | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q14 | How does replication differ from having a backup? | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q15 | Why can a badly chosen shard key create hotspots? | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q16 | What is the difference between authentication and authorization? | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q17 | Store records whose attributes evolve without forcing identical columns | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q18 | Change a counter and append an item without overwriting the whole record | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 0.5000 | decreased |
| q19 | Avoid reading every record just to find a few matching values | 1.0000 / 1.0000 / 0.3333 | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 0.5000 | changed_without_metric_gain |
| q20 | Turn many orders into totals and averages for each customer | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q21 | Keep a shipping address with its order but share product records separately | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 0.5000 | changed_without_metric_gain |
| q22 | Keep serving the application when the current writer machine goes down | 1.0000 / 1.0000 / 0.2500 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 0.3333 | decreased |
| q23 | Spread growing storage and incoming writes across machines evenly | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q24 | Limit each application's database account to only the actions it needs | 1.0000 / 1.0000 / 0.2000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 | improved |
| q25 | MongoDB document database basics | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q26 | Designing flexible data structures and validation rules | 0.6667 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 0.6667 / 1.0000 / 1.0000 | decreased |
| q27 | Improving query and analytics performance | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q28 | Planning capacity and horizontal database growth | 1.0000 / 1.0000 / 1.0000 | 0.5000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 | 0.5000 / 1.0000 / 1.0000 | decreased |
| q29 | Production availability and disaster recovery | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q30 | Protecting database access and sensitive stored data | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q31 | Working with records and producing analytical reports | 0.0000 / 0.0000 / 0.0000 | 1.0000 / 1.0000 / 0.2500 | 1.0000 / 1.0000 / 0.2500 | 0.5000 / 1.0000 / 0.5000 | mixed |
| q32 | Choosing data layout and indexes for application access patterns | 0.5000 / 1.0000 / 0.2000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 0.3333 | 1.0000 / 1.0000 / 0.5000 | improved |
| q33 | I forgot to give my new document an ID. What happens and can I change it later? | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 0.5000 | decreased |
| q34 | I only need two fields from matching records. How can I avoid returning everything? | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q35 | Our writes slowed down after we added lots of indexes. What should we check? | 1.0000 / 1.0000 / 0.2500 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 | improved |
| q36 | I need to combine related records from another collection in a report. Which stage helps? | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q37 | My user document keeps growing as I add every event. Is this a good design? | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 0.5000 | 1.0000 / 1.0000 / 0.5000 | changed_without_metric_gain |
| q38 | Can I read from a secondary if slightly old data is acceptable? | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q39 | We use timestamps as our shard key and one machine gets most new writes. Why? | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |
| q40 | How do I decide acceptable data loss and prove we can restore service in time? | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 | changed_without_metric_gain |

## Changes relative to RRF

Improved/decreased means at least one metric changes in that direction and none changes in the opposite direction. Mixed means both gains and losses. Changed without metric gain means a different ranking but identical measured relevance.

### improved (4)

- q10: How is replacing a document different from updating selected fields? (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.5000)
- q24: Limit each application's database account to only the actions it needs (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.5000)
- q32: Choosing data layout and indexes for application access patterns (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.1667)
- q35: Our writes slowed down after we added lots of indexes. What should we check? (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.5000)

### changed_without_metric_gain (30)

- q01: BSON types and ObjectId identifiers (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q02: updateOne $set $inc $push (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q03: compound index leading fields explain plans (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q04: $match $group $unwind aggregation stages (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q05: JSON Schema validation embedding referencing (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q06: replica set majority write concern (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q07: mongos hashed shard key range queries (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q08: SCRAM X.509 role-based access control (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q09: Why can documents in a collection have different fields? (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q11: Why can adding more indexes reduce write performance? (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q12: Why should filtering happen early in an aggregation pipeline? (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q13: When should related data be embedded rather than referenced? (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q14: How does replication differ from having a backup? (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q15: Why can a badly chosen shard key create hotspots? (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q16: What is the difference between authentication and authorization? (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q17: Store records whose attributes evolve without forcing identical columns (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q19: Avoid reading every record just to find a few matching values (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q20: Turn many orders into totals and averages for each customer (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q21: Keep a shipping address with its order but share product records separately (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q23: Spread growing storage and incoming writes across machines evenly (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q25: MongoDB document database basics (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q27: Improving query and analytics performance (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q29: Production availability and disaster recovery (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q30: Protecting database access and sensitive stored data (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q34: I only need two fields from matching records. How can I avoid returning everything? (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q36: I need to combine related records from another collection in a report. Which stage helps? (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q37: My user document keeps growing as I add every event. Is this a good design? (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q38: Can I read from a secondary if slightly old data is acceptable? (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q39: We use timestamps as our shard key and one machine gets most new writes. Why? (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q40: How do I decide acceptable data loss and prove we can restore service in time? (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)

### decreased (5)

- q18: Change a counter and append an item without overwriting the whole record (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: -0.5000)
- q22: Keep serving the application when the current writer machine goes down (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: -0.1667)
- q26: Designing flexible data structures and validation rules (recall_at_5: -0.3333, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q28: Planning capacity and horizontal database growth (recall_at_5: -0.5000, recall_at_10: +0.0000, reciprocal_rank: +0.0000)
- q33: I forgot to give my new document an ID. What happens and can I change it later? (recall_at_5: +0.0000, recall_at_10: +0.0000, reciprocal_rank: -0.5000)

### mixed (1)

- q31: Working with records and producing analytical reports (recall_at_5: -0.5000, recall_at_10: +0.0000, reciprocal_rank: +0.2500)

### unchanged (0)

None.
