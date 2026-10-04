"""User-defined vector estimates; no assumptions about provider capacity."""
import math


def estimate_vector_budget(*, target_documents, indexed_documents, existing_chunks,
                           estimated_chunks_per_document, max_vectors_estimate,
                           actual_points=None):
    observed = existing_chunks / indexed_documents if indexed_documents else None
    average = max(estimated_chunks_per_document, observed or 0)
    remaining = max(0, target_documents - indexed_documents)
    baseline = actual_points if actual_points is not None else existing_chunks
    estimated = baseline + math.ceil(remaining * average)
    return {"target_documents": target_documents, "indexed_documents": indexed_documents,
            "observed_chunks_per_document": observed, "estimated_chunks_per_document": average,
            "remaining_documents": remaining, "estimated_vectors": estimated,
            "max_vectors_estimate": max_vectors_estimate, "actual_qdrant_points": actual_points,
            "allowed": estimated <= max_vectors_estimate}
