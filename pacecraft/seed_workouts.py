from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-03-024425596638"

db = firestore.Client(project=PROJECT_ID)

sample_workouts = [
    {
        "id": "c25k_w1d1",
        "title": "Couch to 5K: Week 1 Walk-Run Intervals",
        "category": "Intervals / Beginner",
        "description": "5 min brisk walk warmup, then alternate 60s jog and 90s walk for 20 mins, 5 min cool down.",
        "target_distance_km": 3.0,
        "estimated_duration_min": 30,
        "interval_type": "run_walk",
        "run_interval_seconds": 60,
        "walk_interval_seconds": 90,
        "difficulty": "Beginner",
    },
    {
        "id": "easy_recovery_5k",
        "title": "Easy Aerobic Recovery Run",
        "category": "Recovery",
        "description": "Comfortable, conversational pace run to build aerobic base without accumulated fatigue.",
        "target_distance_km": 5.0,
        "estimated_duration_min": 35,
        "interval_type": "continuous",
        "run_interval_seconds": 0,
        "walk_interval_seconds": 0,
        "difficulty": "Beginner/Intermediate",
    },
    {
        "id": "tempo_threshold_8k",
        "title": "Lactate Threshold Tempo Run",
        "category": "Tempo",
        "description": "1.5 km warmup, 5 km at comfortably hard lactate threshold pace, 1.5 km cooldown.",
        "target_distance_km": 8.0,
        "estimated_duration_min": 45,
        "interval_type": "tempo",
        "run_interval_seconds": 0,
        "walk_interval_seconds": 0,
        "difficulty": "Intermediate",
    },
    {
        "id": "speed_intervals_400m",
        "title": "VO2 Max 400m Track Repeats",
        "category": "Speed / Intervals",
        "description": "8 x 400m fast repeats with 90s walking recovery between sets.",
        "target_distance_km": 6.5,
        "estimated_duration_min": 40,
        "interval_type": "speed_repeats",
        "run_interval_seconds": 90,
        "walk_interval_seconds": 90,
        "difficulty": "Advanced",
    },
    {
        "id": "long_run_progression_12k",
        "title": "Long Endurance Progression Run",
        "category": "Long Run",
        "description": "12 km continuous long run, starting easy and finishing the last 2 km at goal half-marathon pace.",
        "target_distance_km": 12.0,
        "estimated_duration_min": 75,
        "interval_type": "continuous",
        "run_interval_seconds": 0,
        "walk_interval_seconds": 0,
        "difficulty": "Intermediate/Advanced",
    },
]

def seed():
    batch = db.batch()
    col = db.collection("workouts")
    for w in sample_workouts:
        doc_ref = col.document(w["id"])
        batch.set(doc_ref, w)
    batch.commit()
    print(f"Successfully seeded {len(sample_workouts)} workouts into Firestore collection 'workouts'!")

if __name__ == "__main__":
    seed()
