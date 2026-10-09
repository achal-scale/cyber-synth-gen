"""
Generate 100 avatar images from DiceBear API and create users.json with 100 users.
Run from repo root: python backend/scripts/generate_seed_avatars.py
Or from backend: python scripts/generate_seed_avatars.py
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
SEED_IMAGES_DIR = os.path.join(BACKEND_DIR, "uploads", "seed_images")
DATA_DIR = os.path.join(BACKEND_DIR, "seeds", "data")

PRAVATAR_URL = "https://i.pravatar.cc"
AVATAR_SIZE = 128
NUM_USERS = 100
MAX_PRAVATAR_ID = 70

FIRST_NAMES = [
    "Alex", "Jordan", "Sam", "Taylor", "Casey", "Morgan", "Riley", "Avery",
    "Quinn", "Reese", "Blake", "Hayden", "Dakota", "Skyler", "Parker", "Cameron",
    "Jamie", "Kendall", "Logan", "River", "Phoenix", "Emery", "Finley", "Rowan",
    "Sage", "Charlie", "Frankie", "Drew", "Elliot", "Peyton", "Adrian", "Robin",
    "Jean", "Claude", "Lou", "Marion", "Dominique", "Simone", "Noel", "Michel",
    "Chris", "Pat", "Jan", "Kelly", "Kim", "Jesse", "Terry", "Stacey", "Robin",
    "Bev", "Gail", "Lynn", "Jo", "Sam", "Bobbie", "Rene", "Carmen", "Angel",
    "Maria", "Luis", "Carlos", "Ana", "Diego", "Sofia", "Miguel", "Elena",
    "Nina", "Leo", "Mia", "Luca", "Zoe", "Oscar", "Luna", "Ian", "Eva",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
    "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen",
    "Hill", "Flores", "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera",
]


def download_avatar(index: int, dest_path: str) -> None:
    pravatar_id = ((index - 1) % MAX_PRAVATAR_ID) + 1
    url = f"{PRAVATAR_URL}/{AVATAR_SIZE}?img={pravatar_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "W-Seed-Script/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(data)


def main() -> None:
    os.makedirs(SEED_IMAGES_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    print(f"Downloading {NUM_USERS} avatars to {SEED_IMAGES_DIR} ...")
    for i in range(1, NUM_USERS + 1):
        dest = os.path.join(SEED_IMAGES_DIR, f"avatar_{i:03d}.jpg")
        if os.path.exists(dest):
            print(f"  {dest} exists, skip")
            continue
        try:
            download_avatar(i, dest)
            print(f"  {i}/{NUM_USERS} ok")
        except Exception as e:
            print(f"  {i} failed: {e}", file=sys.stderr)
            raise

    users = [
        {"id": "user-1", "username": "w_admin", "display_name": "W Admin", "email": "admin@w.local", "password": "password123", "bio": "Official updates from the W team.", "avatar_url": "avatar_001.jpg", "cover_url": None, "verified": True, "created_at": "2024-01-01T00:00:00"},
        {"id": "user-2", "username": "w_news", "display_name": "W News", "email": "news@w.local", "password": "password123", "bio": "Daily highlights from the community.", "avatar_url": "avatar_002.jpg", "cover_url": None, "verified": True, "created_at": "2024-01-02T00:00:00"},
        {"id": "user-3", "username": "w_support", "display_name": "W Support", "email": "support@w.local", "password": "password123", "bio": "Here to help you get started.", "avatar_url": "avatar_003.jpg", "cover_url": None, "verified": False, "created_at": "2024-01-03T00:00:00"},
    ]
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    for i in range(4, NUM_USERS + 1):
        first = FIRST_NAMES[(i - 1) % len(FIRST_NAMES)]
        last = LAST_NAMES[(i - 1) % len(LAST_NAMES)]
        display_name = f"{first} {last}"
        username = f"user_{i:03d}".replace(" ", "_").lower()
        users.append({
            "id": f"user-{i}",
            "username": username,
            "display_name": display_name,
            "email": f"{username}@w.local",
            "password": "password123",
            "bio": f"User {i} on W.",
            "avatar_url": f"avatar_{i:03d}.jpg",
            "cover_url": None,
            "verified": i <= 5,
            "created_at": created,
        })

    users_path = os.path.join(DATA_DIR, "users.json")
    with open(users_path, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(users)} users to {users_path}")


if __name__ == "__main__":
    main()
