
    def get_person_details_with_quality(self, person_id: str, outlier_threshold: float = 0.65) -> Optional[Dict[str, Any]]:
        """Get person details with quality scores and outlier detection.

        Calculates cosine similarity of each embedding to the person's centroid.
        Embeddings with similarity below threshold are marked as potential outliers.

        Args:
            person_id: Person's unique identifier
            outlier_threshold: Similarity threshold below which embeddings are outliers (default 0.65)

        Returns:
            Dict with person info, samples with quality_score and is_outlier flags
        """
        import numpy as np

        # Get base person info
        person = self.get_person(person_id)
        if not person:
            return None

        # Get positive embeddings WITH vectors
        cursor = self.conn.execute(
            """SELECT id, embedding, source_image, created_at, confidence
               FROM face_embeddings WHERE person_id = ? ORDER BY created_at DESC""",
            (person_id,)
        )
        
        embeddings_data = []
        vectors = []
        for row in cursor.fetchall():
            vec = self._blob_to_embedding(row[1])
            vectors.append(vec)
            embeddings_data.append({
                "id": row[0],
                "vector": vec,
                "thumb": row[2],
                "created_at": row[3],
                "confidence": row[4],
                "type": "positive"
            })

        # Calculate centroid and quality scores
        positive_samples = []
        outlier_count = 0
        avg_quality = 0.0
        
        if len(vectors) > 0:
            # Calculate centroid (mean of all embeddings)
            vectors_np = np.array(vectors)
            centroid = np.mean(vectors_np, axis=0)
            centroid_norm = np.linalg.norm(centroid)
            
            if centroid_norm > 0:
                centroid = centroid / centroid_norm
                
                # Calculate quality score for each embedding
                similarities = []
                for i, emb_data in enumerate(embeddings_data):
                    vec_np = np.array(emb_data["vector"])
                    vec_norm = np.linalg.norm(vec_np)
                    if vec_norm > 0:
                        vec_np = vec_np / vec_norm
                        similarity = float(np.dot(centroid, vec_np))
                    else:
                        similarity = 0.0
                    
                    similarities.append(similarity)
                    is_outlier = similarity < outlier_threshold
                    if is_outlier:
                        outlier_count += 1
                    
                    positive_samples.append({
                        "id": emb_data["id"],
                        "thumb": emb_data["thumb"],
                        "created_at": emb_data["created_at"],
                        "confidence": emb_data["confidence"],
                        "type": "positive",
                        "quality_score": round(similarity * 100, 1),
                        "is_outlier": is_outlier
                    })
                
                avg_quality = sum(similarities) / len(similarities) * 100 if similarities else 0
            else:
                # Fallback: no valid centroid
                for emb_data in embeddings_data:
                    positive_samples.append({
                        "id": emb_data["id"],
                        "thumb": emb_data["thumb"],
                        "created_at": emb_data["created_at"],
                        "confidence": emb_data["confidence"],
                        "type": "positive",
                        "quality_score": 100.0,
                        "is_outlier": False
                    })
        
        # Get negative samples (no quality score needed)
        cursor = self.conn.execute(
            """SELECT id, thumb, created_at
               FROM negative_embeddings WHERE person_id = ? ORDER BY created_at DESC""",
            (person_id,)
        )
        negative_samples = []
        for row in cursor.fetchall():
            negative_samples.append({
                "id": row[0],
                "thumb": row[1],
                "created_at": row[2],
                "type": "negative",
                "quality_score": None,
                "is_outlier": False
            })

        # Get recognition count
        person_name = person.get("name", "")
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM recognition_history WHERE person_id = ? OR person_name = ?",
            (person_id, person_name)
        )
        recognition_count = cursor.fetchone()[0]

        # Get last seen
        cursor = self.conn.execute(
            """SELECT camera_name, recognized_at FROM recognition_history
               WHERE person_id = ? OR person_name = ? ORDER BY recognized_at DESC LIMIT 1""",
            (person_id, person_name)
        )
        last_seen_row = cursor.fetchone()
        last_seen = last_seen_row[1] if last_seen_row else None
        last_camera = last_seen_row[0] if last_seen_row else None

        return {
            "id": person_id,
            "name": person.get("name", "Unknown"),
            "created_at": person.get("created_at"),
            "positive_samples": positive_samples,
            "negative_samples": negative_samples,
            "positive_count": len(positive_samples),
            "negative_count": len(negative_samples),
            "recognition_count": recognition_count,
            "last_seen": last_seen,
            "last_camera": last_camera,
            "avg_quality": round(avg_quality, 1),
            "outlier_count": outlier_count,
            "outlier_threshold": outlier_threshold * 100
        }

    def bulk_delete_embeddings(self, embedding_ids: List[int], embedding_type: str = "positive") -> Dict[str, int]:
        """Delete multiple embeddings at once.

        Args:
            embedding_ids: List of embedding IDs to delete
            embedding_type: 'positive' or 'negative'

        Returns:
            Dict with success_count and failure_count
        """
        success_count = 0
        failure_count = 0
        
        for eid in embedding_ids:
            try:
                if embedding_type == "positive":
                    result = self.delete_embedding(eid)
                else:
                    result = self.delete_negative_embedding(eid)
                if result:
                    success_count += 1
                else:
                    failure_count += 1
            except Exception as e:
                _LOGGER.error(f"Bulk delete failed for embedding {eid}: {e}")
                failure_count += 1
        
        return {"success_count": success_count, "failure_count": failure_count}
